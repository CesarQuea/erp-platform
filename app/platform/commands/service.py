from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping

from app.core.errors.models import PlatformError
from app.core.time.clock import Clock, SystemClock
from app.platform.commands.errors import (
    CommandExecutionUnavailableSignal,
    ConcurrencyConflictSignal,
    IdempotencyConflictSignal,
    IdempotencyResultTooLargeSignal,
    InvalidCommandContextSignal,
    InvalidReplayResultSignal,
    PlatformErrorSignal,
    command_execution_unavailable,
    concurrency_conflict,
    idempotency_conflict,
    idempotency_result_too_large,
    invalid_command_context,
)
from app.platform.commands.fingerprint import command_fingerprint
from app.platform.commands.model import (
    CommandContext,
    CommandExecutionOutcome,
    CommandExecutionRecord,
    CommandRequest,
    CommandResult,
)
from app.platform.commands.repository import CommandExecutionRepository
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory

logger = logging.getLogger(__name__)

PrincipalAuthorizer = Callable[[], AuthenticatedPrincipal]
CommandOperation = Callable[[], CommandResult]
_MAX_REPLAY_BYTES = 32 * 1024


class CommandExecutionService:
    def __init__(
        self,
        repository: CommandExecutionRepository,
        transaction_factory: TenantTransactionBoundaryFactory,
        *,
        clock: Clock | None = None,
        replay_limit_bytes: int = _MAX_REPLAY_BYTES,
    ) -> None:
        if replay_limit_bytes <= 0:
            raise ValueError("replay_limit_bytes must be positive")
        self._repository = repository
        self._transaction_factory = transaction_factory
        self._clock = clock or SystemClock()
        self._replay_limit_bytes = replay_limit_bytes

    def execute(
        self,
        request: CommandRequest,
        payload: Mapping[str, object],
        *,
        authorize: PrincipalAuthorizer,
        operation: CommandOperation,
    ) -> CommandExecutionOutcome:
        # Invoked before every execution/replay attempt. The caller wires this
        # callback to current P-3 authentication + permission checks.
        principal = authorize()
        try:
            context = CommandContext.from_principal(request, principal)
        except (TypeError, ValueError) as exc:
            raise invalid_command_context(str(exc)) from None

        try:
            fingerprint = command_fingerprint(context, payload)
        except (TypeError, ValueError) as exc:
            raise invalid_command_context(str(exc)) from None

        boundary = self._transaction_factory.for_tenant(TenantContext(context.tenant_id))
        try:
            outcome = boundary.run(
                lambda: self._execute_in_transaction(
                    context,
                    fingerprint=fingerprint,
                    operation=operation,
                )
            )
        except IdempotencyConflictSignal:
            error = idempotency_conflict()
            self._log_failure(context, error)
            raise error
        except ConcurrencyConflictSignal:
            error = concurrency_conflict()
            self._log_failure(context, error)
            raise error
        except IdempotencyResultTooLargeSignal:
            error = idempotency_result_too_large()
            self._log_failure(context, error)
            raise error
        except (InvalidReplayResultSignal, InvalidCommandContextSignal) as signal:
            error = invalid_command_context(str(signal))
            self._log_failure(context, error)
            raise error
        except CommandExecutionUnavailableSignal:
            error = command_execution_unavailable()
            self._log_failure(context, error)
            raise error
        except PlatformErrorSignal as signal:
            self._log_failure(context, signal.error)
            raise signal.error
        except Exception as exc:
            logger.error(
                "command_failed",
                extra={
                    **self._audit_fields(context),
                    "error_type": type(exc).__name__,
                    "outcome": "FAILED",
                },
            )
            raise

        logger.info(
            "command_replayed" if outcome.replayed else "command_succeeded",
            extra={
                **self._audit_fields(context),
                "outcome": "REPLAYED" if outcome.replayed else "SUCCEEDED",
            },
        )
        return outcome

    def _execute_in_transaction(
        self,
        context: CommandContext,
        *,
        fingerprint: str,
        operation: CommandOperation,
    ) -> CommandExecutionOutcome:
        claimed = self._repository.claim(
            CommandExecutionRecord(
                command_id=context.command_id,
                command_name=context.command_name,
                command_schema_version=context.command_schema_version,
                scope=context.scope,
                company_id=context.company_id,
                actor_user_id=context.actor_user_id,
                fingerprint=fingerprint,
            )
        )
        if not claimed:
            existing = self._repository.get(context.command_id)
            if existing is None:
                raise CommandExecutionUnavailableSignal()
            if existing.fingerprint != fingerprint:
                raise IdempotencyConflictSignal()
            if (
                existing.result_code is None
                or existing.result_json is None
                or existing.committed_at is None
            ):
                raise CommandExecutionUnavailableSignal()
            return CommandExecutionOutcome(
                result=CommandResult(existing.result_code, existing.result_json),
                replayed=True,
            )

        try:
            result = operation()
        except PlatformError as error:
            # Do not propagate a frozen PlatformError through transaction/context
            # managers. Preserve it and re-raise only after rollback has completed.
            raise PlatformErrorSignal(error) from None

        replay_json = self._validated_replay_json(result.data)
        self._repository.complete(
            context.command_id,
            result_code=result.code.strip(),
            result_json=replay_json,
            committed_at=self._clock.now(),
        )
        return CommandExecutionOutcome(
            result=CommandResult(result.code.strip(), replay_json),
            replayed=False,
        )

    def _validated_replay_json(
        self,
        data: Mapping[str, object],
    ) -> Mapping[str, object]:
        try:
            encoded = json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise InvalidReplayResultSignal(
                "Command replay result must be JSON-serializable."
            ) from None
        if len(encoded) > self._replay_limit_bytes:
            raise IdempotencyResultTooLargeSignal()
        decoded = json.loads(encoded.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise InvalidReplayResultSignal(
                "Command replay result must be a JSON object."
            )
        return decoded

    @staticmethod
    def _audit_fields(context: CommandContext) -> dict[str, object]:
        fields: dict[str, object] = {
            "command_id": str(context.command_id),
            "command_name": context.command_name,
            "user_id": str(context.actor_user_id),
            "session_id": str(context.session_id),
            "tenant_id": str(context.tenant_id),
            "scope": context.scope.value,
        }
        if context.company_id is not None:
            fields["company_id"] = str(context.company_id)
        if context.correlation_id:
            fields["correlation_id"] = context.correlation_id
        if context.expected_version is not None:
            fields["expected_version"] = context.expected_version
        return fields

    def _log_failure(self, context: CommandContext, error: PlatformError) -> None:
        event = {
            "IDEMPOTENCY_CONFLICT": "idempotency_conflict",
            "CONCURRENCY_CONFLICT": "concurrency_conflict",
        }.get(error.code, "command_failed")
        logger.warning(
            event,
            extra={
                **self._audit_fields(context),
                "error_code": error.code,
                "outcome": "CONFLICT" if error.status_code == 409 else "FAILED",
            },
        )
