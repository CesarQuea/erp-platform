from __future__ import annotations

from app.core.errors.models import PlatformError


def sync_stream_not_found() -> PlatformError:
    return PlatformError(
        code="SYNC_STREAM_NOT_FOUND",
        message="The requested Sync stream is not available.",
        status_code=404,
    )


def sync_cursor_invalid() -> PlatformError:
    return PlatformError(
        code="SYNC_CURSOR_INVALID",
        message="The supplied Sync cursor is invalid for this request.",
        status_code=400,
    )


def sync_cursor_expired() -> PlatformError:
    return PlatformError(
        code="SYNC_CURSOR_EXPIRED",
        message="The supplied Sync cursor can no longer be continued.",
        status_code=410,
    )


def sync_protocol_unsupported() -> PlatformError:
    return PlatformError(
        code="SYNC_PROTOCOL_UNSUPPORTED",
        message="The requested Sync protocol version is not supported.",
        status_code=409,
    )


def sync_schema_unsupported() -> PlatformError:
    # Reserved by BE-DES-007 v0.1 for a future explicit projection-schema
    # negotiation capability. P-7 v0.1 does not infer client schema support.
    return PlatformError(
        code="SYNC_SCHEMA_UNSUPPORTED",
        message="The requested Sync projection schema is not supported.",
        status_code=409,
    )


def sync_batch_too_large() -> PlatformError:
    return PlatformError(
        code="SYNC_BATCH_TOO_LARGE",
        message="The Sync batch exceeds the configured server limit.",
        status_code=500,
    )
