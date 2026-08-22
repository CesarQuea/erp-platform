from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config.settings import Settings, get_settings
from app.core.errors.handlers import install_exception_handlers
from app.infrastructure.database.runtime import DatabaseRuntime
from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.observability.middleware import CorrelationIdMiddleware


DatabaseRuntimeFactory = Callable[[Settings], DatabaseRuntime]


def create_app(
    *,
    settings: Settings | None = None,
    database_runtime_factory: DatabaseRuntimeFactory = DatabaseRuntime,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_runtime = database_runtime_factory(resolved_settings)
        app.state.settings = resolved_settings
        app.state.database_runtime = database_runtime
        try:
            yield
        finally:
            database_runtime.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_exception_handlers(app)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app
