from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.bootstrap.tenant_platform import TenantPlatformRuntime
from app.core.config.settings import Settings
from app.infrastructure.identity.repository import SqlAlchemyIdentityRepository
from app.infrastructure.identity.runtime import PlatformIdentityDatabase
from app.infrastructure.security.credentials import (
    Argon2idPasswordHasher,
    SecureRefreshTokenGenerator,
)
from app.infrastructure.security.tokens import Hs256AccessTokenCodec
from app.platform.company.errors import CompanyNotFoundError
from app.platform.company.model import Company
from app.platform.identity.service import (
    AuthenticationService,
    CompanyDirectory,
    IdentityProvisioningService,
)
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.errors import TenancyError


class TenantCompanyDirectory(CompanyDirectory):
    def __init__(self, tenant_platform: TenantPlatformRuntime) -> None:
        self._tenant_platform = tenant_platform

    def get_company(self, tenant_id: UUID, company_id: UUID) -> Company | None:
        try:
            return self._tenant_platform.company_service.get_company(
                TenantContext(tenant_id),
                company_id,
            )
        except (CompanyNotFoundError, TenancyError):
            return None


@dataclass(slots=True)
class IdentityPlatformRuntime:
    database: PlatformIdentityDatabase
    authentication: AuthenticationService
    provisioning: IdentityProvisioningService

    def dispose(self) -> None:
        self.database.dispose()


def build_identity_platform(
    settings: Settings,
    tenant_platform: TenantPlatformRuntime,
) -> IdentityPlatformRuntime | None:
    if not settings.database_url or not settings.jwt_signing_secret:
        return None

    database = PlatformIdentityDatabase(settings)
    repository = SqlAlchemyIdentityRepository(database.scope)
    password_hasher = Argon2idPasswordHasher()
    token_codec = Hs256AccessTokenCodec(
        secret=settings.jwt_signing_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    refresh_tokens = SecureRefreshTokenGenerator()
    company_directory = TenantCompanyDirectory(tenant_platform)
    authentication = AuthenticationService(
        repository,
        database.transaction,
        password_hasher,
        token_codec,
        refresh_tokens,
        company_directory,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_token_ttl=timedelta(minutes=settings.access_token_ttl_minutes),
        refresh_token_ttl=timedelta(days=settings.refresh_token_ttl_days),
    )
    provisioning = IdentityProvisioningService(
        repository,
        database.transaction,
        password_hasher,
        tenant_platform.registry,
        company_directory,
    )
    return IdentityPlatformRuntime(
        database=database,
        authentication=authentication,
        provisioning=provisioning,
    )
