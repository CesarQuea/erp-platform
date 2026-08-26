from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.errors.models import PlatformError
from app.core.time.clock import Clock, SystemClock
from app.modules.milking.annulment import annul_done_without_output, validate_annulment_request
from app.modules.milking.commands import (
    CancelDraftMilkingSession,
    ConfirmMilkingSession,
    CreateMilkingSession,
    RequestMilkingAnnulment,
    SetMilkingGeneral,
    SetMilkingNotes,
    SetMilkingUseDiscard,
)
from app.modules.milking.domain import MilkingDomainError, MilkingSession
from app.modules.milking.errors import (
    access_denied,
    already_exists,
    business_conflict,
    from_domain_error,
    from_repository_conflict,
    resource_not_available,
)
from app.modules.milking.repository import MilkingRepository, MilkingRepositoryConflict
from app.platform.commands.model import (
    CommandExecutionOutcome,
    CommandRequest,
    CommandResult,
    CommandScope,
)
from app.platform.commands.service import CommandExecutionService
from app.platform.identity.model import AuthenticatedPrincipal


PERM_CREATE = "milking.session.create"
PERM_UPDATE_DRAFT = "milking.session.update_draft"
PERM_CONFIRM = "milking.session.confirm"
PERM_CANCEL = "milking.session.cancel"

_SCHEMA_VERSION = "1"


class MilkingCommandApplicationService:
    def __init__(
        self,
        repository: MilkingRepository,
        command_execution: CommandExecutionService,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._commands = command_execution
        self._clock = clock or SystemClock()

    def create_session(
        self,
        command: CreateMilkingSession,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        shift_code = command.shift_code.strip()
        payload: dict[str, object] = {
            "farm_id": command.farm_id,
            "milking_date": command.milking_date.isoformat(),
            "shift_code": shift_code,
            "operator_id": command.operator_id,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(command.command_id, "MILKING_CREATE", expected_version=None)
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CREATE),
            operation=lambda: self._guard(
                lambda: self._create_operation(command, principal, shift_code)
            ),
        )

    def set_general(
        self,
        command: SetMilkingGeneral,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "general_gross_quantity": command.general_gross_quantity,
            "animals_milked_count": command.animals_milked_count,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_SET_GENERAL",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_UPDATE_DRAFT),
            operation=lambda: self._guard(lambda: self._set_general_operation(command, principal)),
        )

    def set_use_discard(
        self,
        command: SetMilkingUseDiscard,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "used_on_farm_quantity": command.used_on_farm_quantity,
            "discarded_quantity": command.discarded_quantity,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_SET_USE_DISCARD",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_UPDATE_DRAFT),
            operation=lambda: self._guard(
                lambda: self._set_use_discard_operation(command, principal)
            ),
        )

    def set_notes(
        self,
        command: SetMilkingNotes,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "notes": command.notes,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_SET_NOTES",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_UPDATE_DRAFT),
            operation=lambda: self._guard(lambda: self._set_notes_operation(command, principal)),
        )

    def confirm(
        self,
        command: ConfirmMilkingSession,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_CONFIRM",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CONFIRM),
            operation=lambda: self._guard(lambda: self._confirm_operation(command, principal)),
        )

    def cancel_draft(
        self,
        command: CancelDraftMilkingSession,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "reason": command.reason.strip(),
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_CANCEL_DRAFT",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CANCEL),
            operation=lambda: self._guard(lambda: self._cancel_operation(command, principal)),
        )

    def request_annulment(
        self,
        command: RequestMilkingAnnulment,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        payload: dict[str, object] = {
            "session_id": command.session_id,
            "reason": command.reason.strip(),
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        request = self._request(
            command.command_id,
            "MILKING_REQUEST_ANNULMENT",
            expected_version=command.expected_version,
        )
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CANCEL),
            operation=lambda: self._guard(lambda: self._annulment_operation(command, principal)),
        )

    def _create_operation(
        self,
        command: CreateMilkingSession,
        principal: AuthenticatedPrincipal,
        shift_code: str,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        configuration = self._repository.get_configuration(
            company_id=company_id,
            farm_id=command.farm_id,
            shift_code=shift_code,
        )
        if configuration is None or not configuration.is_active:
            raise resource_not_available()
        profile = self._repository.get_output_profile(
            company_id=company_id,
            profile_id=configuration.output_profile_id,
            profile_version=configuration.output_profile_version,
        )
        if profile is None or not profile.is_active:
            raise resource_not_available()
        if self._repository.find_active_session_by_identity(
            company_id=company_id,
            farm_id=command.farm_id,
            milking_date=command.milking_date,
            shift_code=shift_code,
        ) is not None:
            raise already_exists("SESSION_ALREADY_EXISTS")

        recorded_at = self._clock.now()
        milking_session = MilkingSession.new_draft(
            company_id=company_id,
            farm_id=command.farm_id,
            milking_date=command.milking_date,
            shift_code=shift_code,
            operator_id=command.operator_id,
            quantity_uom_id=profile.quantity_uom_id,
            output_profile_id=profile.profile_id,
            output_profile_version=profile.profile_version,
            product_id=profile.product_id,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.insert_session(milking_session)
        self._audit(
            milking_session,
            command_id=command.command_id,
            event_type="SESSION_CREATED",
            version_before=None,
            version_after=milking_session.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={
                "farm_id": str(milking_session.farm_id),
                "milking_date": milking_session.milking_date.isoformat(),
                "shift_code": milking_session.shift_code,
                "output_profile_id": str(milking_session.output_profile_id),
                "output_profile_version": milking_session.output_profile_version,
                "product_id": str(milking_session.product_id),
                "quantity_uom_id": str(milking_session.quantity_uom_id),
            },
        )
        return self._result(milking_session, output_id=None, code="MILKING_SESSION_CREATED")

    def _set_general_operation(
        self,
        command: SetMilkingGeneral,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        recorded_at = self._clock.now()
        changed = current.set_general(
            gross_quantity=command.general_gross_quantity,
            animals_milked_count=command.animals_milked_count,
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.update_session(changed, expected_version=command.expected_version)
        self._audit(
            changed,
            command_id=command.command_id,
            event_type="GENERAL_SET",
            version_before=current.version,
            version_after=changed.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={
                "general_gross_quantity": self._decimal_text(changed.general_gross_quantity),
                "animals_milked_count": changed.animals_milked_count,
            },
        )
        return self._result(changed, output_id=None, code="MILKING_GENERAL_UPDATED")

    def _set_use_discard_operation(
        self,
        command: SetMilkingUseDiscard,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        recorded_at = self._clock.now()
        changed = current.set_use_discard(
            used_on_farm_quantity=command.used_on_farm_quantity,
            discarded_quantity=command.discarded_quantity,
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.update_session(changed, expected_version=command.expected_version)
        self._audit(
            changed,
            command_id=command.command_id,
            event_type="USE_DISCARD_SET",
            version_before=current.version,
            version_after=changed.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={
                "used_on_farm_quantity": self._decimal_text(changed.used_on_farm_quantity),
                "discarded_quantity": self._decimal_text(changed.discarded_quantity),
            },
        )
        return self._result(changed, output_id=None, code="MILKING_USE_DISCARD_UPDATED")

    def _set_notes_operation(
        self,
        command: SetMilkingNotes,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        recorded_at = self._clock.now()
        changed = current.set_notes(
            notes=command.notes,
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.update_session(changed, expected_version=command.expected_version)
        self._audit(
            changed,
            command_id=command.command_id,
            event_type="NOTES_SET",
            version_before=current.version,
            version_after=changed.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={"notes": changed.notes},
        )
        return self._result(changed, output_id=None, code="MILKING_NOTES_UPDATED")

    def _confirm_operation(
        self,
        command: ConfirmMilkingSession,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        recorded_at = self._clock.now()
        confirmed, output = current.confirm(
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.update_session(confirmed, expected_version=command.expected_version)
        if output is not None:
            self._repository.insert_output(output)
        self._audit(
            confirmed,
            command_id=command.command_id,
            event_type="SESSION_CONFIRMED",
            version_before=current.version,
            version_after=confirmed.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={
                "authoritative_gross_quantity": self._decimal_text(
                    confirmed.authoritative_gross_quantity
                ),
                "used_on_farm_quantity": self._decimal_text(confirmed.used_on_farm_quantity),
                "discarded_quantity": self._decimal_text(confirmed.discarded_quantity),
                "net_output_quantity": self._decimal_text(confirmed.net_output_quantity),
                "output_id": str(output.id) if output is not None else None,
            },
        )
        return self._result(
            confirmed,
            output_id=output.id if output is not None else None,
            code="MILKING_SESSION_CONFIRMED",
        )

    def _cancel_operation(
        self,
        command: CancelDraftMilkingSession,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        recorded_at = self._clock.now()
        cancelled = current.cancel_draft(
            reason=command.reason,
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=recorded_at,
        )
        self._repository.update_session(cancelled, expected_version=command.expected_version)
        self._audit(
            cancelled,
            command_id=command.command_id,
            event_type="DRAFT_CANCELLED",
            version_before=current.version,
            version_after=cancelled.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={"reason": cancelled.cancel_reason},
        )
        return self._result(cancelled, output_id=None, code="MILKING_DRAFT_CANCELLED")

    def _annulment_operation(
        self,
        command: RequestMilkingAnnulment,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        current = self._load_session(principal, command.session_id)
        self._require_active_configuration(current)
        normalized_reason = validate_annulment_request(
            current,
            reason=command.reason,
            expected_version=command.expected_version,
        )
        recorded_at = self._clock.now()
        output = self._repository.get_output_for_session(
            company_id=current.company_id,
            session_id=current.id,
        )
        if output is None:
            cancelled = annul_done_without_output(
                current,
                reason=normalized_reason,
                expected_version=command.expected_version,
                actor_user_id=principal.user_id,
                occurred_at=recorded_at,
            )
            self._repository.update_session(cancelled, expected_version=command.expected_version)
            self._audit(
                cancelled,
                command_id=command.command_id,
                event_type="DONE_ANNULLED_NO_OUTPUT",
                version_before=current.version,
                version_after=cancelled.version,
                actor_user_id=principal.user_id,
                client_occurred_at=command.client_occurred_at,
                recorded_at=recorded_at,
                change_payload={"reason": normalized_reason},
            )
            return self._result(cancelled, output_id=None, code="MILKING_SESSION_ANNULLED")

        if self._repository.has_pending_annulment(
            company_id=current.company_id,
            session_id=current.id,
        ):
            raise business_conflict("ANNULMENT_ALREADY_PENDING")
        request_id = uuid4()
        self._repository.insert_annulment_request(
            request_id=request_id,
            company_id=current.company_id,
            session_id=current.id,
            reason=normalized_reason,
            requested_by=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
        )
        self._audit(
            current,
            command_id=command.command_id,
            event_type="ANNULMENT_REQUESTED",
            version_before=current.version,
            version_after=current.version,
            actor_user_id=principal.user_id,
            client_occurred_at=command.client_occurred_at,
            recorded_at=recorded_at,
            change_payload={
                "annulment_request_id": str(request_id),
                "reason": normalized_reason,
                "output_id": str(output.id),
            },
        )
        return self._result(
            current,
            output_id=output.id,
            code="MILKING_ANNULMENT_REQUESTED",
        )

    def _load_session(
        self,
        principal: AuthenticatedPrincipal,
        session_id: UUID,
    ) -> MilkingSession:
        company_id = self._company_id(principal)
        milking_session = self._repository.get_session(
            company_id=company_id,
            session_id=session_id,
        )
        if milking_session is None:
            raise resource_not_available()
        return milking_session

    def _require_active_configuration(self, milking_session: MilkingSession) -> None:
        configuration = self._repository.get_configuration(
            company_id=milking_session.company_id,
            farm_id=milking_session.farm_id,
            shift_code=milking_session.shift_code,
        )
        if configuration is None or not configuration.is_active:
            raise resource_not_available()

    def _audit(
        self,
        milking_session: MilkingSession,
        *,
        command_id: UUID,
        event_type: str,
        version_before: int | None,
        version_after: int | None,
        actor_user_id: UUID,
        client_occurred_at: datetime,
        recorded_at: datetime,
        change_payload: Mapping[str, object],
    ) -> None:
        self._repository.insert_audit_event(
            event_id=uuid4(),
            company_id=milking_session.company_id,
            session_id=milking_session.id,
            command_id=command_id,
            event_type=event_type,
            version_before=version_before,
            version_after=version_after,
            actor_user_id=actor_user_id,
            client_occurred_at=client_occurred_at,
            recorded_at=recorded_at,
            change_payload=change_payload,
        )

    @staticmethod
    def _result(
        milking_session: MilkingSession,
        *,
        output_id: UUID | None,
        code: str,
    ) -> CommandResult:
        return CommandResult(
            code,
            {
                "session_id": str(milking_session.id),
                "version": milking_session.version,
                "status": milking_session.status.value,
                "output_id": str(output_id) if output_id is not None else None,
            },
        )

    @staticmethod
    def _request(
        command_id: UUID,
        command_name: str,
        *,
        expected_version: int | None,
    ) -> CommandRequest:
        return CommandRequest(
            command_id=command_id,
            command_name=command_name,
            command_schema_version=_SCHEMA_VERSION,
            scope=CommandScope.COMPANY,
            expected_version=expected_version,
        )

    @staticmethod
    def _authorizer(
        principal: AuthenticatedPrincipal,
        permission: str,
    ) -> Callable[[], AuthenticatedPrincipal]:
        def authorize() -> AuthenticatedPrincipal:
            if not principal.has_operational_context:
                raise access_denied()
            if permission not in principal.effective_permissions:
                raise access_denied()
            return principal

        return authorize

    @staticmethod
    def _company_id(principal: AuthenticatedPrincipal) -> UUID:
        if principal.company_id is None or principal.tenant_id is None:
            raise access_denied()
        return principal.company_id

    @staticmethod
    def _guard(operation: Callable[[], CommandResult]) -> CommandResult:
        try:
            return operation()
        except MilkingDomainError as error:
            raise from_domain_error(error) from None
        except MilkingRepositoryConflict as error:
            raise from_repository_conflict(error) from None

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")
