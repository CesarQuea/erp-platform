from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, String, Table, Uuid, delete, insert, select

from app.core.errors.models import PlatformError
from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.sync_models import SyncBatchRecordModel, SyncStreamRecordModel
from app.infrastructure.database.sync_repository import SqlAlchemySyncJournalRepository
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import SqlAlchemyTenantTransactionBoundaryFactory
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.commands.model import CommandRequest, CommandResult, CommandScope
from app.platform.commands.service import CommandExecutionService
from app.platform.company.service import CompanyService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.sync.model import SyncChange, SyncChangeKind
from app.platform.sync.service import SyncPublisher
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig

_TEST_ENV = "P7_TEST_TENANT_DATABASES_JSON"
_P7_HEAD = "0006_p7_sync_foundation"
_TEST_MODULE_ID = "testsync"


def _postgres_entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for real PostgreSQL P-7 tests")
    parsed = json.loads(raw)
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in parsed.items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain at least two PostgreSQL tenant databases")
    return entries[:2]


@pytest.fixture
def postgres_runtime():
    entries = _postgres_entries()
    registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, url) for tenant_id, url in entries}
    )
    runner = TenantMigrationRunner(
        repository_root=Path(__file__).resolve().parents[1],
        target_revision=_P7_HEAD,
    )
    provisioner = TenantProvisioner(registry, migration_runner=runner)
    for tenant_id, _ in entries:
        assert provisioner.provision(TenantContext(tenant_id)) == _P7_HEAD

    scope = TenantSessionScope()
    resolver = SqlAlchemyTenantDataSourceResolver(registry)
    tx_factory = SqlAlchemyTenantTransactionBoundaryFactory(resolver, scope)
    command_service = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(scope),
        tx_factory,
    )
    company_service = CompanyService(
        SqlAlchemyCompanyRepository(scope),
        tx_factory,
    )
    journal = SqlAlchemySyncJournalRepository(scope)
    publisher = SyncPublisher(journal, max_batch_bytes=128 * 1024)

    metadata = MetaData()
    resource = Table(
        "p7_verification_resource",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("value", String(128), nullable=False),
    )
    companies = {}
    for tenant_id, _ in entries:
        context = TenantContext(tenant_id)
        engine = resolver.resolve(context).engine
        resource.create(engine, checkfirst=True)
        with engine.begin() as connection:
            connection.execute(delete(resource))
            connection.execute(delete(SyncBatchRecordModel.__table__))
            connection.execute(delete(SyncStreamRecordModel.__table__))
        companies[tenant_id] = company_service.register_company(
            context,
            code=f"P7-{uuid4().hex[:10]}",
            legal_name="P-7 Verification Company",
        )

    try:
        yield entries, scope, resolver, command_service, journal, publisher, resource, companies
    finally:
        for tenant_id, _ in entries:
            engine = resolver.resolve(TenantContext(tenant_id)).engine
            resource.drop(engine, checkfirst=True)
        resolver.dispose()


def _principal(tenant_id: UUID, company_id: UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
    )


def _change(resource_id: UUID, value: str, *, version: int = 1) -> SyncChange:
    return SyncChange(
        entity_type="verification_resource",
        entity_id=resource_id,
        change_kind=SyncChangeKind.UPSERT,
        schema_version="1",
        entity_version=version,
        payload={"id": str(resource_id), "value": value},
    )


def test_postgres_business_p4_and_sync_commit_atomically_and_replay_once(postgres_runtime):
    entries, scope, resolver, commands, _, publisher, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    command_id, resource_id = uuid4(), uuid4()
    request = CommandRequest(command_id, "p7.atomic.create", "1", CommandScope.COMPANY)

    def operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(resource).values(id=resource_id, value="committed")
        )
        batch = publisher.publish(
            company_id=company.id,
            module_id=_TEST_MODULE_ID,
            stream_id="default",
            changes=(_change(resource_id, "committed"),),
            source_command_id=command_id,
        )
        return CommandResult("CREATED", {"id": str(resource_id), "batch": str(batch.batch_id)})

    first = commands.execute(
        request,
        {"id": resource_id, "value": "committed"},
        authorize=lambda: principal,
        operation=operation,
    )
    replay = commands.execute(
        request,
        {"id": resource_id, "value": "committed"},
        authorize=lambda: principal,
        operation=operation,
    )
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.result.data == first.result.data

    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        assert len(connection.execute(select(resource).where(resource.c.id == resource_id)).all()) == 1
        batches = connection.execute(
            select(
                SyncBatchRecordModel.batch_id,
                SyncBatchRecordModel.position,
                SyncBatchRecordModel.source_command_id,
            ).where(
                SyncBatchRecordModel.company_id == company.id,
                SyncBatchRecordModel.module_id == _TEST_MODULE_ID,
                SyncBatchRecordModel.stream_id == "default",
            )
        ).mappings().all()
        assert len(batches) == 1
        assert batches[0]["position"] == 1
        assert batches[0]["source_command_id"] == command_id
        command = connection.execute(
            select(CommandExecutionRecordModel.committed_at).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ).scalar_one()
        assert command is not None


def test_postgres_sync_publication_failure_rolls_back_business_and_p4_claim(postgres_runtime):
    entries, scope, resolver, commands, _, _, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    command_id, resource_id = uuid4(), uuid4()
    request = CommandRequest(command_id, "p7.atomic.rollback", "1", CommandScope.COMPANY)
    tiny_publisher = SyncPublisher(SqlAlchemySyncJournalRepository(scope), max_batch_bytes=32)

    def operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(resource).values(id=resource_id, value="must-rollback")
        )
        tiny_publisher.publish(
            company_id=company.id,
            module_id=_TEST_MODULE_ID,
            stream_id="default",
            changes=(_change(resource_id, "x" * 100),),
            source_command_id=command_id,
        )
        return CommandResult("UNREACHABLE", {})

    with pytest.raises(PlatformError) as captured:
        commands.execute(
            request,
            {"id": resource_id},
            authorize=lambda: principal,
            operation=operation,
        )
    assert captured.value.code == "SYNC_BATCH_TOO_LARGE"

    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        assert connection.execute(select(resource).where(resource.c.id == resource_id)).all() == []
        assert connection.execute(
            select(CommandExecutionRecordModel.command_id).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ).all() == []
        assert connection.execute(
            select(SyncBatchRecordModel.batch_id).where(
                SyncBatchRecordModel.source_command_id == command_id
            )
        ).all() == []
        stream_position = connection.execute(
            select(SyncStreamRecordModel.current_position).where(
                SyncStreamRecordModel.company_id == company.id,
                SyncStreamRecordModel.module_id == _TEST_MODULE_ID,
                SyncStreamRecordModel.stream_id == "default",
            )
        ).scalar_one_or_none()
        assert stream_position in (None, 0)


def test_postgres_concurrent_first_publish_is_race_safe_and_gap_free(postgres_runtime):
    entries, scope, resolver, _, _, publisher, _, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    tx_factory = SqlAlchemyTenantTransactionBoundaryFactory(resolver, scope)

    def publish(index: int) -> int:
        resource_id = uuid4()
        boundary = tx_factory.for_tenant(TenantContext(tenant_id))
        return boundary.run(
            lambda: publisher.publish(
                company_id=company.id,
                module_id=_TEST_MODULE_ID,
                stream_id="race",
                changes=(_change(resource_id, f"v-{index}"),),
            ).position
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        positions = list(pool.map(publish, range(24)))

    assert sorted(positions) == list(range(1, 25))
    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        stored = connection.execute(
            select(SyncBatchRecordModel.position)
            .where(
                SyncBatchRecordModel.company_id == company.id,
                SyncBatchRecordModel.module_id == _TEST_MODULE_ID,
                SyncBatchRecordModel.stream_id == "race",
            )
            .order_by(SyncBatchRecordModel.position)
        ).scalars().all()
        assert list(stored) == list(range(1, 25))
        stream_position = connection.execute(
            select(SyncStreamRecordModel.current_position).where(
                SyncStreamRecordModel.company_id == company.id,
                SyncStreamRecordModel.module_id == _TEST_MODULE_ID,
                SyncStreamRecordModel.stream_id == "race",
            )
        ).scalar_one()
        assert stream_position == 24


def test_postgres_streams_and_companies_advance_independently(postgres_runtime):
    entries, scope, resolver, _, _, publisher, _, companies = postgres_runtime
    tx_factory = SqlAlchemyTenantTransactionBoundaryFactory(resolver, scope)

    work: list[tuple[UUID, UUID, str]] = []
    for tenant_id, _ in entries:
        company = companies[tenant_id]
        work.extend(
            (tenant_id, company.id, stream_id)
            for stream_id in ("default", "secondary")
            for _ in range(5)
        )

    def publish(item: tuple[UUID, UUID, str]) -> tuple[UUID, str, int]:
        tenant_id, company_id, stream_id = item
        resource_id = uuid4()
        position = tx_factory.for_tenant(TenantContext(tenant_id)).run(
            lambda: publisher.publish(
                company_id=company_id,
                module_id=_TEST_MODULE_ID,
                stream_id=stream_id,
                changes=(_change(resource_id, stream_id),),
            ).position
        )
        return company_id, stream_id, position

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(publish, work))

    groups: dict[tuple[UUID, str], list[int]] = {}
    for company_id, stream_id, position in results:
        groups.setdefault((company_id, stream_id), []).append(position)
    assert len(groups) == 4
    for positions in groups.values():
        assert sorted(positions) == [1, 2, 3, 4, 5]
