from __future__ import annotations

from dataclasses import dataclass

from app.core.config.settings import Settings
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.company.service import CompanyService


@dataclass(slots=True)
class TenantPlatformRuntime:
    registry: EnvironmentTenantRegistry
    resolver: SqlAlchemyTenantDataSourceResolver
    provisioner: TenantProvisioner
    company_service: CompanyService

    def dispose(self) -> None:
        self.resolver.dispose()


def build_tenant_platform(settings: Settings) -> TenantPlatformRuntime:
    registry = EnvironmentTenantRegistry.from_json(settings.tenant_databases_json)
    resolver = SqlAlchemyTenantDataSourceResolver(
        registry,
        max_cached_engines=settings.tenant_engine_cache_size,
    )
    session_scope = TenantSessionScope()
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    company_repository = SqlAlchemyCompanyRepository(session_scope)
    return TenantPlatformRuntime(
        registry=registry,
        resolver=resolver,
        provisioner=TenantProvisioner(registry),
        company_service=CompanyService(company_repository, transaction_factory),
    )
