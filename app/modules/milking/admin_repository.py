from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID

from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile


class MilkingAdminRepository(Protocol):
    def get_output_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> MilkingOutputProfile | None: ...

    def latest_output_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
    ) -> MilkingOutputProfile | None: ...

    def list_output_profiles(
        self,
        *,
        company_id: UUID,
        profile_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MilkingOutputProfile]: ...

    def insert_output_profile(self, profile: MilkingOutputProfile) -> None: ...

    def update_output_profile_active(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
        expected_row_version: int,
        is_active: bool,
    ) -> int: ...

    def has_active_configuration_for_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> bool: ...

    def get_configuration_by_id(
        self,
        *,
        company_id: UUID,
        configuration_id: UUID,
    ) -> MilkingConfiguration | None: ...

    def list_configurations(
        self,
        *,
        company_id: UUID,
        farm_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MilkingConfiguration]: ...

    def insert_configuration(self, configuration: MilkingConfiguration) -> None: ...

    def update_configuration(
        self,
        configuration: MilkingConfiguration,
        *,
        expected_version: int,
    ) -> int: ...
