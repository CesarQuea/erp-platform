from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.milking_admin_repository import SqlAlchemyMilkingAdminRepository
from app.infrastructure.database.milking_query_repository import SqlAlchemyMilkingQueryRepository
from app.infrastructure.database.milking_repository import SqlAlchemyMilkingRepository
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
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


_TEST_ENV = "P5_TEST_TENANT_DATABASES_JSON"
_P5_HEAD = "0005_p5_module_activation"
_MILKING_PERMISSIONS = frozenset(
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
        pytest.skip(f"{_TEST_ENV} is required for P-5/O-4 PostgreSQL regression")
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            return UUID(str(raw_tenant_id)), url
    pytest.skip(f"{_TEST_ENV} must contain a PostgreSQL Tenant DB")


def test_o4_milking_command_flow_remains_operational_on_p5_schema():
    tenant_id, url = _entry()
    tenant_registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, url)}
    )
    provisioner = TenantProvisioner(
        tenant_registry,
        migration_runner=TenantMigrationRunner(
            repository_root=Path(__file__).resolve().parents[1],
            target_revision=_P5_HEAD,
        ),
    )
    assert provisioner.provision(TenantContext(tenant_id)) == _P5_HEAD

    session_scope = TenantSessionScope()
    resolver = SqlAlchemyTenantDataSourceResolver(tenant_registry)
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    command_execution = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(session_scope),
        transaction_factory,
    )
    company_service = CompanyService(
        SqlAlchemyCompanyRepository(session_scope),
        transaction_factory,
    )
    repository = SqlAlchemyMilkingRepository(session_scope)
    admin = MilkingAdminService(
        SqlAlchemyMilkingAdminRepository(session_scope),
        command_execution,
        transaction_factory,
    )
    commands = MilkingCommandApplicationService(repository, command_execution)
    query = MilkingQueryService(
        SqlAlchemyMilkingQueryRepository(session_scope),
        transaction_factory,
    )

    try:
        company = company_service.register_company(
            TenantContext(tenant_id),
            code=f"P5-O4-{uuid4().hex[:10]}",
            legal_name="P-5 O-4 Regression Company",
        )
        principal = AuthenticatedPrincipal(
            user_id=uuid4(),
            session_id=uuid4(),
            tenant_id=tenant_id,
            company_id=company.id,
            effective_permissions=_MILKING_PERMISSIONS,
        )
        farm_id = uuid4()
        occurred_at = datetime.now(UTC)

        profile = admin.create_output_profile(
            CreateOutputProfile(
                command_id=uuid4(),
                product_id=uuid4(),
                quantity_uom_id=uuid4(),
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )
        profile_id = UUID(profile.result.data["profile_id"])
        admin.create_configuration(
            CreateMilkingConfiguration(
                command_id=uuid4(),
                farm_id=farm_id,
                shift_code="MORNING",
                output_profile_id=profile_id,
                output_profile_version=1,
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )

        created = commands.create_session(
            CreateMilkingSession(
                command_id=uuid4(),
                farm_id=farm_id,
                milking_date=date(2026, 8, 26),
                shift_code="MORNING",
                operator_id=None,
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )
        session_id = UUID(created.result.data["session_id"])
        general = commands.set_general(
            SetMilkingGeneral(
                command_id=uuid4(),
                session_id=session_id,
                expected_version=1,
                general_gross_quantity=100,
                animals_milked_count=25,
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )
        assert general.result.data["version"] == 2
        reconciled = commands.set_use_discard(
            SetMilkingUseDiscard(
                command_id=uuid4(),
                session_id=session_id,
                expected_version=2,
                used_on_farm_quantity=10,
                discarded_quantity=5,
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )
        assert reconciled.result.data["version"] == 3
        confirmed = commands.confirm(
            ConfirmMilkingSession(
                command_id=uuid4(),
                session_id=session_id,
                expected_version=3,
                client_occurred_at=occurred_at,
                client_instance_id="p5-regression",
            ),
            principal=principal,
        )
        assert confirmed.result.data["status"] == "DONE"
        assert confirmed.result.data["output_id"] is not None

        stored = query.get_session(principal=principal, session_id=session_id)
        assert stored.status.value == "DONE"
        assert stored.version == 4
    finally:
        resolver.dispose()
