from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, inspect, select

from app.core.errors.models import PlatformError
from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.milking_admin_repository import SqlAlchemyMilkingAdminRepository
from app.infrastructure.database.milking_models import (
    MilkingAuditEventRecord,
    MilkingOutputRecord,
    MilkingSessionRecord,
)
from app.infrastructure.database.milking_query_repository import SqlAlchemyMilkingQueryRepository
from app.infrastructure.database.milking_repository import SqlAlchemyMilkingRepository
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import SqlAlchemyTenantTransactionBoundaryFactory
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.modules.milking.admin import MilkingAdminService
from app.modules.milking.admin_commands import CreateMilkingConfiguration, CreateOutputProfile
from app.modules.milking.commands import (
    ConfirmMilkingSession,
    CreateMilkingSession,
    SetMilkingGeneral,
    SetMilkingUseDiscard,
)
from app.modules.milking.query import MilkingQueryService
from app.modules.milking.service import MilkingCommandApplicationService
from app.platform.commands.service import CommandExecutionService
from app.platform.company.service import CompanyService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


_TEST_ENV = "O4_TEST_TENANT_DATABASES_JSON"
_CURRENT_TENANT_HEAD = "0005_p5_module_activation"
_ALL_PERMISSIONS = frozenset(
    {
        "milking.session.create",
        "milking.session.update_draft",
        "milking.session.confirm",
        "milking.session.cancel",
        "milking.session.read",
        "milking.config.read",
        "milking.config.manage",
        "milking.output_profile.read",
        "milking.output_profile.manage",
    }
)


def _postgres_entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for real PostgreSQL O-4 tests")
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


def _principal(tenant_id: UUID, company_id: UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        effective_permissions=_ALL_PERMISSIONS,
    )


@pytest.fixture(scope="module")
def o4_postgres_runtime():
    entries = _postgres_entries()
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    runner = TenantMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    provisioner = TenantProvisioner(registry, migration_runner=runner)
    revisions = {
        tenant_id: provisioner.provision(TenantContext(tenant_id))
        for tenant_id, _ in entries
    }
    assert set(revisions.values()) == {_CURRENT_TENANT_HEAD}

    session_scope = TenantSessionScope()
    resolver = SqlAlchemyTenantDataSourceResolver(registry)
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    company_service = CompanyService(
        SqlAlchemyCompanyRepository(session_scope),
        transaction_factory,
    )
    companies = {}
    for tenant_id, _ in entries:
        context = TenantContext(tenant_id)
        primary = company_service.register_company(
            context,
            code=f"O4-A-{uuid4().hex[:10]}",
            legal_name="O-4 Verification Company A",
        )
        secondary = company_service.register_company(
            context,
            code=f"O4-B-{uuid4().hex[:10]}",
            legal_name="O-4 Verification Company B",
        )
        companies[tenant_id] = (primary, secondary)

    command_execution = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(session_scope),
        transaction_factory,
    )
    repository = SqlAlchemyMilkingRepository(session_scope)
    admin_repository = SqlAlchemyMilkingAdminRepository(session_scope)
    query_repository = SqlAlchemyMilkingQueryRepository(session_scope)
    runtime = SimpleNamespace(
        entries=entries,
        resolver=resolver,
        transaction_factory=transaction_factory,
        repository=repository,
        commands=MilkingCommandApplicationService(repository, command_execution),
        admin=MilkingAdminService(
            admin_repository,
            command_execution,
            transaction_factory,
        ),
        query=MilkingQueryService(query_repository, transaction_factory),
        companies=companies,
    )
    try:
        yield runtime
    finally:
        resolver.dispose()


def _seed_configuration(runtime, *, tenant_id: UUID, company_id: UUID, farm_id: UUID):
    principal = _principal(tenant_id, company_id)
    now = datetime.now(UTC)
    profile_outcome = runtime.admin.create_output_profile(
        CreateOutputProfile(
            command_id=uuid4(),
            product_id=uuid4(),
            quantity_uom_id=uuid4(),
            client_occurred_at=now,
            client_instance_id="pytest",
        ),
        principal=principal,
    )
    profile_id = UUID(profile_outcome.result.data["profile_id"])
    runtime.admin.create_configuration(
        CreateMilkingConfiguration(
            command_id=uuid4(),
            farm_id=farm_id,
            shift_code="MORNING",
            output_profile_id=profile_id,
            output_profile_version=1,
            client_occurred_at=now,
            client_instance_id="pytest",
        ),
        principal=principal,
    )
    return principal


def _create_session(
    runtime,
    *,
    principal,
    farm_id: UUID,
    command_id: UUID | None = None,
    client_occurred_at: datetime | None = None,
):
    return runtime.commands.create_session(
        CreateMilkingSession(
            command_id=command_id or uuid4(),
            farm_id=farm_id,
            milking_date=date(2026, 8, 25),
            shift_code="MORNING",
            operator_id=None,
            client_occurred_at=client_occurred_at or datetime.now(UTC),
            client_instance_id="pytest",
        ),
        principal=principal,
    )


def _prepare_confirmable_session(runtime, *, principal, farm_id: UUID, net_zero: bool = False):
    created = _create_session(runtime, principal=principal, farm_id=farm_id)
    session_id = UUID(created.result.data["session_id"])
    general = runtime.commands.set_general(
        SetMilkingGeneral(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=1,
            general_gross_quantity=100,
            animals_milked_count=None,
            client_occurred_at=datetime.now(UTC),
            client_instance_id="pytest",
        ),
        principal=principal,
    )
    assert general.result.data["version"] == 2
    used = 100 if net_zero else 10
    discarded = 0 if net_zero else 5
    reconciled = runtime.commands.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=2,
            used_on_farm_quantity=used,
            discarded_quantity=discarded,
            client_occurred_at=datetime.now(UTC),
            client_instance_id="pytest",
        ),
        principal=principal,
    )
    assert reconciled.result.data["version"] == 3
    return session_id


def _engine(runtime, tenant_id: UUID):
    return runtime.resolver.resolve(TenantContext(tenant_id)).engine


def test_o4_migrates_two_physical_tenant_databases_without_shadow_masters(o4_postgres_runtime):
    for tenant_id, _ in o4_postgres_runtime.entries:
        inspector = inspect(_engine(o4_postgres_runtime, tenant_id))
        tables = set(inspector.get_table_names())
        assert {
            "milking_output_profiles",
            "milking_configurations",
            "milking_sessions",
            "milking_outputs",
            "milking_annulment_requests",
            "milking_audit_events",
            "platform_command_executions",
            "companies",
        } <= tables
        assert {
            "milking_farms",
            "milking_products",
            "milking_uoms",
            "sites",
            "operational_units",
        }.isdisjoint(tables)


@pytest.mark.parametrize("_iteration", range(5))
def test_o4_concurrent_create_same_identity_has_one_winner(o4_postgres_runtime, _iteration):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(
        runtime,
        tenant_id=tenant_id,
        company_id=company_id,
        farm_id=farm_id,
    )

    def invoke(_):
        try:
            outcome = _create_session(runtime, principal=principal, farm_id=farm_id)
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(invoke, range(8)))

    assert outcomes.count("MILKING_SESSION_CREATED") == 1
    assert outcomes.count("ALREADY_EXISTS") == 7
    engine = _engine(runtime, tenant_id)
    with engine.connect() as connection:
        count = connection.scalar(
            select(func.count()).select_from(MilkingSessionRecord).where(
                MilkingSessionRecord.company_id == company_id,
                MilkingSessionRecord.farm_id == farm_id,
                MilkingSessionRecord.milking_date == date(2026, 8, 25),
                MilkingSessionRecord.shift_code == "MORNING",
                MilkingSessionRecord.status != "CANCELLED",
            )
        )
    assert count == 1


def test_o4_same_date_shift_different_farms_are_both_valid(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_a, farm_b = uuid4(), uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_a)
    _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_b)

    first = _create_session(runtime, principal=principal, farm_id=farm_a)
    second = _create_session(runtime, principal=principal, farm_id=farm_b)
    assert first.result.code == second.result.code == "MILKING_SESSION_CREATED"
    assert first.result.data["session_id"] != second.result.data["session_id"]


def test_o4_same_create_command_replays_same_session_without_duplicate_audit(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_id)
    command_id = uuid4()
    occurred_at = datetime.now(UTC)

    first = _create_session(
        runtime,
        principal=principal,
        farm_id=farm_id,
        command_id=command_id,
        client_occurred_at=occurred_at,
    )
    second = _create_session(
        runtime,
        principal=principal,
        farm_id=farm_id,
        command_id=command_id,
        client_occurred_at=occurred_at,
    )

    assert first.replayed is False
    assert second.replayed is True
    assert first.result.data == second.result.data
    session_id = UUID(first.result.data["session_id"])
    engine = _engine(runtime, tenant_id)
    with engine.connect() as connection:
        audit_count = connection.scalar(
            select(func.count()).select_from(MilkingAuditEventRecord).where(
                MilkingAuditEventRecord.session_id == session_id,
                MilkingAuditEventRecord.event_type == "SESSION_CREATED",
            )
        )
    assert audit_count == 1


def test_o4_concurrent_stale_updates_have_one_cas_winner(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_id)
    created = _create_session(runtime, principal=principal, farm_id=farm_id)
    session_id = UUID(created.result.data["session_id"])

    def invoke(quantity: int):
        try:
            outcome = runtime.commands.set_general(
                SetMilkingGeneral(
                    command_id=uuid4(),
                    session_id=session_id,
                    expected_version=1,
                    general_gross_quantity=quantity,
                    animals_milked_count=None,
                    client_occurred_at=datetime.now(UTC),
                    client_instance_id="pytest",
                ),
                principal=principal,
            )
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, (90, 110)))

    assert outcomes.count("MILKING_GENERAL_UPDATED") == 1
    assert outcomes.count("CONCURRENCY_CONFLICT") == 1
    session = runtime.query.get_session(principal=principal, session_id=session_id)
    assert session.version == 2
    assert session.general_gross_quantity in {90, 110}


def test_o4_confirm_replay_creates_exactly_one_output_and_one_business_audit(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_id)
    session_id = _prepare_confirmable_session(runtime, principal=principal, farm_id=farm_id)
    command_id = uuid4()
    command = ConfirmMilkingSession(
        command_id=command_id,
        session_id=session_id,
        expected_version=3,
        client_occurred_at=datetime.now(UTC),
        client_instance_id="pytest",
    )

    first = runtime.commands.confirm(command, principal=principal)
    second = runtime.commands.confirm(command, principal=principal)

    assert first.replayed is False
    assert second.replayed is True
    assert first.result.data == second.result.data
    assert first.result.data["status"] == "DONE"
    assert first.result.data["output_id"] is not None
    engine = _engine(runtime, tenant_id)
    with engine.connect() as connection:
        output_count = connection.scalar(
            select(func.count()).select_from(MilkingOutputRecord).where(
                MilkingOutputRecord.milking_session_id == session_id
            )
        )
        audit_count = connection.scalar(
            select(func.count()).select_from(MilkingAuditEventRecord).where(
                MilkingAuditEventRecord.session_id == session_id,
                MilkingAuditEventRecord.event_type == "SESSION_CONFIRMED",
            )
        )
        command_count = connection.scalar(
            select(func.count()).select_from(CommandExecutionRecordModel).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        )
    assert output_count == 1
    assert audit_count == 1
    assert command_count == 1


def test_o4_zero_net_confirmation_creates_no_output(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_id)
    session_id = _prepare_confirmable_session(
        runtime,
        principal=principal,
        farm_id=farm_id,
        net_zero=True,
    )
    result = runtime.commands.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=3,
            client_occurred_at=datetime.now(UTC),
            client_instance_id="pytest",
        ),
        principal=principal,
    )
    assert result.result.data["status"] == "DONE"
    assert result.result.data["output_id"] is None
    engine = _engine(runtime, tenant_id)
    with engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(MilkingOutputRecord).where(
                MilkingOutputRecord.milking_session_id == session_id
            )
        ) == 0


def test_o4_business_failure_rolls_back_session_audit_and_p4_claim(o4_postgres_runtime, monkeypatch):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_id = runtime.companies[tenant_id][0].id
    farm_id = uuid4()
    principal = _seed_configuration(runtime, tenant_id=tenant_id, company_id=company_id, farm_id=farm_id)
    created = _create_session(runtime, principal=principal, farm_id=farm_id)
    session_id = UUID(created.result.data["session_id"])
    command_id = uuid4()

    original = runtime.repository.insert_audit_event

    def fail_audit(**kwargs):
        raise RuntimeError("forced business audit failure")

    monkeypatch.setattr(runtime.repository, "insert_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="forced business audit failure"):
        runtime.commands.set_general(
            SetMilkingGeneral(
                command_id=command_id,
                session_id=session_id,
                expected_version=1,
                general_gross_quantity=95,
                animals_milked_count=None,
                client_occurred_at=datetime.now(UTC),
                client_instance_id="pytest",
            ),
            principal=principal,
        )
    monkeypatch.setattr(runtime.repository, "insert_audit_event", original)

    session = runtime.query.get_session(principal=principal, session_id=session_id)
    assert session.version == 1
    assert session.general_gross_quantity is None
    engine = _engine(runtime, tenant_id)
    with engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(CommandExecutionRecordModel).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ) == 0
        assert connection.scalar(
            select(func.count()).select_from(MilkingAuditEventRecord).where(
                MilkingAuditEventRecord.session_id == session_id,
                MilkingAuditEventRecord.event_type == "GENERAL_SET",
            )
        ) == 0


def test_o4_same_tenant_other_company_cannot_read_session(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    tenant_id = runtime.entries[0][0]
    company_a, company_b = runtime.companies[tenant_id]
    farm_id = uuid4()
    principal_a = _seed_configuration(
        runtime,
        tenant_id=tenant_id,
        company_id=company_a.id,
        farm_id=farm_id,
    )
    principal_b = _principal(tenant_id, company_b.id)
    created = _create_session(runtime, principal=principal_a, farm_id=farm_id)
    session_id = UUID(created.result.data["session_id"])

    with pytest.raises(PlatformError) as captured:
        runtime.query.get_session(principal=principal_b, session_id=session_id)
    assert captured.value.code == "RESOURCE_NOT_AVAILABLE"


def test_o4_same_command_id_is_physically_isolated_between_tenants(o4_postgres_runtime):
    runtime = o4_postgres_runtime
    command_id = uuid4()
    session_ids = []
    for tenant_id, _ in runtime.entries:
        company_id = runtime.companies[tenant_id][0].id
        farm_id = uuid4()
        principal = _seed_configuration(
            runtime,
            tenant_id=tenant_id,
            company_id=company_id,
            farm_id=farm_id,
        )
        outcome = _create_session(
            runtime,
            principal=principal,
            farm_id=farm_id,
            command_id=command_id,
        )
        assert outcome.replayed is False
        session_ids.append(outcome.result.data["session_id"])

    assert len(set(session_ids)) == 2
    for tenant_id, _ in runtime.entries:
        with _engine(runtime, tenant_id).connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(CommandExecutionRecordModel).where(
                    CommandExecutionRecordModel.command_id == command_id
                )
            ) == 1
