from __future__ import annotations

import re
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


_CORRELATION_HEADER = "X-Correlation-ID"
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _resolve_correlation_id(value: str | None) -> str:
    if value and _VALID_CORRELATION_ID.fullmatch(value):
        return value
    return str(uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = _resolve_correlation_id(
            request.headers.get(_CORRELATION_HEADER)
        )
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[_CORRELATION_HEADER] = correlation_id
        return response
