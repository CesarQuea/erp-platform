from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, Uuid, create_engine, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.concurrency import SqlAlchemyCompareAndSet
from app.infrastructure.database.models import CompanyRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.errors import ConcurrencyConflictSignal
from app.platform.commands.model import CommandExecutionRecord, CommandScope


def test_repository_claim_complete_replay_on_sqlite():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CompanyRecord.__table__.create(engine)
    CommandExecutionRecordModel.__table__.create(engine)
    tenant_id, company_id, actor_id, command_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(CompanyRecord).values(
                id=company_id,
                code="C",
                legal_name="Company",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )

    scope = TenantSessionScope()
    repo = SqlAlchemyCommandExecutionRepository(scope)
    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                record = CommandExecutionRecord(
                    command_id=command_id,
                    command_name="x",
                    command_schema_version="1",
                    scope=CommandScope.COMPANY,
                    company_id=company_id,
                    actor_user_id=actor_id,
                    fingerprint="a" * 64,
                )
                assert repo.claim(record)
                repo.complete(
                    command_id,
                    result_code="OK",
                    result_json={"id": "1"},
                    committed_at=now,
                )
        with session.begin():
            with scope.activate(tenant_id, session):
                assert not repo.claim(record)
                replay = repo.get(command_id)
                assert replay is not None
                assert replay.result_code == "OK"
                assert replay.result_json == {"id": "1"}
    engine.dispose()


def test_company_scope_constraint_rejects_missing_company():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CompanyRecord.__table__.create(engine)
    CommandExecutionRecordModel.__table__.create(engine)
    scope = TenantSessionScope()
    repo = SqlAlchemyCommandExecutionRepository(scope)
    record = CommandExecutionRecord(
        command_id=uuid4(),
        command_name="x",
        command_schema_version="1",
        scope=CommandScope.COMPANY,
        company_id=None,
        actor_user_id=uuid4(),
        fingerprint="b" * 64,
    )
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                with scope.activate(uuid4(), session):
                    repo.claim(record)
    engine.dispose()


def test_compare_and_set_increments_once_and_signals_stale_version():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    resource = Table(
        "resource",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("name", String(64), nullable=False),
        Column("version", Integer, nullable=False),
    )
    metadata.create_all(engine)
    resource_id, tenant_id = uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(insert(resource).values(id=resource_id, name="before", version=0))

    scope = TenantSessionScope()
    cas = SqlAlchemyCompareAndSet(scope)
    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                version = cas.update_versioned(
                    resource,
                    identity_column=resource.c.id,
                    identity_value=resource_id,
                    version_column=resource.c.version,
                    expected_version=0,
                    values={"name": "after"},
                )
                assert version == 1
        with pytest.raises(ConcurrencyConflictSignal):
            with session.begin():
                with scope.activate(tenant_id, session):
                    cas.update_versioned(
                        resource,
                        identity_column=resource.c.id,
                        identity_value=resource_id,
                        version_column=resource.c.version,
                        expected_version=0,
                        values={"name": "stale"},
                    )
        row = session.execute(select(resource)).mappings().one()
        assert row["name"] == "after"
        assert row["version"] == 1
    engine.dispose()
