from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.bootstrap.identity_platform import (
    IdentityPlatformRuntime,
    build_identity_platform,
)
from app.bootstrap.milking_platform import MilkingPlatformRuntime, build_milking_platform
from app.bootstrap.tenant_platform import TenantPlatformRuntime, build_tenant_platform
from app.core.config.settings import Settings, get_settings
from app.core.errors.handlers import install_exception_handlers
from app.infrastructure.database.runtime import DatabaseRuntime
from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.observability.middleware import CorrelationIdMiddleware


DatabaseRuntimeFactory = Callable[[Settings], DatabaseRuntime]
TenantPlatformRuntimeFactory = Callable[[Settings], TenantPlatformRuntime]
IdentityPlatformRuntimeFactory = Callable[
    [Settings, TenantPlatformRuntime],
    IdentityPlatformRuntime | None,
]
MilkingPlatformRuntimeFactory = Callable[
    [TenantPlatformRuntime],
    MilkingPlatformRuntime | None,
]


def create_app(
    *,
    settings: Settings | None = None,
    database_runtime_factory: DatabaseRuntimeFactory = DatabaseRuntime,
    tenant_platform_factory: TenantPlatformRuntimeFactory = build_tenant_platform,
    identity_platform_factory: IdentityPlatformRuntimeFactory = build_identity_platform,
    milking_platform_factory: MilkingPlatformRuntimeFactory = build_milking_platform,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_runtime = database_runtime_factory(resolved_settings)
        tenant_platform: TenantPlatformRuntime | None = None
        identity_platform: IdentityPlatformRuntime | None = None
        milking_platform: MilkingPlatformRuntime | None = None
        try:
            tenant_platform = tenant_platform_factory(resolved_settings)
            identity_platform = identity_platform_factory(
                resolved_settings,
                tenant_platform,
            )
            milking_platform = milking_platform_factory(tenant_platform)
            app.state.settings = resolved_settings
            app.state.database_runtime = database_runtime
            app.state.tenant_platform = tenant_platform
            app.state.identity_platform = identity_platform
            app.state.milking_platform = milking_platform
            yield
        finally:
            if milking_platform is not None:
                milking_platform.dispose()
            if identity_platform is not None:
                identity_platform.dispose()
            if tenant_platform is not None:
                tenant_platform.dispose()
            database_runtime.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.4.0",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app
