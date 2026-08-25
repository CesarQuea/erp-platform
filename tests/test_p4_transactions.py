from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, Uuid, create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors.models import PlatformError
from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.concurrency import SqlAlchemyCompareAndSet
from app.infrastructure.database.models import CompanyRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.model import CommandRequest, CommandResult, CommandScope
from app.platform.commands.service import CommandExecutionService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext


class FixedClock:
    def now(self):
        return datetime(2026, 8, 24, 20, 30, tzinfo=timezone.utc)


class Boundary:
    def __init__(self, engine, scope: TenantSessionScope, tenant_id: UUID):
        self.engine = engine
        self.scope = scope
        self.tenant_id = tenant_id

    def run(self, operation):
        factory = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        with factory() as session:
            with session.begin():
                with self.scope.activate(self.tenant_id, session):
                    return operation()


class Factory:
    def __init__(self, engine, scope):
        self.engine = engine
        self.scope = scope

    def for_tenant(self, context: TenantContext):
        return Boundary(self.engine, self.scope, context.tenant_id)


def setup_db(path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    CompanyRecord.__table__.create(engine)
    CommandExecutionRecordModel.__table__.create(engine)
    metadata = MetaData()
    business = Table(
        "p4_business",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("value", String(64), nullable=False),
        Column("version", Integer, nullable=False),
    )
    metadata.create_all(engine)
    return engine, business


def principal(tenant_id, company_id):
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
    )


def test_idempotency_and_business_mutation_commit_together(tmp_path):
    tenant_id, company_id, resource_id = uuid4(), uuid4(), uuid4()
    engine, business = setup_db(tmp_path / "tenant.db")
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
    service = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(scope), Factory(engine, scope), clock=FixedClock()
    )
    p = principal(tenant_id, company_id)
    request = CommandRequest(uuid4(), "test.create", "1", CommandScope.COMPANY)

    def operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(business).values(id=resource_id, value="once", version=0)
        )
        return CommandResult("CREATED", {"id": str(resource_id)})

    first = service.execute(request, {"id": resource_id}, authorize=lambda: p, operation=operation)
    replay = service.execute(request, {"id": resource_id}, authorize=lambda: p, operation=operation)
    assert not first.replayed and replay.replayed
    with engine.connect() as conn:
        assert len(conn.execute(select(business)).all()) == 1
        assert conn.execute(select(CommandExecutionRecordModel)).one().result_code == "CREATED"
    engine.dispose()


def test_failure_rolls_back_business_and_claim_then_retry_succeeds(tmp_path):
    tenant_id, company_id, resource_id = uuid4(), uuid4(), uuid4()
    engine, business = setup_db(tmp_path / "rollback.db")
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
    service = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(scope), Factory(engine, scope), clock=FixedClock()
    )
    p = principal(tenant_id, company_id)
    request = CommandRequest(uuid4(), "test.create", "1", CommandScope.COMPANY)

    def failing():
        scope.current().execute(insert(business).values(id=resource_id, value="bad", version=0))
        raise RuntimeError("fail after mutation")

    with pytest.raises(RuntimeError):
        service.execute(request, {}, authorize=lambda: p, operation=failing)
    with engine.connect() as conn:
        assert conn.execute(select(business)).all() == []
        assert conn.execute(select(CommandExecutionRecordModel)).all() == []

    def success():
        scope.current().execute(insert(business).values(id=resource_id, value="ok", version=0))
        return CommandResult("OK", {})

    service.execute(request, {}, authorize=lambda: p, operation=success)
    with engine.connect() as conn:
        assert len(conn.execute(select(business)).all()) == 1
        assert len(conn.execute(select(CommandExecutionRecordModel)).all()) == 1
    engine.dispose()


def test_cas_conflict_maps_to_platform_error_after_transaction_exit(tmp_path):
    tenant_id, company_id, resource_id = uuid4(), uuid4(), uuid4()
    engine, business = setup_db(tmp_path / "cas.db")
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
        conn.execute(insert(business).values(id=resource_id, value="before", version=1))
    scope = TenantSessionScope()
    cas = SqlAlchemyCompareAndSet(scope)
    service = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(scope), Factory(engine, scope), clock=FixedClock()
    )
    p = principal(tenant_id, company_id)
    request = CommandRequest(
        uuid4(), "test.update", "1", CommandScope.COMPANY, expected_version=0
    )

    def operation():
        cas.update_versioned(
            business,
            identity_column=business.c.id,
            identity_value=resource_id,
            version_column=business.c.version,
            expected_version=0,
            values={"value": "stale"},
        )
        return CommandResult("OK", {})

    with pytest.raises(PlatformError) as exc:
        service.execute(request, {"value": "stale"}, authorize=lambda: p, operation=operation)
    assert exc.value.code == "CONCURRENCY_CONFLICT"
    with engine.connect() as conn:
        row = conn.execute(select(business)).mappings().one()
        assert row["value"] == "before" and row["version"] == 1
        assert conn.execute(select(CommandExecutionRecordModel)).all() == []
    engine.dispose()
