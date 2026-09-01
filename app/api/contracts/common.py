from __future__ import annotations

from pydantic import BaseModel

from app.platform.commands.model import CommandExecutionOutcome


API_V1_PREFIX = "/api/v1"
# P-7 adds compatible Sync endpoints within the frozen /api/v1 major.
PUBLIC_API_VERSION = "1.1.0"
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class CommandResponse(BaseModel):
    code: str
    replayed: bool
    data: dict[str, object]


# Frozen P-6 common response surface. P-7 must not widen unrelated Auth,
# Modules or Milking operations with Sync-only statuses/descriptions.
COMMON_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Invalid request or domain validation failure."},
    401: {"model": ErrorResponse, "description": "Authentication failed."},
    403: {"model": ErrorResponse, "description": "Access denied."},
    404: {"model": ErrorResponse, "description": "Requested resource or module is not available."},
    409: {"model": ErrorResponse, "description": "Idempotency, concurrency, state or activation conflict."},
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    500: {"model": ErrorResponse, "description": "Unexpected server error."},
    503: {"model": ErrorResponse, "description": "Required platform capability is unavailable."},
}


SYNC_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    **COMMON_ERROR_RESPONSES,
    404: {
        "model": ErrorResponse,
        "description": "Requested module or Sync stream is not available.",
    },
    409: {
        "model": ErrorResponse,
        "description": "Module activation or Sync protocol conflict.",
    },
    410: {
        "model": ErrorResponse,
        "description": "The requested retained Sync checkpoint is no longer available.",
    },
}


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        status_code: COMMON_ERROR_RESPONSES[status_code]
        for status_code in status_codes
    }


def command_response(outcome: CommandExecutionOutcome) -> CommandResponse:
    return CommandResponse(
        code=outcome.result.code,
        replayed=outcome.replayed,
        data=dict(outcome.result.data),
    )
