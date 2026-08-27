from __future__ import annotations

from app.core.errors.models import PlatformError


def module_not_registered() -> PlatformError:
    return PlatformError(
        code="MODULE_NOT_REGISTERED",
        message="The requested module is not registered in this runtime.",
        status_code=404,
    )


def module_not_enabled() -> PlatformError:
    return PlatformError(
        code="MODULE_NOT_ENABLED",
        message="The requested module is not enabled for the active company.",
        status_code=409,
    )


def module_activation_not_available() -> PlatformError:
    return PlatformError(
        code="MODULE_ACTIVATION_NOT_AVAILABLE",
        message="Module activation is not available for the active company.",
        status_code=409,
    )
