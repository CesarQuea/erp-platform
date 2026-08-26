from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Protocol, Sequence
from uuid import UUID

from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.domain import MilkingOutput, MilkingSession


@dataclass(frozen=True, slots=True)
class MilkingRepositoryConflict(RuntimeError):
    code: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.code)


class MilkingRepository(Protocol):
    def get_output_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> MilkingOutputProfile | None: ...

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

    def get_configuration(
        self,
        *,
        company_id: UUID,
        farm_id: UUID,
        shift_code: str,
    ) -> MilkingConfiguration | None: ...

    def get_configuration_by_id(
        self,
        *,
        company_id: UUID,
        configuration_id: UUID,
    ) -> MilkingConfiguration | None: ...

    def insert_configuration(self, configuration: MilkingConfiguration) -> None: ...

    def update_configuration(
        self,
        configuration: MilkingConfiguration,
        *,
        expected_version: int,
    ) -> int: ...

    def get_session(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
        for_update: bool = False,
    ) -> MilkingSession | None: ...

    def find_active_session_by_identity(
        self,
        *,
        company_id: UUID,
        farm_id: UUID,
        milking_date: date,
        shift_code: str,
    ) -> MilkingSession | None: ...

    def insert_session(self, session: MilkingSession) -> None: ...

    def update_session(
        self,
        session: MilkingSession,
        *,
        expected_version: int,
    ) -> int: ...

    def get_output_for_session(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
    ) -> MilkingOutput | None: ...

    def insert_output(self, output: MilkingOutput) -> None: ...

    def has_pending_annulment(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
    ) -> bool: ...

    def insert_annulment_request(
        self,
        *,
        request_id: UUID,
        company_id: UUID,
        session_id: UUID,
        reason: str,
        requested_by: UUID,
        client_occurred_at: datetime,
        recorded_at: datetime,
    ) -> None: ...

    def insert_audit_event(
        self,
        *,
        event_id: UUID,
        company_id: UUID,
        session_id: UUID,
        command_id: UUID,
        event_type: str,
        version_before: int | None,
        version_after: int | None,
        actor_user_id: UUID,
        client_occurred_at: datetime,
        recorded_at: datetime,
        change_payload: Mapping[str, object],
    ) -> None: ...

    def list_sessions(
        self,
        *,
        company_id: UUID,
        farm_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        shift_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MilkingSession]: ...

    def list_outputs(
        self,
        *,
        company_id: UUID,
        farm_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MilkingOutput]: ...
