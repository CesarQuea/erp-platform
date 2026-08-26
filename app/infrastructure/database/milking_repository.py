from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.concurrency import SqlAlchemyCompareAndSet
from app.infrastructure.database.milking_models import (
    MilkingAnnulmentRequestRecord,
    MilkingAuditEventRecord,
    MilkingConfigurationRecord,
    MilkingOutputProfileRecord,
    MilkingOutputRecord,
    MilkingSessionRecord,
)
from app.infrastructure.database.session_scope import TenantSessionScope
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.domain import (
    MilkingOutput,
    MilkingReconciliationStatus,
    MilkingSession,
    MilkingSessionStatus,
    MilkingTotalSource,
)
from app.modules.milking.repository import MilkingRepositoryConflict
from app.platform.commands.errors import ConcurrencyConflictSignal


_CONSTRAINT_CONFLICTS = {
    "uq_milking_session_active_identity": "SESSION_ALREADY_EXISTS",
    "uq_milking_output_session": "OUTPUT_ALREADY_EXISTS",
    "uq_milking_configuration_company_farm_shift": "CONFIGURATION_ALREADY_EXISTS",
    "uq_milking_annulment_pending_session": "ANNULMENT_ALREADY_PENDING",
    "milking_output_profiles_pkey": "OUTPUT_PROFILE_ALREADY_EXISTS",
}


class SqlAlchemyMilkingRepository:
    def __init__(self, session_scope: TenantSessionScope) -> None:
        self._session_scope = session_scope
        self._cas = SqlAlchemyCompareAndSet(session_scope)

    def get_output_profile(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> MilkingOutputProfile | None:
        row = self._session_scope.current().scalar(
            select(MilkingOutputProfileRecord).where(
                MilkingOutputProfileRecord.company_id == company_id,
                MilkingOutputProfileRecord.profile_id == profile_id,
                MilkingOutputProfileRecord.profile_version == profile_version,
            )
        )
        return None if row is None else self._profile_from_record(row)

    def insert_output_profile(self, profile: MilkingOutputProfile) -> None:
        row = MilkingOutputProfileRecord(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            company_id=profile.company_id,
            product_id=profile.product_id,
            quantity_uom_id=profile.quantity_uom_id,
            is_active=profile.is_active,
            row_version=profile.row_version,
            created_at=profile.created_at,
            created_by=profile.created_by,
        )
        self._add_with_conflict_mapping(row)

    def update_output_profile_active(
        self,
        *,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
        expected_row_version: int,
        is_active: bool,
    ) -> int:
        result = self._session_scope.current().execute(
            update(MilkingOutputProfileRecord)
            .where(
                MilkingOutputProfileRecord.company_id == company_id,
                MilkingOutputProfileRecord.profile_id == profile_id,
                MilkingOutputProfileRecord.profile_version == profile_version,
                MilkingOutputProfileRecord.row_version == expected_row_version,
            )
            .values(
                is_active=is_active,
                row_version=MilkingOutputProfileRecord.row_version + 1,
            )
            .returning(MilkingOutputProfileRecord.row_version)
        )
        new_version = result.scalar_one_or_none()
        if new_version is None:
            raise ConcurrencyConflictSignal()
        return int(new_version)

    def get_configuration(
        self,
        *,
        company_id: UUID,
        farm_id: UUID,
        shift_code: str,
    ) -> MilkingConfiguration | None:
        row = self._session_scope.current().scalar(
            select(MilkingConfigurationRecord).where(
                MilkingConfigurationRecord.company_id == company_id,
                MilkingConfigurationRecord.farm_id == farm_id,
                MilkingConfigurationRecord.shift_code == shift_code,
            )
        )
        return None if row is None else self._configuration_from_record(row)

    def get_configuration_by_id(
        self,
        *,
        company_id: UUID,
        configuration_id: UUID,
    ) -> MilkingConfiguration | None:
        row = self._session_scope.current().scalar(
            select(MilkingConfigurationRecord).where(
                MilkingConfigurationRecord.company_id == company_id,
                MilkingConfigurationRecord.id == configuration_id,
            )
        )
        return None if row is None else self._configuration_from_record(row)

    def insert_configuration(self, configuration: MilkingConfiguration) -> None:
        row = MilkingConfigurationRecord(
            id=configuration.id,
            company_id=configuration.company_id,
            farm_id=configuration.farm_id,
            shift_code=configuration.shift_code,
            output_profile_id=configuration.output_profile_id,
            output_profile_version=configuration.output_profile_version,
            is_active=configuration.is_active,
            version=configuration.version,
            created_at=configuration.created_at,
            created_by=configuration.created_by,
            updated_at=configuration.updated_at,
            updated_by=configuration.updated_by,
        )
        self._add_with_conflict_mapping(row)

    def update_configuration(
        self,
        configuration: MilkingConfiguration,
        *,
        expected_version: int,
    ) -> int:
        current = self.get_configuration_by_id(
            company_id=configuration.company_id,
            configuration_id=configuration.id,
        )
        if current is None:
            raise ConcurrencyConflictSignal()
        new_version = self._cas.update_versioned(
            MilkingConfigurationRecord.__table__,
            identity_column=MilkingConfigurationRecord.id,
            identity_value=configuration.id,
            version_column=MilkingConfigurationRecord.version,
            expected_version=expected_version,
            values={
                "output_profile_id": configuration.output_profile_id,
                "output_profile_version": configuration.output_profile_version,
                "is_active": configuration.is_active,
                "updated_at": configuration.updated_at,
                "updated_by": configuration.updated_by,
            },
        )
        if new_version != configuration.version:
            raise RuntimeError("Milking configuration domain/database version diverged")
        return new_version

    def get_session(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
        for_update: bool = False,
    ) -> MilkingSession | None:
        statement = select(MilkingSessionRecord).where(
            MilkingSessionRecord.company_id == company_id,
            MilkingSessionRecord.id == session_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session_scope.current().scalar(statement)
        return None if row is None else self._session_from_record(row)

    def find_active_session_by_identity(
        self,
        *,
        company_id: UUID,
        farm_id: UUID,
        milking_date: date,
        shift_code: str,
    ) -> MilkingSession | None:
        row = self._session_scope.current().scalar(
            select(MilkingSessionRecord).where(
                MilkingSessionRecord.company_id == company_id,
                MilkingSessionRecord.farm_id == farm_id,
                MilkingSessionRecord.milking_date == milking_date,
                MilkingSessionRecord.shift_code == shift_code,
                MilkingSessionRecord.status != MilkingSessionStatus.CANCELLED.value,
            )
        )
        return None if row is None else self._session_from_record(row)

    def insert_session(self, milking_session: MilkingSession) -> None:
        row = MilkingSessionRecord(
            id=milking_session.id,
            company_id=milking_session.company_id,
            farm_id=milking_session.farm_id,
            milking_date=milking_session.milking_date,
            shift_code=milking_session.shift_code,
            operator_id=milking_session.operator_id,
            status=milking_session.status.value,
            animals_milked_count=milking_session.animals_milked_count,
            general_gross_quantity=milking_session.general_gross_quantity,
            quantity_uom_id=milking_session.quantity_uom_id,
            authoritative_gross_quantity=milking_session.authoritative_gross_quantity,
            authoritative_total_source=(
                milking_session.authoritative_total_source.value
                if milking_session.authoritative_total_source is not None
                else None
            ),
            used_on_farm_quantity=milking_session.used_on_farm_quantity,
            discarded_quantity=milking_session.discarded_quantity,
            net_output_quantity=milking_session.net_output_quantity,
            reconciliation_status=milking_session.reconciliation_status.value,
            output_profile_id=milking_session.output_profile_id,
            output_profile_version=milking_session.output_profile_version,
            product_id=milking_session.product_id,
            notes=milking_session.notes,
            version=milking_session.version,
            created_at=milking_session.created_at,
            created_by=milking_session.created_by,
            updated_at=milking_session.updated_at,
            updated_by=milking_session.updated_by,
            confirmed_at=milking_session.confirmed_at,
            confirmed_by=milking_session.confirmed_by,
            cancelled_at=milking_session.cancelled_at,
            cancelled_by=milking_session.cancelled_by,
            cancel_reason=milking_session.cancel_reason,
        )
        self._add_with_conflict_mapping(row)

    def update_session(
        self,
        milking_session: MilkingSession,
        *,
        expected_version: int,
    ) -> int:
        current = self.get_session(
            company_id=milking_session.company_id,
            session_id=milking_session.id,
        )
        if current is None:
            raise ConcurrencyConflictSignal()
        new_version = self._cas.update_versioned(
            MilkingSessionRecord.__table__,
            identity_column=MilkingSessionRecord.id,
            identity_value=milking_session.id,
            version_column=MilkingSessionRecord.version,
            expected_version=expected_version,
            values={
                "status": milking_session.status.value,
                "animals_milked_count": milking_session.animals_milked_count,
                "general_gross_quantity": milking_session.general_gross_quantity,
                "authoritative_gross_quantity": milking_session.authoritative_gross_quantity,
                "authoritative_total_source": (
                    milking_session.authoritative_total_source.value
                    if milking_session.authoritative_total_source is not None
                    else None
                ),
                "used_on_farm_quantity": milking_session.used_on_farm_quantity,
                "discarded_quantity": milking_session.discarded_quantity,
                "net_output_quantity": milking_session.net_output_quantity,
                "reconciliation_status": milking_session.reconciliation_status.value,
                "notes": milking_session.notes,
                "updated_at": milking_session.updated_at,
                "updated_by": milking_session.updated_by,
                "confirmed_at": milking_session.confirmed_at,
                "confirmed_by": milking_session.confirmed_by,
                "cancelled_at": milking_session.cancelled_at,
                "cancelled_by": milking_session.cancelled_by,
                "cancel_reason": milking_session.cancel_reason,
            },
        )
        if new_version != milking_session.version:
            raise RuntimeError("Milking session domain/database version diverged")
        return new_version

    def get_output_for_session(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
    ) -> MilkingOutput | None:
        row = self._session_scope.current().scalar(
            select(MilkingOutputRecord).where(
                MilkingOutputRecord.company_id == company_id,
                MilkingOutputRecord.milking_session_id == session_id,
            )
        )
        return None if row is None else self._output_from_record(row)

    def insert_output(self, output: MilkingOutput) -> None:
        row = MilkingOutputRecord(
            id=output.id,
            company_id=output.company_id,
            milking_session_id=output.milking_session_id,
            farm_id=output.farm_id,
            product_id=output.product_id,
            quantity=output.quantity,
            uom_id=output.uom_id,
            production_date=output.production_date,
            created_at=output.created_at,
            created_by=output.created_by,
        )
        self._add_with_conflict_mapping(row)

    def has_pending_annulment(
        self,
        *,
        company_id: UUID,
        session_id: UUID,
    ) -> bool:
        request_id = self._session_scope.current().scalar(
            select(MilkingAnnulmentRequestRecord.id).where(
                MilkingAnnulmentRequestRecord.company_id == company_id,
                MilkingAnnulmentRequestRecord.milking_session_id == session_id,
                MilkingAnnulmentRequestRecord.state == "PENDING",
            )
        )
        return request_id is not None

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
    ) -> None:
        row = MilkingAnnulmentRequestRecord(
            id=request_id,
            company_id=company_id,
            milking_session_id=session_id,
            reason=reason,
            requested_by=requested_by,
            client_occurred_at=client_occurred_at,
            recorded_at=recorded_at,
            state="PENDING",
        )
        self._add_with_conflict_mapping(row)

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
    ) -> None:
        self._session_scope.current().add(
            MilkingAuditEventRecord(
                id=event_id,
                company_id=company_id,
                session_id=session_id,
                command_id=command_id,
                event_type=event_type,
                version_before=version_before,
                version_after=version_after,
                actor_user_id=actor_user_id,
                client_occurred_at=client_occurred_at,
                recorded_at=recorded_at,
                change_payload=dict(change_payload),
            )
        )

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
    ) -> Sequence[MilkingSession]:
        statement = select(MilkingSessionRecord).where(
            MilkingSessionRecord.company_id == company_id
        )
        if farm_id is not None:
            statement = statement.where(MilkingSessionRecord.farm_id == farm_id)
        if status is not None:
            statement = statement.where(MilkingSessionRecord.status == status)
        if date_from is not None:
            statement = statement.where(MilkingSessionRecord.milking_date >= date_from)
        if date_to is not None:
            statement = statement.where(MilkingSessionRecord.milking_date <= date_to)
        if shift_code is not None:
            statement = statement.where(MilkingSessionRecord.shift_code == shift_code)
        rows = self._session_scope.current().scalars(
            statement.order_by(
                MilkingSessionRecord.milking_date.desc(),
                MilkingSessionRecord.created_at.desc(),
                MilkingSessionRecord.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return tuple(self._session_from_record(row) for row in rows)

    def list_outputs(
        self,
        *,
        company_id: UUID,
        farm_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MilkingOutput]:
        statement = select(MilkingOutputRecord).where(
            MilkingOutputRecord.company_id == company_id
        )
        if farm_id is not None:
            statement = statement.where(MilkingOutputRecord.farm_id == farm_id)
        if date_from is not None:
            statement = statement.where(MilkingOutputRecord.production_date >= date_from)
        if date_to is not None:
            statement = statement.where(MilkingOutputRecord.production_date <= date_to)
        rows = self._session_scope.current().scalars(
            statement.order_by(
                MilkingOutputRecord.production_date.desc(),
                MilkingOutputRecord.created_at.desc(),
                MilkingOutputRecord.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return tuple(self._output_from_record(row) for row in rows)

    def _add_with_conflict_mapping(self, row: object) -> None:
        session = self._session_scope.current()
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            code = self._mapped_constraint_conflict(exc)
            if code is None:
                raise
            raise MilkingRepositoryConflict(code) from exc

    @staticmethod
    def _mapped_constraint_conflict(exc: IntegrityError) -> str | None:
        original = exc.orig
        diag = getattr(original, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)
        if constraint_name in _CONSTRAINT_CONFLICTS:
            return _CONSTRAINT_CONFLICTS[constraint_name]
        message = str(original)
        for name, code in _CONSTRAINT_CONFLICTS.items():
            if name in message:
                return code
        return None

    @staticmethod
    def _profile_from_record(row: MilkingOutputProfileRecord) -> MilkingOutputProfile:
        return MilkingOutputProfile(
            profile_id=row.profile_id,
            profile_version=int(row.profile_version),
            company_id=row.company_id,
            product_id=row.product_id,
            quantity_uom_id=row.quantity_uom_id,
            is_active=row.is_active,
            row_version=int(row.row_version),
            created_at=row.created_at,
            created_by=row.created_by,
        )

    @staticmethod
    def _configuration_from_record(row: MilkingConfigurationRecord) -> MilkingConfiguration:
        return MilkingConfiguration(
            id=row.id,
            company_id=row.company_id,
            farm_id=row.farm_id,
            shift_code=row.shift_code,
            output_profile_id=row.output_profile_id,
            output_profile_version=int(row.output_profile_version),
            is_active=row.is_active,
            version=int(row.version),
            created_at=row.created_at,
            created_by=row.created_by,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )

    @staticmethod
    def _session_from_record(row: MilkingSessionRecord) -> MilkingSession:
        return MilkingSession(
            id=row.id,
            company_id=row.company_id,
            farm_id=row.farm_id,
            milking_date=row.milking_date,
            shift_code=row.shift_code,
            operator_id=row.operator_id,
            status=MilkingSessionStatus(row.status),
            animals_milked_count=row.animals_milked_count,
            general_gross_quantity=row.general_gross_quantity,
            quantity_uom_id=row.quantity_uom_id,
            authoritative_gross_quantity=row.authoritative_gross_quantity,
            authoritative_total_source=(
                MilkingTotalSource(row.authoritative_total_source)
                if row.authoritative_total_source is not None
                else None
            ),
            used_on_farm_quantity=row.used_on_farm_quantity,
            discarded_quantity=row.discarded_quantity,
            net_output_quantity=row.net_output_quantity,
            reconciliation_status=MilkingReconciliationStatus(row.reconciliation_status),
            output_profile_id=row.output_profile_id,
            output_profile_version=int(row.output_profile_version),
            product_id=row.product_id,
            notes=row.notes,
            version=int(row.version),
            created_at=row.created_at,
            created_by=row.created_by,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
            confirmed_at=row.confirmed_at,
            confirmed_by=row.confirmed_by,
            cancelled_at=row.cancelled_at,
            cancelled_by=row.cancelled_by,
            cancel_reason=row.cancel_reason,
        )

    @staticmethod
    def _output_from_record(row: MilkingOutputRecord) -> MilkingOutput:
        return MilkingOutput(
            id=row.id,
            company_id=row.company_id,
            milking_session_id=row.milking_session_id,
            farm_id=row.farm_id,
            product_id=row.product_id,
            quantity=row.quantity,
            uom_id=row.uom_id,
            production_date=row.production_date,
            created_at=row.created_at,
            created_by=row.created_by,
        )
