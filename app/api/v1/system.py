from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.contracts import error_responses
from app.core.errors.models import PlatformError
from app.infrastructure.database.runtime import DatabaseRuntime


router = APIRouter(tags=["platform"])


class LiveResponse(BaseModel):
    status: Literal["live"]


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ready"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    database: Literal["ready", "unavailable"]


def _database_runtime(request: Request) -> DatabaseRuntime:
    return request.app.state.database_runtime


@router.get(
    "/live",
    response_model=LiveResponse,
    responses=error_responses(500),
)
def live() -> LiveResponse:
    return LiveResponse(status="live")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses=error_responses(500, 503),
)
def ready(request: Request) -> ReadyResponse:
    database = _database_runtime(request)
    if not database.check_ready():
        raise PlatformError(
            code="PLATFORM_NOT_READY",
            message="Service dependencies are not ready.",
            status_code=503,
        )
    return ReadyResponse(status="ready", database="ready")


@router.get(
    "/health",
    response_model=HealthResponse,
    responses=error_responses(500),
)
def health(request: Request) -> HealthResponse:
    database = _database_runtime(request)
    database_ready = database.check_ready()
    settings = request.app.state.settings

    return HealthResponse(
        status="ok" if database_ready else "degraded",
        service="erp-platform",
        environment=settings.environment,
        database="ready" if database_ready else "unavailable",
    )
