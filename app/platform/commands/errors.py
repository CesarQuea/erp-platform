from __future__ import annotations

from app.core.errors.models import PlatformError


# Internal mutable signals are used while a Tenant transaction/contextmanager is active.
# Frozen PlatformError instances are mapped only after the transaction has exited.
class _CommandSignal(RuntimeError):
    pass


class IdempotencyConflictSignal(_CommandSignal):
    pass


class ConcurrencyConflictSignal(_CommandSignal):
    pass


class IdempotencyResultTooLargeSignal(_CommandSignal):
    pass


class CommandExecutionUnavailableSignal(_CommandSignal):
    pass


class InvalidReplayResultSignal(_CommandSignal):
    pass


class InvalidCommandContextSignal(_CommandSignal):
    pass


class PlatformErrorSignal(_CommandSignal):
    def __init__(self, error: PlatformError) -> None:
        super().__init__(error.code)
        self.error = error


def invalid_command_context(message: str = "Command context is invalid.") -> PlatformError:
    return PlatformError(
        code="INVALID_COMMAND_CONTEXT",
        message=message,
        status_code=400,
    )


def idempotency_conflict() -> PlatformError:
    return PlatformError(
        code="IDEMPOTENCY_CONFLICT",
        message="The command id was already used for a different logical command.",
        status_code=409,
    )


def concurrency_conflict() -> PlatformError:
    return PlatformError(
        code="CONCURRENCY_CONFLICT",
        message="The resource version changed before the command could be applied.",
        status_code=409,
    )


def idempotency_result_too_large() -> PlatformError:
    return PlatformError(
        code="IDEMPOTENCY_RESULT_TOO_LARGE",
        message="The idempotent replay result exceeds the platform limit.",
        status_code=500,
    )


def command_execution_unavailable() -> PlatformError:
    return PlatformError(
        code="COMMAND_EXECUTION_UNAVAILABLE",
        message="The command execution state is temporarily unavailable.",
        status_code=503,
    )
