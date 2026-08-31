from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.models import Base, CompanyRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.sync_models import (
    SyncBatchRecordModel,
    SyncStreamRecordModel,
)
from app.infrastructure.database.sync_repository import SqlAlchemySyncJournalRepository
from app.platform.sync.model import SyncChange, SyncChangeKind
from app.platform.sync.service import SyncPublisher
from app.platform.tenancy.errors import TenantSessionScopeError


def _change(name: str = "value") -> SyncChange:
    entity_id = uuid4()
    return SyncChange(
        entity_type="record",
        entity_id=entity_id,
        change_kind=SyncChangeKind.UPSERT,
        schema_version="1",
        entity_version=1,
        payload={"id": str(entity_id), "name": name},
    )


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    # Referencing the mapped classes above guarantees they are present in
    # Base.metadata before create_all.
    assert SyncStreamRecordModel.__tablename__ == "platform_sync_streams"
    assert SyncBatchRecordModel.__tablename__ == "platform_sync_batches"
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant_id = uuid4()
    company_id = uuid4()
    now = datetime.now(timezone.utc)
    with factory() as session, session.begin():
        session.add(
            CompanyRecord(
                id=company_id,
                code="COMPANY",
                legal_name="Test Company",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
    return engine, factory, tenant_id, company_id


def test_sync_journal_publishes_monotonic_batches_in_active_transaction() -> None:
    engine, factory, tenant_id, company_id = _fixture()
    scope = TenantSessionScope()
    repository = SqlAlchemySyncJournalRepository(scope)
    publisher = SyncPublisher(repository, max_batch_bytes=64 * 1024)

    with factory() as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                first = publisher.publish(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                    changes=(_change("one"),),
                )
                second = publisher.publish(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                    changes=(_change("two"),),
                )
                assert first.position == 1
                assert second.position == 2

    with factory() as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                assert repository.current_position(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                ) == 2
                batches = repository.list_batches(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                    after_position=0,
                    limit=10,
                )
                assert [batch.position for batch in batches] == [1, 2]
                assert [batch.changes[0].payload["name"] for batch in batches] == [
                    "one",
                    "two",
                ]
    engine.dispose()


def test_sync_publish_rollback_reverts_batch_and_stream_position() -> None:
    engine, factory, tenant_id, company_id = _fixture()
    scope = TenantSessionScope()
    repository = SqlAlchemySyncJournalRepository(scope)
    publisher = SyncPublisher(repository, max_batch_bytes=64 * 1024)

    with pytest.raises(RuntimeError, match="force rollback"):
        with factory() as session:
            with session.begin():
                with scope.activate(tenant_id, session):
                    publisher.publish(
                        company_id=company_id,
                        module_id="testsync",
                        stream_id="default",
                        changes=(_change(),),
                    )
                    raise RuntimeError("force rollback")

    with factory() as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                assert repository.current_position(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                ) == 0
                assert repository.list_batches(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                    after_position=0,
                    limit=10,
                ) == ()
    engine.dispose()


def test_sync_publisher_requires_existing_transaction_scope() -> None:
    engine, _factory, _tenant_id, company_id = _fixture()
    scope = TenantSessionScope()
    publisher = SyncPublisher(
        SqlAlchemySyncJournalRepository(scope),
        max_batch_bytes=64 * 1024,
    )
    with pytest.raises(TenantSessionScopeError, match="No active tenant"):
        publisher.publish(
            company_id=company_id,
            module_id="testsync",
            stream_id="default",
            changes=(_change(),),
        )
    engine.dispose()


def test_sync_batch_size_limit_fails_before_journal_mutation() -> None:
    engine, factory, tenant_id, company_id = _fixture()
    scope = TenantSessionScope()
    repository = SqlAlchemySyncJournalRepository(scope)
    publisher = SyncPublisher(repository, max_batch_bytes=32)

    with factory() as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                with pytest.raises(Exception) as captured:
                    publisher.publish(
                        company_id=company_id,
                        module_id="testsync",
                        stream_id="default",
                        changes=(_change("x" * 200),),
                    )
                assert getattr(captured.value, "code", None) == "SYNC_BATCH_TOO_LARGE"
                assert repository.current_position(
                    company_id=company_id,
                    module_id="testsync",
                    stream_id="default",
                ) == 0
    engine.dispose()
