from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors.models import PlatformError


logger = logging.getLogger(__name__)


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if isinstance(value, str) and value:
        return value
    return str(uuid4())


def _error_payload(
    *,
    code: str,
    message: str,
    correlation_id: str,
) -> dict[str, dict[str, str]]:
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
        correlation_id = _correlation_id(request)
        if exc.code == "ACCESS_DENIED":
            logger.warning(
                "access_denied",
                extra={
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=exc.code,
                message=exc.message,
                correlation_id=correlation_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Never serialize exc.errors() or exc.body here: validation failures may
        # contain passwords, refresh tokens or other credentials supplied by the client.
        correlation_id = _correlation_id(request)
        logger.info(
            "request_validation_failed",
            extra={
                "correlation_id": correlation_id,
                "error_count": len(exc.errors()),
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="REQUEST_VALIDATION_FAILED",
                message="Request validation failed.",
                correlation_id=correlation_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        correlation_id = _correlation_id(request)
        logger.error(
            "unhandled_request_error",
            extra={
                "correlation_id": correlation_id,
                "error_type": type(exc).__name__,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="INTERNAL_ERROR",
                message="An unexpected server error occurred.",
                correlation_id=correlation_id,
            ),
        )
