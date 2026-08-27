from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select

from app.core.errors.models import PlatformError
from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.module_repository import SqlAlchemyModuleActivationRepository
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.modules.milking.module import MILKING_MODULE_DEFINITION
from app.platform.commands.service import CommandExecutionService
from app.platform.company.service import CompanyService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.model import ChangeModuleActivation
from app.platform.modules.registry import ModuleRegistry
from app.platform.modules.service import (
    PERM_MANAGE_MODULES,
    ModuleActivationService,
    ModuleAvailabilityService,
)
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


_TEST_ENV = "P5_TEST_TENANT_DATABASES_JSON"
_P5_HEAD = "0005_p5_module_activation"


def _postgres_entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for real PostgreSQL P-5 tests")
    parsed = json.loads(raw)
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in parsed.items():
        url = config["database_url"]
        if not url.startswith(
            ("postgresql://", "postgres://", "postgresql+psycopg://")
        ):
            continue
        entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain two dedicated PostgreSQL Tenant DBs")
    return entries[:2]


def _principal(tenant_id: UUID, company_id: UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        effective_permissions=frozenset({PERM_MANAGE_MODULES}),
    )


@pytest.fixture(scope="module")
def p5_runtime():
    entries = _postgres_entries()
    tenant_registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    runner = TenantMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    provisioner = TenantProvisioner(tenant_registry, migration_runner=runner)
    for tenant_id, _ in entries:
        assert provisioner.provision(TenantContext(tenant_id)) == _P5_HEAD

    session_scope = TenantSessionScope()
    resolver = SqlAlchemyTenantDataSourceResolver(tenant_registry)
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    company_repository = SqlAlchemyCompanyRepository(session_scope)
    company_service = CompanyService(company_repository, transaction_factory)
    activation_repository = SqlAlchemyModuleActivationRepository(session_scope)
    command_service = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(session_scope),
        transaction_factory,
    )
    registry = ModuleRegistry([MILKING_MODULE_DEFINITION])
    registry.freeze()
    availability = ModuleAvailabilityService(
        registry,
        activation_repository,
        company_repository,
        transaction_factory,
    )
    activations = ModuleActivationService(
        registry,
        activation_repository,
        company_repository,
        command_service,
    )

    def create_company(tenant_id: UUID, label: str):
        return company_service.register_company(
            TenantContext(tenant_id),
            code=f"P5-{label}-{uuid4().hex[:10]}",
            legal_name=f"P-5 {label}",
        )

    try:
        yield {
            "entries": entries,
            "resolver": resolver,
            "scope": session_scope,
            "transactions": transaction_factory,
            "company_repository": company_repository,
            "company_service": company_service,
            "activation_repository": activation_repository,
            "command_service": command_service,
            "registry": registry,
            "availability": availability,
            "activations": activations,
            "create_company": create_company,
        }
    finally:
        resolver.dispose()


def test_p5_schema_exists_with_pk_fk_and_checks_on_each_tenant(p5_runtime):
    for tenant_id, _ in p5_runtime["entries"]:
        engine = p5_runtime["resolver"].resolve(TenantContext(tenant_id)).engine
        inspector = inspect(engine)
        assert "platform_module_activations" in inspector.get_table_names()
        columns = {
            column["name"]
            for column in inspector.get_columns("platform_module_activations")
        }
        assert columns == {
            "company_id",
            "module_id",
            "state",
            "version",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        }
        pk = inspector.get_pk_constraint("platform_module_activations")
        assert pk["constrained_columns"] == ["company_id", "module_id"]
        fks = inspector.get_foreign_keys("platform_module_activations")
        assert any(
            fk["constrained_columns"] == ["company_id"]
            and fk["referred_table"] == "companies"
            and fk["referred_columns"] == ["id"]
            for fk in fks
        )
        checks = {
            check["name"]
            for check in inspector.get_check_constraints("platform_module_activations")
        }
        assert {
            "ck_module_activation_state",
            "ck_module_activation_version_positive",
            "ck_module_activation_module_id_required",
        } <= checks


def test_company_scoped_activation_isolated_within_tenant(p5_runtime):
    tenant_id = p5_runtime["entries"][0][0]
    company_a = p5_runtime["create_company"](tenant_id, "COMPANY-A")
    company_b = p5_runtime["create_company"](tenant_id, "COMPANY-B")
    principal_a = _principal(tenant_id, company_a.id)

    p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0),
        principal=principal_a,
    )

    assert p5_runtime["availability"].is_enabled(
        TenantContext(tenant_id), company_a.id, "milking"
    )
    assert not p5_runtime["availability"].is_enabled(
        TenantContext(tenant_id), company_b.id, "milking"
    )


def test_activation_lifecycle_is_v1_v2_v3_and_noop_does_not_increment(p5_runtime):
    tenant_id = p5_runtime["entries"][0][0]
    company = p5_runtime["create_company"](tenant_id, "LIFECYCLE")
    principal = _principal(tenant_id, company.id)

    enabled = p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0), principal=principal
    )
    assert enabled.result.data["version"] == 1

    noop = p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 1), principal=principal
    )
    assert noop.result.data["version"] == 1
    assert noop.result.data["changed"] is False

    disabled = p5_runtime["activations"].disable_module(
        ChangeModuleActivation(uuid4(), "milking", 1), principal=principal
    )
    assert disabled.result.data["version"] == 2

    reenabled = p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 2), principal=principal
    )
    assert reenabled.result.data["version"] == 3


def test_p4_replay_and_fingerprint_conflict_apply_to_module_activation(p5_runtime):
    tenant_id = p5_runtime["entries"][0][0]
    company = p5_runtime["create_company"](tenant_id, "IDEMPOTENCY")
    principal = _principal(tenant_id, company.id)
    command_id = uuid4()
    command = ChangeModuleActivation(command_id, "milking", 0)

    first = p5_runtime["activations"].enable_module(command, principal=principal)
    replay = p5_runtime["activations"].enable_module(command, principal=principal)
    assert not first.replayed
    assert replay.replayed
    assert first.result == replay.result

    with pytest.raises(PlatformError) as exc:
        p5_runtime["activations"].disable_module(
            ChangeModuleActivation(command_id, "milking", 1), principal=principal
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("_iteration", range(5))
def test_concurrent_first_enable_has_one_winner(p5_runtime, _iteration):
    tenant_id = p5_runtime["entries"][0][0]
    company = p5_runtime["create_company"](tenant_id, f"FIRST-{_iteration}")
    principal = _principal(tenant_id, company.id)

    def invoke(_):
        try:
            outcome = p5_runtime["activations"].enable_module(
                ChangeModuleActivation(uuid4(), "milking", 0),
                principal=principal,
            )
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(invoke, range(8)))

    assert outcomes.count("MODULE_ACTIVATION_CHANGED") == 1
    assert outcomes.count("CONCURRENCY_CONFLICT") == 7
    activation = p5_runtime["availability"].get_activation(
        TenantContext(tenant_id), company.id, "milking"
    )
    assert activation is not None
    assert activation.version == 1


def test_concurrent_changes_with_same_expected_version_have_one_cas_winner(p5_runtime):
    tenant_id = p5_runtime["entries"][0][0]
    company = p5_runtime["create_company"](tenant_id, "CAS")
    principal = _principal(tenant_id, company.id)
    p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0), principal=principal
    )

    def invoke(_):
        try:
            outcome = p5_runtime["activations"].disable_module(
                ChangeModuleActivation(uuid4(), "milking", 1),
                principal=principal,
            )
            return outcome.result.code
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, range(2)))

    assert outcomes.count("MODULE_ACTIVATION_CHANGED") == 1
    assert outcomes.count("CONCURRENCY_CONFLICT") == 1
    activation = p5_runtime["availability"].get_activation(
        TenantContext(tenant_id), company.id, "milking"
    )
    assert activation is not None
    assert activation.state.value == "DISABLED"
    assert activation.version == 2


def test_module_activation_is_physically_isolated_between_tenants(p5_runtime):
    tenant_a = p5_runtime["entries"][0][0]
    tenant_b = p5_runtime["entries"][1][0]
    company_a = p5_runtime["create_company"](tenant_a, "TENANT-A")
    company_b = p5_runtime["create_company"](tenant_b, "TENANT-B")

    p5_runtime["activations"].enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0),
        principal=_principal(tenant_a, company_a.id),
    )

    assert p5_runtime["availability"].is_enabled(
        TenantContext(tenant_a), company_a.id, "milking"
    )
    assert not p5_runtime["availability"].is_enabled(
        TenantContext(tenant_b), company_b.id, "milking"
    )


class FailingAfterInsertRepository(SqlAlchemyModuleActivationRepository):
    def insert(self, activation):
        super().insert(activation)
        raise RuntimeError("forced failure after activation insert")


def test_failed_activation_rolls_back_business_row_and_p4_claim(p5_runtime):
    tenant_id = p5_runtime["entries"][0][0]
    company = p5_runtime["create_company"](tenant_id, "ROLLBACK")
    principal = _principal(tenant_id, company.id)
    command_id = uuid4()
    scope = p5_runtime["scope"]
    transaction_factory = p5_runtime["transactions"]
    failing_repository = FailingAfterInsertRepository(scope)
    failing_service = ModuleActivationService(
        p5_runtime["registry"],
        failing_repository,
        p5_runtime["company_repository"],
        p5_runtime["command_service"],
    )

    with pytest.raises(RuntimeError):
        failing_service.enable_module(
            ChangeModuleActivation(command_id, "milking", 0),
            principal=principal,
        )

    assert p5_runtime["availability"].get_activation(
        TenantContext(tenant_id), company.id, "milking"
    ) is None
    engine = p5_runtime["resolver"].resolve(TenantContext(tenant_id)).engine
    with engine.connect() as connection:
        assert connection.execute(
            select(CommandExecutionRecordModel.command_id).where(
                CommandExecutionRecordModel.command_id == command_id
            )
        ).all() == []
