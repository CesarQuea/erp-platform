from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors.models import PlatformError


logger = logging.getLogger(__name__)


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _error_payload(
    *,
    code: str,
    message: str,
    correlation_id: str | None,
) -> dict[str, dict[str, str | None]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        }
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PlatformError)
    async def handle_platform_error(
        request: Request,
        exc: PlatformError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=exc.code,
                message=exc.message,
                correlation_id=_correlation_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        correlation_id = _correlation_id(request)
        logger.exception(
            "unhandled_request_error",
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="INTERNAL_ERROR",
                message="An unexpected server error occurred.",
                correlation_id=correlation_id,
            ),
        )
