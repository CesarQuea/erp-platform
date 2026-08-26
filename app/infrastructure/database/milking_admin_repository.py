from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.milking_models import (
    MilkingConfigurationRecord,
    MilkingOutputProfileRecord,
)
from app.infrastructure.database.milking_repository import SqlAlchemyMilkingRepository
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile


class SqlAlchemyMilkingAdminRepository(SqlAlchemyMilkingRepository):
    def latest_output_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
    ) -> MilkingOutputProfile | None:
        row = self._session_scope.current().scalar(
            select(MilkingOutputProfileRecord)
            .where(
                MilkingOutputProfileRecord.company_id == company_id,
                MilkingOutputProfileRecord.profile_id == profile_id,
            )
            .order_by(MilkingOutputProfileRecord.profile_version.desc())
            .limit(1)
        )
        return None if row is None else self._profile_from_record(row)

    def list_output_profiles(
        self,
        *,
        company_id: UUID,
        profile_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingOutputProfile, ...]:
        statement = select(MilkingOutputProfileRecord).where(
            MilkingOutputProfileRecord.company_id == company_id
        )
        if profile_id is not None:
            statement = statement.where(MilkingOutputProfileRecord.profile_id == profile_id)
        if active is not None:
            statement = statement.where(MilkingOutputProfileRecord.is_active == active)
        rows = self._session_scope.current().scalars(
            statement.order_by(
                MilkingOutputProfileRecord.profile_id.asc(),
                MilkingOutputProfileRecord.profile_version.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return tuple(self._profile_from_record(row) for row in rows)

    def has_active_configuration_for_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> bool:
        configuration_id = self._session_scope.current().scalar(
            select(MilkingConfigurationRecord.id).where(
                MilkingConfigurationRecord.company_id == company_id,
                MilkingConfigurationRecord.output_profile_id == profile_id,
                MilkingConfigurationRecord.output_profile_version == profile_version,
                MilkingConfigurationRecord.is_active.is_(True),
            ).limit(1)
        )
        return configuration_id is not None

    def list_configurations(
        self,
        *,
        company_id: UUID,
        farm_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingConfiguration, ...]:
        statement = select(MilkingConfigurationRecord).where(
            MilkingConfigurationRecord.company_id == company_id
        )
        if farm_id is not None:
            statement = statement.where(MilkingConfigurationRecord.farm_id == farm_id)
        if active is not None:
            statement = statement.where(MilkingConfigurationRecord.is_active == active)
        rows = self._session_scope.current().scalars(
            statement.order_by(
                MilkingConfigurationRecord.farm_id.asc(),
                MilkingConfigurationRecord.shift_code.asc(),
                MilkingConfigurationRecord.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return tuple(self._configuration_from_record(row) for row in rows)
