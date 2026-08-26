from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.errors.models import PlatformError
from app.modules.milking.admin import (
    MilkingAdminService,
    PERM_CONFIG_MANAGE,
    PERM_CONFIG_READ,
    PERM_PROFILE_MANAGE,
    PERM_PROFILE_READ,
)
from app.modules.milking.admin_commands import (
    CreateMilkingConfiguration,
    CreateOutputProfile,
    CreateOutputProfileVersion,
    SetOutputProfileActive,
    UpdateMilkingConfiguration,
)
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.platform.commands.model import CommandExecutionOutcome
from app.platform.identity.model import AuthenticatedPrincipal


NOW = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
ALL_ADMIN = {
    PERM_PROFILE_READ,
    PERM_PROFILE_MANAGE,
    PERM_CONFIG_READ,
    PERM_CONFIG_MANAGE,
}


class FixedClock:
    def now(self):
        return NOW


class DirectCommandExecution:
    def execute(self, request, payload, *, authorize, operation):
        authorize()
        return CommandExecutionOutcome(operation(), replayed=False)


class DirectBoundary:
    def run(self, operation):
        return operation()


class DirectTransactionFactory:
    def for_tenant(self, context):
        return DirectBoundary()


class FakeAdminRepository:
    def __init__(self) -> None:
        self.profiles: dict[tuple[UUID, int], MilkingOutputProfile] = {}
        self.configurations: dict[UUID, MilkingConfiguration] = {}

    def get_output_profile(self, *, company_id, profile_id, profile_version):
        value = self.profiles.get((profile_id, profile_version))
        return value if value is not None and value.company_id == company_id else None

    def latest_output_profile(self, *, company_id, profile_id):
        values = [
            value
            for (candidate_id, _), value in self.profiles.items()
            if candidate_id == profile_id and value.company_id == company_id
        ]
        return max(values, key=lambda value: value.profile_version) if values else None

    def list_output_profiles(self, *, company_id, profile_id=None, active=None, limit=100, offset=0):
        values = [value for value in self.profiles.values() if value.company_id == company_id]
        if profile_id is not None:
            values = [value for value in values if value.profile_id == profile_id]
        if active is not None:
            values = [value for value in values if value.is_active == active]
        values.sort(key=lambda value: (str(value.profile_id), -value.profile_version))
        return tuple(values[offset : offset + limit])

    def insert_output_profile(self, profile):
        key = (profile.profile_id, profile.profile_version)
        if key in self.profiles:
            raise AssertionError("duplicate profile version")
        self.profiles[key] = profile

    def update_output_profile_active(
        self,
        *,
        company_id,
        profile_id,
        profile_version,
        expected_row_version,
        is_active,
    ):
        current = self.get_output_profile(
            company_id=company_id,
            profile_id=profile_id,
            profile_version=profile_version,
        )
        if current is None or current.row_version != expected_row_version:
            raise AssertionError("fake CAS conflict")
        changed = current.with_active(
            active=is_active,
            expected_row_version=expected_row_version,
        )
        self.profiles[(profile_id, profile_version)] = changed
        return changed.row_version

    def has_active_configuration_for_profile(
        self,
        *,
        company_id,
        profile_id,
        profile_version,
    ):
        return any(
            value.company_id == company_id
            and value.output_profile_id == profile_id
            and value.output_profile_version == profile_version
            and value.is_active
            for value in self.configurations.values()
        )

    def get_configuration_by_id(self, *, company_id, configuration_id):
        value = self.configurations.get(configuration_id)
        return value if value is not None and value.company_id == company_id else None

    def list_configurations(self, *, company_id, farm_id=None, active=None, limit=100, offset=0):
        values = [
            value for value in self.configurations.values() if value.company_id == company_id
        ]
        if farm_id is not None:
            values = [value for value in values if value.farm_id == farm_id]
        if active is not None:
            values = [value for value in values if value.is_active == active]
        values.sort(key=lambda value: (str(value.farm_id), value.shift_code, str(value.id)))
        return tuple(values[offset : offset + limit])

    def insert_configuration(self, configuration):
        if any(
            value.company_id == configuration.company_id
            and value.farm_id == configuration.farm_id
            and value.shift_code == configuration.shift_code
            for value in self.configurations.values()
        ):
            raise AssertionError("duplicate configuration")
        self.configurations[configuration.id] = configuration

    def update_configuration(self, configuration, *, expected_version):
        current = self.configurations.get(configuration.id)
        if current is None or current.version != expected_version:
            raise AssertionError("fake CAS conflict")
        self.configurations[configuration.id] = configuration
        return configuration.version


def principal(company_id: UUID, permissions=ALL_ADMIN) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        company_id=company_id,
        effective_permissions=frozenset(permissions),
    )


def service(repo: FakeAdminRepository) -> MilkingAdminService:
    return MilkingAdminService(
        repo,
        DirectCommandExecution(),
        DirectTransactionFactory(),
        clock=FixedClock(),
    )


def create_profile(app, actor, *, product_id=None, uom_id=None):
    return app.create_output_profile(
        CreateOutputProfile(
            command_id=uuid4(),
            product_id=product_id or uuid4(),
            quantity_uom_id=uom_id or uuid4(),
            client_occurred_at=NOW,
        ),
        principal=actor,
    )


def test_output_profile_is_versioned_without_mutating_previous_version() -> None:
    company_id = uuid4()
    repo = FakeAdminRepository()
    actor = principal(company_id)
    app = service(repo)
    product_v1, uom_v1 = uuid4(), uuid4()
    first = create_profile(app, actor, product_id=product_v1, uom_id=uom_v1)
    profile_id = UUID(first.result.data["profile_id"])
    product_v2, uom_v2 = uuid4(), uuid4()

    second = app.create_output_profile_version(
        CreateOutputProfileVersion(
            command_id=uuid4(),
            profile_id=profile_id,
            product_id=product_v2,
            quantity_uom_id=uom_v2,
            client_occurred_at=NOW,
        ),
        principal=actor,
    )

    assert second.result.data["profile_version"] == 2
    assert repo.profiles[(profile_id, 1)].product_id == product_v1
    assert repo.profiles[(profile_id, 1)].quantity_uom_id == uom_v1
    assert repo.profiles[(profile_id, 2)].product_id == product_v2
    assert repo.profiles[(profile_id, 2)].quantity_uom_id == uom_v2


def test_configuration_can_move_to_new_profile_version_and_increments_version() -> None:
    company_id = uuid4()
    farm_id = uuid4()
    repo = FakeAdminRepository()
    actor = principal(company_id)
    app = service(repo)
    first = create_profile(app, actor)
    profile_id = UUID(first.result.data["profile_id"])
    app.create_output_profile_version(
        CreateOutputProfileVersion(
            command_id=uuid4(),
            profile_id=profile_id,
            product_id=uuid4(),
            quantity_uom_id=uuid4(),
            client_occurred_at=NOW,
        ),
        principal=actor,
    )
    created = app.create_configuration(
        CreateMilkingConfiguration(
            command_id=uuid4(),
            farm_id=farm_id,
            shift_code="MORNING",
            output_profile_id=profile_id,
            output_profile_version=1,
            client_occurred_at=NOW,
        ),
        principal=actor,
    )
    configuration_id = UUID(created.result.data["configuration_id"])

    updated = app.update_configuration(
        UpdateMilkingConfiguration(
            command_id=uuid4(),
            configuration_id=configuration_id,
            expected_version=1,
            output_profile_id=profile_id,
            output_profile_version=2,
            is_active=None,
            client_occurred_at=NOW,
        ),
        principal=actor,
    )

    assert updated.result.data["version"] == 2
    assert repo.configurations[configuration_id].output_profile_version == 2
    assert repo.configurations[configuration_id].farm_id == farm_id
    assert repo.configurations[configuration_id].shift_code == "MORNING"


def test_active_configuration_prevents_deactivating_its_output_profile() -> None:
    company_id = uuid4()
    repo = FakeAdminRepository()
    actor = principal(company_id)
    app = service(repo)
    created_profile = create_profile(app, actor)
    profile_id = UUID(created_profile.result.data["profile_id"])
    app.create_configuration(
        CreateMilkingConfiguration(
            command_id=uuid4(),
            farm_id=uuid4(),
            shift_code="MORNING",
            output_profile_id=profile_id,
            output_profile_version=1,
            client_occurred_at=NOW,
        ),
        principal=actor,
    )

    with pytest.raises(PlatformError) as captured:
        app.set_output_profile_active(
            SetOutputProfileActive(
                command_id=uuid4(),
                profile_id=profile_id,
                profile_version=1,
                expected_version=1,
                is_active=False,
                client_occurred_at=NOW,
            ),
            principal=actor,
        )

    assert captured.value.code == "BUSINESS_CONFLICT"
    assert repo.profiles[(profile_id, 1)].is_active is True


def test_admin_read_and_manage_permissions_are_independent() -> None:
    company_id = uuid4()
    repo = FakeAdminRepository()
    read_only = principal(company_id, {PERM_PROFILE_READ, PERM_CONFIG_READ})
    app = service(repo)

    assert app.list_output_profiles(principal=read_only) == ()
    assert app.list_configurations(principal=read_only) == ()
    with pytest.raises(PlatformError) as captured:
        create_profile(app, read_only)
    assert captured.value.code == "ACCESS_DENIED"
