from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.bootstrap.identity_platform import IdentityPlatformRuntime
from app.bootstrap.module_platform import ModulePlatformRuntime
from app.platform.identity.errors import access_denied, authentication_failed, identity_unavailable
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.errors import module_activation_not_available
from app.platform.tenancy.context import TenantContext


_bearer = HTTPBearer(auto_error=False)


def identity_runtime(request: Request) -> IdentityPlatformRuntime:
    runtime = getattr(request.app.state, "identity_platform", None)
    if runtime is None:
        raise identity_unavailable()
    return runtime


def module_runtime(request: Request) -> ModulePlatformRuntime:
    runtime = getattr(request.app.state, "module_platform", None)
    if runtime is None:
        raise module_activation_not_available()
    return runtime


def access_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> str:
    if credentials is None or not credentials.credentials:
        raise authentication_failed()
    return credentials.credentials


def current_principal(
    request: Request,
    token: Annotated[str, Depends(access_token)],
) -> AuthenticatedPrincipal:
    return identity_runtime(request).authentication.principal_from_access_token(token)


def operational_principal(
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> AuthenticatedPrincipal:
    if not principal.has_operational_context:
        raise access_denied()
    return principal


def require_module_enabled(
    module_id: str,
) -> Callable[..., AuthenticatedPrincipal]:
    def dependency(
        request: Request,
        principal: Annotated[
            AuthenticatedPrincipal,
            Depends(operational_principal),
        ],
    ) -> AuthenticatedPrincipal:
        runtime = module_runtime(request)
        if runtime.availability is None:
            raise module_activation_not_available()
        assert principal.tenant_id is not None
        assert principal.company_id is not None
        runtime.availability.require_enabled(
            TenantContext(principal.tenant_id),
            principal.company_id,
            module_id,
        )
        return principal

    return dependency
