from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, Uuid, delete, insert, select

from app.core.errors.models import PlatformError
from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.concurrency import SqlAlchemyCompareAndSet
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import SqlAlchemyTenantTransactionBoundaryFactory
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.commands.model import CommandRequest, CommandResult, CommandScope
from app.platform.commands.service import CommandExecutionService
from app.platform.company.service import CompanyService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


_TEST_ENV = "P4_TEST_TENANT_DATABASES_JSON"


def _postgres_entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for real PostgreSQL P-4 tests")
    parsed = json.loads(raw)
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in parsed.items():
        url = config["database_url"]
        if not (
            url.startswith("postgresql://")
            or url.startswith("postgres://")
            or url.startswith("postgresql+psycopg://")
        ):
            continue
        entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain at least two PostgreSQL tenant databases")
    return entries[:2]


@pytest.fixture
def postgres_runtime():
    entries = _postgres_entries()
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    runner = TenantMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    provisioner = TenantProvisioner(registry, migration_runner=runner)
    for tenant_id, _ in entries:
        assert provisioner.provision(TenantContext(tenant_id)) == "0002_p4_command_execution"

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
    cas = SqlAlchemyCompareAndSet(scope)

    metadata = MetaData()
    resource = Table(
        "p4_verification_resource",
        metadata,
        Column("id", Uuid(), primary_key=True),
        Column("value", String(64), nullable=False),
        Column("version", Integer, nullable=False),
    )
    companies = {}
    for tenant_id, _ in entries:
        context = TenantContext(tenant_id)
        engine = resolver.resolve(context).engine
        resource.create(engine, checkfirst=True)
        with engine.begin() as connection:
            connection.execute(delete(resource))
        companies[tenant_id] = company_service.register_company(
            context,
            code=f"P4-{uuid4().hex[:10]}",
            legal_name="P-4 Verification Company",
        )

    try:
        yield entries, scope, resolver, command_service, cas, resource, companies
    finally:
        for tenant_id, _ in entries:
            engine = resolver.resolve(TenantContext(tenant_id)).engine
            resource.drop(engine, checkfirst=True)
        resolver.dispose()


def _principal(tenant_id: UUID, company_id: UUID, user_id: UUID | None = None):
    return AuthenticatedPrincipal(
        user_id=user_id or uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
    )


@pytest.mark.parametrize("_iteration", range(5))
def test_postgres_concurrent_retries_same_command_have_exactly_one_effect(
    postgres_runtime,
    _iteration,
):
    entries, scope, resolver, service, _, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    command_id, resource_id = uuid4(), uuid4()
    request = CommandRequest(command_id, "p4.concurrent.create", "1", CommandScope.COMPANY)

    def operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(resource).values(id=resource_id, value="once", version=0)
        )
        time.sleep(0.15)
        return CommandResult("CREATED", {"id": str(resource_id)})

    def invoke():
        return service.execute(
            request,
            {"id": resource_id},
            authorize=lambda: principal,
            operation=operation,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: invoke(), range(8)))

    assert sum(not outcome.replayed for outcome in outcomes) == 1
    assert sum(outcome.replayed for outcome in outcomes) == 7
    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        rows = connection.execute(
            select(resource).where(resource.c.id == resource_id)
        ).all()
        assert len(rows) == 1
        command = connection.execute(
            select(CommandExecutionRecordModel).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ).one()
        assert command.result_code == "CREATED"
        assert command.committed_at is not None


def test_postgres_concurrent_same_command_different_fingerprint_conflicts(postgres_runtime):
    entries, scope, resolver, service, _, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    command_id, resource_id = uuid4(), uuid4()
    request = CommandRequest(command_id, "p4.concurrent.conflict", "1", CommandScope.COMPANY)

    def invoke(value: str):
        def operation():
            scope.current(expected_tenant_id=tenant_id).execute(
                insert(resource).values(id=resource_id, value=value, version=0)
            )
            time.sleep(0.1)
            return CommandResult("CREATED", {"id": str(resource_id), "value": value})

        try:
            outcome = service.execute(
                request,
                {"id": resource_id, "value": value},
                authorize=lambda: principal,
                operation=operation,
            )
            return "REPLAY" if outcome.replayed else "SUCCEEDED"
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, ("intent-a", "intent-b")))

    assert sorted(outcomes) == ["IDEMPOTENCY_CONFLICT", "SUCCEEDED"]
    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        rows = connection.execute(
            select(resource).where(resource.c.id == resource_id)
        ).mappings().all()
        assert len(rows) == 1
        assert rows[0]["value"] in {"intent-a", "intent-b"}


def test_postgres_failed_transaction_removes_claim_and_allows_retry(postgres_runtime):
    entries, scope, resolver, service, _, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    command_id, resource_id = uuid4(), uuid4()
    request = CommandRequest(command_id, "p4.rollback.create", "1", CommandScope.COMPANY)

    def failing_operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(resource).values(id=resource_id, value="rolled-back", version=0)
        )
        raise RuntimeError("forced rollback")

    with pytest.raises(RuntimeError):
        service.execute(
            request,
            {"id": resource_id},
            authorize=lambda: principal,
            operation=failing_operation,
        )

    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        assert connection.execute(
            select(resource).where(resource.c.id == resource_id)
        ).all() == []
        assert connection.execute(
            select(CommandExecutionRecordModel).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ).all() == []

    def successful_operation():
        scope.current(expected_tenant_id=tenant_id).execute(
            insert(resource).values(id=resource_id, value="committed", version=0)
        )
        return CommandResult("CREATED", {"id": str(resource_id)})

    outcome = service.execute(
        request,
        {"id": resource_id},
        authorize=lambda: principal,
        operation=successful_operation,
    )
    assert not outcome.replayed


def test_postgres_cas_allows_one_writer_and_rejects_stale_writer(postgres_runtime):
    entries, scope, resolver, service, cas, resource, companies = postgres_runtime
    tenant_id = entries[0][0]
    company = companies[tenant_id]
    principal = _principal(tenant_id, company.id)
    resource_id = uuid4()
    engine = resolver.resolve(TenantContext(tenant_id)).engine
    with engine.begin() as connection:
        connection.execute(insert(resource).values(id=resource_id, value="initial", version=0))

    def invoke(value: str):
        request = CommandRequest(
            uuid4(),
            "p4.concurrent.update",
            "1",
            CommandScope.COMPANY,
            expected_version=0,
        )

        def operation():
            new_version = cas.update_versioned(
                resource,
                identity_column=resource.c.id,
                identity_value=resource_id,
                version_column=resource.c.version,
                expected_version=0,
                values={"value": value},
            )
            return CommandResult("UPDATED", {"version": new_version})

        try:
            service.execute(
                request,
                {"value": value},
                authorize=lambda: principal,
                operation=operation,
            )
            return "SUCCEEDED"
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, ("writer-a", "writer-b")))

    assert sorted(outcomes) == ["CONCURRENCY_CONFLICT", "SUCCEEDED"]
    with engine.connect() as connection:
        row = connection.execute(
            select(resource).where(resource.c.id == resource_id)
        ).mappings().one()
        assert row["version"] == 1
        assert row["value"] in {"writer-a", "writer-b"}


def test_same_command_id_is_physically_isolated_between_tenants(postgres_runtime):
    entries, scope, resolver, service, _, resource, companies = postgres_runtime
    command_id = uuid4()
    user_id = uuid4()
    results = []

    for tenant_id, _ in entries:
        company = companies[tenant_id]
        principal = _principal(tenant_id, company.id, user_id=user_id)
        resource_id = uuid4()
        request = CommandRequest(command_id, "p4.isolation.create", "1", CommandScope.COMPANY)

        def operation(resource_id=resource_id, tenant_id=tenant_id):
            scope.current(expected_tenant_id=tenant_id).execute(
                insert(resource).values(id=resource_id, value="isolated", version=0)
            )
            return CommandResult("CREATED", {"id": str(resource_id)})

        results.append(
            service.execute(
                request,
                {"id": resource_id},
                authorize=lambda principal=principal: principal,
                operation=operation,
            )
        )

    assert all(not result.replayed for result in results)
    for tenant_id, _ in entries:
        engine = resolver.resolve(TenantContext(tenant_id)).engine
        with engine.connect() as connection:
            count = connection.execute(
                select(CommandExecutionRecordModel.command_id).where(
                    CommandExecutionRecordModel.command_id == command_id
                )
            ).all()
            assert len(count) == 1
