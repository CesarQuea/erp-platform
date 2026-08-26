from __future__ import annotations

from datetime import datetime
from uuid import UUID


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("client_occurred_at must be timezone-aware")


def _require_expected_version(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("expected_version must be a positive integer")


class CreateOutputProfile:
    def __init__(
        self,
        *,
        command_id: UUID,
        product_id: UUID,
        quantity_uom_id: UUID,
        client_occurred_at: datetime,
        client_instance_id: str | None = None,
    ) -> None:
        _require_aware(client_occurred_at)
        self.command_id = command_id
        self.product_id = product_id
        self.quantity_uom_id = quantity_uom_id
        self.client_occurred_at = client_occurred_at
        self.client_instance_id = client_instance_id


class CreateOutputProfileVersion:
    def __init__(
        self,
        *,
        command_id: UUID,
        profile_id: UUID,
        product_id: UUID,
        quantity_uom_id: UUID,
        client_occurred_at: datetime,
        client_instance_id: str | None = None,
    ) -> None:
        _require_aware(client_occurred_at)
        self.command_id = command_id
        self.profile_id = profile_id
        self.product_id = product_id
        self.quantity_uom_id = quantity_uom_id
        self.client_occurred_at = client_occurred_at
        self.client_instance_id = client_instance_id


class SetOutputProfileActive:
    def __init__(
        self,
        *,
        command_id: UUID,
        profile_id: UUID,
        profile_version: int,
        expected_version: int,
        is_active: bool,
        client_occurred_at: datetime,
        client_instance_id: str | None = None,
    ) -> None:
        _require_expected_version(expected_version)
        _require_aware(client_occurred_at)
        self.command_id = command_id
        self.profile_id = profile_id
        self.profile_version = profile_version
        self.expected_version = expected_version
        self.is_active = is_active
        self.client_occurred_at = client_occurred_at
        self.client_instance_id = client_instance_id


class CreateMilkingConfiguration:
    def __init__(
        self,
        *,
        command_id: UUID,
        farm_id: UUID,
        shift_code: str,
        output_profile_id: UUID,
        output_profile_version: int,
        client_occurred_at: datetime,
        client_instance_id: str | None = None,
    ) -> None:
        if not shift_code.strip():
            raise ValueError("shift_code cannot be blank")
        if output_profile_version <= 0:
            raise ValueError("output_profile_version must be positive")
        _require_aware(client_occurred_at)
        self.command_id = command_id
        self.farm_id = farm_id
        self.shift_code = shift_code.strip()
        self.output_profile_id = output_profile_id
        self.output_profile_version = output_profile_version
        self.client_occurred_at = client_occurred_at
        self.client_instance_id = client_instance_id


class UpdateMilkingConfiguration:
    def __init__(
        self,
        *,
        command_id: UUID,
        configuration_id: UUID,
        expected_version: int,
        output_profile_id: UUID | None,
        output_profile_version: int | None,
        is_active: bool | None,
        client_occurred_at: datetime,
        client_instance_id: str | None = None,
    ) -> None:
        _require_expected_version(expected_version)
        if output_profile_version is not None and output_profile_version <= 0:
            raise ValueError("output_profile_version must be positive")
        if (output_profile_id is None) != (output_profile_version is None):
            raise ValueError("output_profile_id and output_profile_version must be changed together")
        if output_profile_id is None and is_active is None:
            raise ValueError("configuration update has no changes")
        _require_aware(client_occurred_at)
        self.command_id = command_id
        self.configuration_id = configuration_id
        self.expected_version = expected_version
        self.output_profile_id = output_profile_id
        self.output_profile_version = output_profile_version
        self.is_active = is_active
        self.client_occurred_at = client_occurred_at
        self.client_instance_id = client_instance_id
