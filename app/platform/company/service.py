from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from app.core.identifiers.uuid import new_uuid
from app.core.time.clock import Clock, SystemClock
from app.platform.company.errors import CompanyNotFoundError
from app.platform.company.model import Company
from app.platform.company.repository import CompanyRepository
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory


class CompanyService:
    def __init__(
        self,
        repository: CompanyRepository,
        transaction_factory: TenantTransactionBoundaryFactory,
        *,
        clock: Clock | None = None,
        id_factory: Callable[[], UUID] = new_uuid,
    ) -> None:
        self._repository = repository
        self._transaction_factory = transaction_factory
        self._clock = clock or SystemClock()
        self._id_factory = id_factory

    def register_company(
        self,
        context: TenantContext,
        *,
        code: str,
        legal_name: str,
    ) -> Company:
        now = self._clock.now()
        company = Company(
            id=self._id_factory(),
            code=code,
            legal_name=legal_name,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        boundary = self._transaction_factory.for_tenant(context)
        return boundary.run(lambda: self._persist(company))

    def get_company(self, context: TenantContext, company_id: UUID) -> Company:
        boundary = self._transaction_factory.for_tenant(context)

        def operation() -> Company:
            company = self._repository.get_by_id(company_id)
            if company is None:
                raise CompanyNotFoundError("Company was not found in the active tenant")
            return company

        return boundary.run(operation)

    def list_companies(self, context: TenantContext) -> Sequence[Company]:
        boundary = self._transaction_factory.for_tenant(context)
        return boundary.run(self._repository.list_all)

    def _persist(self, company: Company) -> Company:
        self._repository.add(company)
        return company
