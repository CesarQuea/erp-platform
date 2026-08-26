from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.milking_models import MilkingOutputRecord
from app.infrastructure.database.milking_repository import SqlAlchemyMilkingRepository
from app.modules.milking.domain import MilkingOutput


class SqlAlchemyMilkingQueryRepository(SqlAlchemyMilkingRepository):
    def get_output_by_id(
        self,
        *,
        company_id: UUID,
        output_id: UUID,
    ) -> MilkingOutput | None:
        row = self._session_scope.current().scalar(
            select(MilkingOutputRecord).where(
                MilkingOutputRecord.company_id == company_id,
                MilkingOutputRecord.id == output_id,
            )
        )
        return None if row is None else self._output_from_record(row)
