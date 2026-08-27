from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.errors.models import PlatformError
from app.platform.commands.errors import ConcurrencyConflictSignal
from app.platform.commands.model import CommandExecutionRecord
from app.platform.commands.service import CommandExecutionService
from app.platform.company.model import Company
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.model import (
    ChangeModuleActivation,
    CompanyModuleActivation,
    ModuleActivationState,
    ModuleDefinition,
)
from app.platform.modules.registry import ModuleRegistry
from app.platform.modules.service import (
    PERM_MANAGE_MODULES,
    ModuleActivationService,
    ModuleAvailabilityService,
)
from app.platform.tenancy.context import TenantContext


class FixedClock:
    def now(self):
        return datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)


class MemoryCommandRepository:
    def __init__(self):
        self.records: dict[UUID, CommandExecutionRecord] = {}

    def claim(self, record: CommandExecutionRecord) -> bool:
        if record.command_id in self.records:
            return False
        self.records[record.command_id] = record
        return True

    def get(self, command_id: UUID):
        return self.records.get(command_id)

    def complete(self, command_id, *, result_code, result_json, committed_at):
        old = self.records[command_id]
        self.records[command_id] = CommandExecutionRecord(
            command_id=old.command_id,
            command_name=old.command_name,
            command_schema_version=old.command_schema_version,
            scope=old.scope,
            company_id=old.company_id,
            actor_user_id=old.actor_user_id,
            fingerprint=old.fingerprint,
            result_code=result_code,
            result_json=dict(result_json),
            committed_at=committed_at,
        )


class MemoryActivationRepository:
    def __init__(self):
        self.records: dict[tuple[UUID, str], CompanyModuleActivation] = {}

    def get(self, *, company_id: UUID, module_id: str):
        return self.records.get((company_id, module_id))

    def list_for_company(self, company_id: UUID):
        return tuple(
            activation
            for (stored_company_id, _), activation in sorted(
                self.records.items(), key=lambda item: item[0][1]
            )
            if stored_company_id == company_id
        )

    def insert(self, activation: CompanyModuleActivation) -> None:
        key = (activation.company_id, activation.module_id)
        if key in self.records:
            raise ConcurrencyConflictSignal()
        self.records[key] = activation

    def update_state(
        self,
        *,
        company_id,
        module_id,
        expected_version,
        state,
        updated_at,
        updated_by,
    ):
        key = (company_id, module_id)
        current = self.records.get(key)
        if current is None or current.version != expected_version:
            raise ConcurrencyConflictSignal()
        changed = CompanyModuleActivation(
            company_id=current.company_id,
            module_id=current.module_id,
            state=state,
            version=current.version + 1,
            created_at=current.created_at,
            created_by=current.created_by,
            updated_at=updated_at,
            updated_by=updated_by,
        )
        self.records[key] = changed
        return changed


class MemoryCompanyRepository:
    def __init__(self, companies: list[Company]):
        self.companies = {company.id: company for company in companies}

    def get_by_id(self, company_id: UUID):
        return self.companies.get(company_id)

    def list_all(self):
        return tuple(self.companies.values())

    def add(self, company):
        self.companies[company.id] = company


class SnapshotBoundary:
    def __init__(self, command_repo, activation_repo):
        self.command_repo = command_repo
        self.activation_repo = activation_repo

    def run(self, operation):
        command_snapshot = deepcopy(self.command_repo.records)
        activation_snapshot = deepcopy(self.activation_repo.records)
        try:
            return operation()
        except Exception:
            self.command_repo.records = command_snapshot
            self.activation_repo.records = activation_snapshot
            raise


class BoundaryFactory:
    def __init__(self, command_repo, activation_repo):
        self.command_repo = command_repo
        self.activation_repo = activation_repo

    def for_tenant(self, context):
        return SnapshotBoundary(self.command_repo, self.activation_repo)


def company(company_id: UUID, *, active: bool = True) -> Company:
    now = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
    return Company(
        id=company_id,
        code=f"C-{str(company_id)[:8]}",
        legal_name="Test Company",
        is_active=active,
        created_at=now,
        updated_at=now,
    )


def principal(tenant_id: UUID, company_id: UUID, *, allowed: bool = True):
    permissions = frozenset({PERM_MANAGE_MODULES}) if allowed else frozenset()
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        effective_permissions=permissions,
    )


def services(*, active_company: bool = True):
    tenant_id, company_id = uuid4(), uuid4()
    registry = ModuleRegistry(
        [ModuleDefinition("milking", "1.0.0", "milking", "Milking")]
    )
    registry.freeze()
    command_repo = MemoryCommandRepository()
    activation_repo = MemoryActivationRepository()
    company_repo = MemoryCompanyRepository([company(company_id, active=active_company)])
    boundaries = BoundaryFactory(command_repo, activation_repo)
    commands = CommandExecutionService(command_repo, boundaries, clock=FixedClock())
    availability = ModuleAvailabilityService(
        registry,
        activation_repo,
        company_repo,
        boundaries,
    )
    activations = ModuleActivationService(
        registry,
        activation_repo,
        company_repo,
        commands,
        clock=FixedClock(),
    )
    return (
        tenant_id,
        company_id,
        command_repo,
        activation_repo,
        availability,
        activations,
    )


def test_absent_activation_is_disabled_version_zero_without_persisting_row():
    tenant_id, company_id, _, activation_repo, availability, activations = services()
    ctx = TenantContext(tenant_id)
    p = principal(tenant_id, company_id)

    assert availability.get_activation(ctx, company_id, "milking") is None
    assert not availability.is_enabled(ctx, company_id, "milking")
    status = availability.list_company_modules(ctx, company_id)[0]
    assert status.state is ModuleActivationState.DISABLED
    assert status.version == 0
    assert not status.activation_present
    assert not status.effective_enabled

    outcome = activations.disable_module(
        ChangeModuleActivation(uuid4(), "milking", 0),
        principal=p,
    )
    assert outcome.result.code == "MODULE_ACTIVATION_UNCHANGED"
    assert outcome.result.data["version"] == 0
    assert activation_repo.records == {}


def test_enable_disable_reenable_versions_only_effective_changes():
    tenant_id, company_id, _, _, availability, activations = services()
    p = principal(tenant_id, company_id)
    ctx = TenantContext(tenant_id)

    enabled = activations.enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0), principal=p
    )
    assert enabled.result.data == {
        "module_id": "milking",
        "state": "ENABLED",
        "version": 1,
        "changed": True,
    }
    assert availability.is_enabled(ctx, company_id, "milking")

    noop = activations.enable_module(
        ChangeModuleActivation(uuid4(), "milking", 1), principal=p
    )
    assert noop.result.code == "MODULE_ACTIVATION_UNCHANGED"
    assert noop.result.data["version"] == 1

    disabled = activations.disable_module(
        ChangeModuleActivation(uuid4(), "milking", 1), principal=p
    )
    assert disabled.result.data["state"] == "DISABLED"
    assert disabled.result.data["version"] == 2
    assert not availability.is_enabled(ctx, company_id, "milking")

    reenabled = activations.enable_module(
        ChangeModuleActivation(uuid4(), "milking", 2), principal=p
    )
    assert reenabled.result.data["state"] == "ENABLED"
    assert reenabled.result.data["version"] == 3


def test_same_enable_command_replays_without_second_effect():
    tenant_id, company_id, _, activation_repo, _, activations = services()
    p = principal(tenant_id, company_id)
    command = ChangeModuleActivation(uuid4(), "milking", 0)

    first = activations.enable_module(command, principal=p)
    replay = activations.enable_module(command, principal=p)

    assert not first.replayed
    assert replay.replayed
    assert replay.result == first.result
    assert activation_repo.records[(company_id, "milking")].version == 1


def test_same_command_id_with_different_target_state_is_idempotency_conflict():
    tenant_id, company_id, _, _, _, activations = services()
    p = principal(tenant_id, company_id)
    command_id = uuid4()
    activations.enable_module(
        ChangeModuleActivation(command_id, "milking", 0), principal=p
    )
    with pytest.raises(PlatformError) as exc:
        activations.disable_module(
            ChangeModuleActivation(command_id, "milking", 1), principal=p
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_stale_expected_version_is_concurrency_conflict():
    tenant_id, company_id, _, _, _, activations = services()
    p = principal(tenant_id, company_id)
    activations.enable_module(
        ChangeModuleActivation(uuid4(), "milking", 0), principal=p
    )
    with pytest.raises(PlatformError) as exc:
        activations.disable_module(
            ChangeModuleActivation(uuid4(), "milking", 0), principal=p
        )
    assert exc.value.code == "CONCURRENCY_CONFLICT"


def test_unknown_module_fails_closed_before_command_claim():
    tenant_id, company_id, command_repo, _, availability, activations = services()
    p = principal(tenant_id, company_id)
    assert not availability.is_registered("inventory")
    with pytest.raises(PlatformError) as exc:
        availability.is_enabled(TenantContext(tenant_id), company_id, "inventory")
    assert exc.value.code == "MODULE_NOT_REGISTERED"

    with pytest.raises(PlatformError) as exc:
        activations.enable_module(
            ChangeModuleActivation(uuid4(), "inventory", 0), principal=p
        )
    assert exc.value.code == "MODULE_NOT_REGISTERED"
    assert command_repo.records == {}


def test_orphan_activation_fails_closed_when_listing_company_modules():
    tenant_id, company_id, _, activation_repo, availability, _ = services()
    actor = uuid4()
    activation_repo.records[(company_id, "inventory")] = CompanyModuleActivation(
        company_id=company_id,
        module_id="inventory",
        state=ModuleActivationState.ENABLED,
        version=1,
        created_at=datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
        created_by=actor,
    )
    with pytest.raises(PlatformError) as exc:
        availability.list_company_modules(TenantContext(tenant_id), company_id)
    assert exc.value.code == "MODULE_NOT_REGISTERED"


def test_permission_is_independent_from_company_module_activation():
    tenant_id, company_id, command_repo, _, _, activations = services()
    denied = principal(tenant_id, company_id, allowed=False)
    with pytest.raises(PlatformError) as exc:
        activations.enable_module(
            ChangeModuleActivation(uuid4(), "milking", 0), principal=denied
        )
    assert exc.value.code == "ACCESS_DENIED"
    assert command_repo.records == {}


def test_inactive_company_rejects_activation_and_rolls_back_command_claim():
    tenant_id, company_id, command_repo, activation_repo, availability, activations = services(
        active_company=False
    )
    p = principal(tenant_id, company_id)
    assert not availability.is_enabled(TenantContext(tenant_id), company_id, "milking")

    with pytest.raises(PlatformError) as exc:
        activations.enable_module(
            ChangeModuleActivation(uuid4(), "milking", 0), principal=p
        )
    assert exc.value.code == "MODULE_ACTIVATION_NOT_AVAILABLE"
    assert command_repo.records == {}
    assert activation_repo.records == {}


def test_require_enabled_distinguishes_not_registered_from_not_enabled():
    tenant_id, company_id, _, _, availability, _ = services()
    ctx = TenantContext(tenant_id)
    with pytest.raises(PlatformError) as exc:
        availability.require_enabled(ctx, company_id, "milking")
    assert exc.value.code == "MODULE_NOT_ENABLED"

    with pytest.raises(PlatformError) as exc:
        availability.require_enabled(ctx, company_id, "inventory")
    assert exc.value.code == "MODULE_NOT_REGISTERED"
