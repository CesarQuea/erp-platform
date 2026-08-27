from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.bootstrap.milking_platform import build_milking_platform
from app.bootstrap.tenant_platform import TenantPlatformRuntime
from app.core.errors.models import PlatformError
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.milking_models import (
    MilkingAnnulmentRequestRecord,
    MilkingAuditEventRecord,
    MilkingOutputRecord,
)
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import SqlAlchemyTenantTransactionBoundaryFactory
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.modules.milking.admin_commands import (
    CreateMilkingConfiguration,
    CreateOutputProfile,
    UpdateMilkingConfiguration,
)
from app.modules.milking.commands import (
    CancelDraftMilkingSession,
    ConfirmMilkingSession,
    CreateMilkingSession,
    RequestMilkingAnnulment,
    SetMilkingGeneral,
    SetMilkingUseDiscard,
)
from app.platform.company.service import CompanyService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


_TEST_ENV = "O4_TEST_TENANT_DATABASES_JSON"
_CURRENT_TENANT_HEAD = "0005_p5_module_activation"
_PERMISSIONS = frozenset(
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


def _entry() -> tuple[UUID, str]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for real PostgreSQL O-4 tests")
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            return UUID(str(raw_tenant_id)), url
    pytest.skip(f"{_TEST_ENV} contains no PostgreSQL tenant database")


@pytest.fixture(scope="module")
def race_runtime():
    tenant_id, url = _entry()
    registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, url)}
    )
    provisioner = TenantProvisioner(
        registry,
        migration_runner=TenantMigrationRunner(
            repository_root=Path(__file__).resolve().parents[1]
        ),
    )
    assert provisioner.provision(TenantContext(tenant_id)) == _CURRENT_TENANT_HEAD

    resolver = SqlAlchemyTenantDataSourceResolver(registry)
    company_scope = TenantSessionScope()
    company_tx = SqlAlchemyTenantTransactionBoundaryFactory(resolver, company_scope)
    company_service = CompanyService(
        SqlAlchemyCompanyRepository(company_scope),
        company_tx,
    )
    company = company_service.register_company(
        TenantContext(tenant_id),
        code=f"O4-RACE-{uuid4().hex[:10]}",
        legal_name="O-4 Race Verification Company",
    )
    tenant_runtime = TenantPlatformRuntime(
        registry=registry,
        resolver=resolver,
        provisioner=provisioner,
        company_service=company_service,
    )
    milking = build_milking_platform(tenant_runtime)
    assert milking is not None
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company.id,
        effective_permissions=_PERMISSIONS,
    )
    try:
        yield tenant_id, company, principal, tenant_runtime, milking
    finally:
        tenant_runtime.dispose()


def _seed(milking, principal, farm_id: UUID):
    now = datetime.now(UTC)
    profile = milking.admin.create_output_profile(
        CreateOutputProfile(
            command_id=uuid4(),
            product_id=uuid4(),
            quantity_uom_id=uuid4(),
            client_occurred_at=now,
        ),
        principal=principal,
    )
    profile_id = UUID(profile.result.data["profile_id"])
    configuration = milking.admin.create_configuration(
        CreateMilkingConfiguration(
            command_id=uuid4(),
            farm_id=farm_id,
            shift_code="MORNING",
            output_profile_id=profile_id,
            output_profile_version=1,
            client_occurred_at=now,
        ),
        principal=principal,
    )
    return profile_id, UUID(configuration.result.data["configuration_id"])


def _draft(milking, principal, farm_id: UUID):
    created = milking.commands.create_session(
        CreateMilkingSession(
            command_id=uuid4(),
            farm_id=farm_id,
            milking_date=date(2026, 8, 26),
            shift_code="MORNING",
            operator_id=None,
            client_occurred_at=datetime.now(UTC),
        ),
        principal=principal,
    )
    return UUID(created.result.data["session_id"])


def _confirmable(milking, principal, farm_id: UUID):
    session_id = _draft(milking, principal, farm_id)
    milking.commands.set_general(
        SetMilkingGeneral(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=1,
            general_gross_quantity=100,
            animals_milked_count=None,
            client_occurred_at=datetime.now(UTC),
        ),
        principal=principal,
    )
    milking.commands.set_use_discard(
        SetMilkingUseDiscard(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=2,
            used_on_farm_quantity=10,
            discarded_quantity=5,
            client_occurred_at=datetime.now(UTC),
        ),
        principal=principal,
    )
    return session_id


def _engine(tenant_runtime, tenant_id):
    return tenant_runtime.resolver.resolve(TenantContext(tenant_id)).engine


def test_confirm_vs_cancel_race_allows_one_transition(race_runtime):
    tenant_id, _, principal, tenant_runtime, milking = race_runtime
    farm_id = uuid4()
    _seed(milking, principal, farm_id)
    session_id = _confirmable(milking, principal, farm_id)

    def confirm():
        try:
            value = milking.commands.confirm(
                ConfirmMilkingSession(
                    command_id=uuid4(),
                    session_id=session_id,
                    expected_version=3,
                    client_occurred_at=datetime.now(UTC),
                ),
                principal=principal,
            )
            return value.result.code
        except PlatformError as error:
            return error.code

    def cancel():
        try:
            value = milking.commands.cancel_draft(
                CancelDraftMilkingSession(
                    command_id=uuid4(),
                    session_id=session_id,
                    expected_version=3,
                    reason="Concurrent correction",
                    client_occurred_at=datetime.now(UTC),
                ),
                principal=principal,
            )
            return value.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_confirm = pool.submit(confirm)
        future_cancel = pool.submit(cancel)
        outcomes = [future_confirm.result(), future_cancel.result()]

    success_codes = {"MILKING_SESSION_CONFIRMED", "MILKING_DRAFT_CANCELLED"}
    assert sum(outcome in success_codes for outcome in outcomes) == 1
    assert sum(outcome in {"CONCURRENCY_CONFLICT", "STATE_CONFLICT"} for outcome in outcomes) == 1
    session = milking.query.get_session(principal=principal, session_id=session_id)
    assert session.version == 4
    assert session.status.value in {"DONE", "CANCELLED"}

    with _engine(tenant_runtime, tenant_id).connect() as connection:
        output_count = connection.scalar(
            select(func.count()).select_from(MilkingOutputRecord).where(
                MilkingOutputRecord.milking_session_id == session_id
            )
        )
        transition_audits = connection.scalar(
            select(func.count()).select_from(MilkingAuditEventRecord).where(
                MilkingAuditEventRecord.session_id == session_id,
                MilkingAuditEventRecord.event_type.in_(
                    ["SESSION_CONFIRMED", "DRAFT_CANCELLED"]
                ),
            )
        )
    assert transition_audits == 1
    assert output_count == (1 if session.status.value == "DONE" else 0)


def test_cancelled_draft_releases_operational_identity(race_runtime):
    _, _, principal, _, milking = race_runtime
    farm_id = uuid4()
    _seed(milking, principal, farm_id)
    first_id = _draft(milking, principal, farm_id)
    cancelled = milking.commands.cancel_draft(
        CancelDraftMilkingSession(
            command_id=uuid4(),
            session_id=first_id,
            expected_version=1,
            reason="Restart capture",
            client_occurred_at=datetime.now(UTC),
        ),
        principal=principal,
    )
    assert cancelled.result.data["status"] == "CANCELLED"

    second_id = _draft(milking, principal, farm_id)
    assert second_id != first_id


def test_concurrent_annulment_with_output_creates_one_pending_request(race_runtime):
    tenant_id, _, principal, tenant_runtime, milking = race_runtime
    farm_id = uuid4()
    _seed(milking, principal, farm_id)
    session_id = _confirmable(milking, principal, farm_id)
    confirmed = milking.commands.confirm(
        ConfirmMilkingSession(
            command_id=uuid4(),
            session_id=session_id,
            expected_version=3,
            client_occurred_at=datetime.now(UTC),
        ),
        principal=principal,
    )
    assert confirmed.result.data["version"] == 4

    def invoke(index: int):
        try:
            outcome = milking.commands.request_annulment(
                RequestMilkingAnnulment(
                    command_id=uuid4(),
                    session_id=session_id,
                    expected_version=4,
                    reason=f"Concurrent annulment {index}",
                    client_occurred_at=datetime.now(UTC),
                ),
                principal=principal,
            )
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, (1, 2)))

    assert outcomes.count("MILKING_ANNULMENT_REQUESTED") == 1
    assert outcomes.count("BUSINESS_CONFLICT") == 1
    session = milking.query.get_session(principal=principal, session_id=session_id)
    assert session.status.value == "DONE"
    assert session.version == 4
    with _engine(tenant_runtime, tenant_id).connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(MilkingAnnulmentRequestRecord).where(
                MilkingAnnulmentRequestRecord.milking_session_id == session_id,
                MilkingAnnulmentRequestRecord.state == "PENDING",
            )
        ) == 1


def test_configuration_concurrent_updates_use_cas(race_runtime):
    _, _, principal, _, milking = race_runtime
    farm_id = uuid4()
    _, configuration_id = _seed(milking, principal, farm_id)

    def invoke(active: bool):
        try:
            outcome = milking.admin.update_configuration(
                UpdateMilkingConfiguration(
                    command_id=uuid4(),
                    configuration_id=configuration_id,
                    expected_version=1,
                    output_profile_id=None,
                    output_profile_version=None,
                    is_active=active,
                    client_occurred_at=datetime.now(UTC),
                ),
                principal=principal,
            )
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, (False, True)))

    assert outcomes.count("MILKING_CONFIGURATION_UPDATED") == 1
    assert sum(code in {"CONCURRENCY_CONFLICT", "VERSION_CONFLICT"} for code in outcomes) == 1
    configurations = milking.admin.list_configurations(
        principal=principal,
        farm_id=farm_id,
    )
    assert len(configurations) == 1
    assert configurations[0].version == 2
