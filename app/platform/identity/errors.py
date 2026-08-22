from __future__ import annotations

from app.core.errors.models import PlatformError


def authentication_failed() -> PlatformError:
    return PlatformError(
        code="AUTHENTICATION_FAILED",
        message="Authentication failed.",
        status_code=401,
    )


def access_denied() -> PlatformError:
    return PlatformError(
        code="ACCESS_DENIED",
        message="Access is not allowed for the requested context.",
        status_code=403,
    )


def identity_conflict(message: str = "Identity resource already exists.") -> PlatformError:
    return PlatformError(code="IDENTITY_CONFLICT", message=message, status_code=409)


def identity_not_found(message: str = "Identity resource was not found.") -> PlatformError:
    return PlatformError(code="IDENTITY_NOT_FOUND", message=message, status_code=404)


def identity_unavailable() -> PlatformError:
    return PlatformError(
        code="IDENTITY_UNAVAILABLE",
        message="Identity service is unavailable.",
        status_code=503,
    )
