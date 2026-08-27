from __future__ import annotations

from pydantic import BaseModel

from app.platform.commands.model import CommandExecutionOutcome


API_V1_PREFIX = "/api/v1"
PUBLIC_API_VERSION = "1.0.0"
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str | None


class ErrorResponse(BaseModel):
    error: ErrorBody


class CommandResponse(BaseModel):
    code: str
    replayed: bool
    data: dict[str, object]


def command_response(outcome: CommandExecutionOutcome) -> CommandResponse:
    return CommandResponse(
        code=outcome.result.code,
        replayed=outcome.replayed,
        data=dict(outcome.result.data),
    )
