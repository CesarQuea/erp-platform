from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence
from uuid import UUID

from app.modules.milking.domain import MilkingOutput, MilkingSession


class MilkingQueryRepository(Protocol):
    def get_session(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
        for_update: bool = False,
    ) -> MilkingSession | None: ...

    def get_output_by_id(
        self,
        *,
        company_id: UUID,
        output_id: UUID,
    ) -> MilkingOutput | None: ...

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
