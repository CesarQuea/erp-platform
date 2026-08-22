from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models import CompanyRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.company.errors import CompanyConflictError
from app.platform.company.model import Company


class SqlAlchemyCompanyRepository:
    def __init__(self, session_scope: TenantSessionScope) -> None:
        self._session_scope = session_scope

    def add(self, company: Company) -> None:
        session = self._session_scope.current()
        record = CompanyRecord(
            id=company.id,
            code=company.code,
            legal_name=company.legal_name,
            is_active=company.is_active,
            created_at=company.created_at,
            updated_at=company.updated_at,
        )
        session.add(record)
        try:
            session.flush()
        except IntegrityError:
            raise CompanyConflictError(
                "Company could not be registered due to a uniqueness conflict"
            ) from None

    def get_by_id(self, company_id: UUID) -> Company | None:
        session = self._session_scope.current()
        record = session.get(CompanyRecord, company_id)
        return self._to_domain(record) if record is not None else None

    def list_all(self) -> Sequence[Company]:
        session = self._session_scope.current()
        records = session.execute(
            select(CompanyRecord).order_by(CompanyRecord.code)
        ).scalars().all()
        return tuple(self._to_domain(record) for record in records)

    @staticmethod
    def _to_domain(record: CompanyRecord) -> Company:
        return Company(
            id=record.id,
            code=record.code,
            legal_name=record.legal_name,
            is_active=record.is_active,
            created_at=SqlAlchemyCompanyRepository._as_utc(record.created_at),
            updated_at=SqlAlchemyCompanyRepository._as_utc(record.updated_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
