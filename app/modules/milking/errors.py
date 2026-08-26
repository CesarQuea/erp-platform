from __future__ import annotations

from app.core.errors.models import PlatformError
from app.modules.milking.domain import MilkingDomainError
from app.modules.milking.repository import MilkingRepositoryConflict


def access_denied() -> PlatformError:
    return PlatformError("ACCESS_DENIED", "Milking access denied.", 403)


def resource_not_available() -> PlatformError:
    return PlatformError("RESOURCE_NOT_AVAILABLE", "Milking resource is not available.", 404)


def validation_failed(detail: str) -> PlatformError:
    return PlatformError("VALIDATION_FAILED", detail, 400)


def already_exists(detail: str = "Milking resource already exists.") -> PlatformError:
    return PlatformError("ALREADY_EXISTS", detail, 409)


def state_conflict() -> PlatformError:
    return PlatformError("STATE_CONFLICT", "Milking state transition is not allowed.", 409)


def version_conflict() -> PlatformError:
    return PlatformError("VERSION_CONFLICT", "Milking resource version conflict.", 409)


def business_conflict(detail: str) -> PlatformError:
    return PlatformError("BUSINESS_CONFLICT", detail, 409)


def from_domain_error(error: MilkingDomainError) -> PlatformError:
    code = str(error)
    if code == "STATE_CONFLICT":
        return state_conflict()
    if code == "VERSION_CONFLICT":
        return version_conflict()
    return validation_failed(code)


def from_repository_conflict(error: MilkingRepositoryConflict) -> PlatformError:
    if error.code in {"SESSION_ALREADY_EXISTS", "CONFIGURATION_ALREADY_EXISTS", "OUTPUT_PROFILE_ALREADY_EXISTS"}:
        return already_exists(error.code)
    if error.code in {"OUTPUT_ALREADY_EXISTS", "ANNULMENT_ALREADY_PENDING"}:
        return business_conflict(error.code)
    return business_conflict(error.code)
