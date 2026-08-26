from __future__ import annotations

from datetime import date
from uuid import UUID

from app.modules.milking.domain import MilkingOutput, MilkingSession
from app.modules.milking.errors import access_denied, resource_not_available
from app.modules.milking.query_repository import MilkingQueryRepository
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory


PERM_READ = "milking.session.read"


class MilkingQueryService:
    def __init__(
        self,
        repository: MilkingQueryRepository,
        transaction_factory: TenantTransactionBoundaryFactory,
    ) -> None:
        self._repository = repository
        self._transaction_factory = transaction_factory

    def get_session(
        self,
        *,
        principal: AuthenticatedPrincipal,
        session_id: UUID,
    ) -> MilkingSession:
        tenant_id, company_id = self._authorize(principal)
        result = self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
            lambda: self._repository.get_session(
                company_id=company_id,
                session_id=session_id,
            )
        )
        if result is None:
            raise resource_not_available()
        return result

    def list_sessions(
        self,
        *,
        principal: AuthenticatedPrincipal,
        farm_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        shift_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingSession, ...]:
        tenant_id, company_id = self._authorize(principal)
        return tuple(
            self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
                lambda: self._repository.list_sessions(
                    company_id=company_id,
                    farm_id=farm_id,
                    status=status,
                    date_from=date_from,
                    date_to=date_to,
                    shift_code=shift_code,
                    limit=limit,
                    offset=offset,
                )
            )
        )

    def get_output(
        self,
        *,
        principal: AuthenticatedPrincipal,
        output_id: UUID,
    ) -> MilkingOutput:
        tenant_id, company_id = self._authorize(principal)
        result = self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
            lambda: self._repository.get_output_by_id(
                company_id=company_id,
                output_id=output_id,
            )
        )
        if result is None:
            raise resource_not_available()
        return result

    def list_outputs(
        self,
        *,
        principal: AuthenticatedPrincipal,
        farm_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingOutput, ...]:
        tenant_id, company_id = self._authorize(principal)
        return tuple(
            self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
                lambda: self._repository.list_outputs(
                    company_id=company_id,
                    farm_id=farm_id,
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                    offset=offset,
                )
            )
        )

    @staticmethod
    def _authorize(principal: AuthenticatedPrincipal) -> tuple[UUID, UUID]:
        if (
            principal.tenant_id is None
            or principal.company_id is None
            or PERM_READ not in principal.effective_permissions
        ):
            raise access_denied()
        return principal.tenant_id, principal.company_id
