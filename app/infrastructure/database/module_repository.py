from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infrastructure.database.concurrency import SqlAlchemyCompareAndSet
from app.infrastructure.database.module_models import ModuleActivationRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.errors import ConcurrencyConflictSignal
from app.platform.modules.model import CompanyModuleActivation, ModuleActivationState


class SqlAlchemyModuleActivationRepository:
    def __init__(
        self,
        session_scope: TenantSessionScope,
        *,
        compare_and_set: SqlAlchemyCompareAndSet | None = None,
    ) -> None:
        self._session_scope = session_scope
        self._cas = compare_and_set or SqlAlchemyCompareAndSet(session_scope)

    def get(
        self,
        *,
        company_id: UUID,
        module_id: str,
    ) -> CompanyModuleActivation | None:
        session = self._session_scope.current()
        record = session.get(ModuleActivationRecord, (company_id, module_id))
        return self._to_domain(record) if record is not None else None

    def list_for_company(self, company_id: UUID) -> Sequence[CompanyModuleActivation]:
        session = self._session_scope.current()
        records = session.execute(
            select(ModuleActivationRecord)
            .where(ModuleActivationRecord.company_id == company_id)
            .order_by(ModuleActivationRecord.module_id)
        ).scalars().all()
        return tuple(self._to_domain(record) for record in records)

    def insert(self, activation: CompanyModuleActivation) -> None:
        session = self._session_scope.current()
        values = {
            "company_id": activation.company_id,
            "module_id": activation.module_id,
            "state": activation.state.value,
            "version": activation.version,
            "created_at": activation.created_at,
            "created_by": activation.created_by,
            "updated_at": activation.updated_at,
            "updated_by": activation.updated_by,
        }
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(ModuleActivationRecord).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    ModuleActivationRecord.company_id,
                    ModuleActivationRecord.module_id,
                ]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(ModuleActivationRecord).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    ModuleActivationRecord.company_id,
                    ModuleActivationRecord.module_id,
                ]
            )
        else:
            raise RuntimeError(
                f"P-5 module activation does not support database dialect {dialect!r}"
            )
        statement = statement.returning(ModuleActivationRecord.module_id)
        inserted = session.execute(statement).scalar_one_or_none()
        if inserted is None:
            raise ConcurrencyConflictSignal()

    def update_state(
        self,
        *,
        company_id: UUID,
        module_id: str,
        expected_version: int,
        state: ModuleActivationState,
        updated_at: datetime,
        updated_by: UUID,
    ) -> CompanyModuleActivation:
        table = ModuleActivationRecord.__table__
        new_version = self._cas.update_versioned_where(
            table,
            identity_values={
                table.c.company_id: company_id,
                table.c.module_id: module_id,
            },
            version_column=table.c.version,
            expected_version=expected_version,
            values={
                "state": state.value,
                "updated_at": updated_at,
                "updated_by": updated_by,
            },
        )
        updated = self.get(company_id=company_id, module_id=module_id)
        if updated is None or updated.version != new_version:
            raise RuntimeError("module activation disappeared after compare-and-set")
        return updated

    @staticmethod
    def _to_domain(record: ModuleActivationRecord) -> CompanyModuleActivation:
        return CompanyModuleActivation(
            company_id=record.company_id,
            module_id=record.module_id,
            state=ModuleActivationState(record.state),
            version=int(record.version),
            created_at=SqlAlchemyModuleActivationRepository._as_utc(record.created_at),
            created_by=record.created_by,
            updated_at=(
                SqlAlchemyModuleActivationRepository._as_utc(record.updated_at)
                if record.updated_at is not None
                else None
            ),
            updated_by=record.updated_by,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
