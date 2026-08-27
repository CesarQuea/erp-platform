from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from app.core.time.clock import Clock, SystemClock
from app.platform.commands.errors import ConcurrencyConflictSignal
from app.platform.commands.model import (
    CommandExecutionOutcome,
    CommandRequest,
    CommandResult,
    CommandScope,
)
from app.platform.commands.service import CommandExecutionService
from app.platform.company.repository import CompanyRepository
from app.platform.identity.errors import access_denied
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.errors import (
    module_activation_not_available,
    module_not_enabled,
    module_not_registered,
)
from app.platform.modules.model import (
    ChangeModuleActivation,
    CompanyModuleActivation,
    CompanyModuleStatus,
    ModuleActivationState,
    ModuleDefinition,
)
from app.platform.modules.registry import ModuleNotRegisteredError, ModuleRegistry
from app.platform.modules.repository import ModuleActivationRepository
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory


PERM_MANAGE_MODULES = "platform.modules.manage"
_SCHEMA_VERSION = "1"


class ModuleAvailabilityService:
    def __init__(
        self,
        registry: ModuleRegistry,
        activation_repository: ModuleActivationRepository,
        company_repository: CompanyRepository,
        transaction_factory: TenantTransactionBoundaryFactory,
    ) -> None:
        self._registry = registry
        self._activations = activation_repository
        self._companies = company_repository
        self._transactions = transaction_factory

    def is_registered(self, module_id: str) -> bool:
        return self._registry.contains(module_id)

    def list_available_modules(self) -> Sequence[ModuleDefinition]:
        return self._registry.list()

    def get_activation(
        self,
        context: TenantContext,
        company_id: UUID,
        module_id: str,
    ) -> CompanyModuleActivation | None:
        self._require_registered(module_id)
        boundary = self._transactions.for_tenant(context)

        def operation() -> CompanyModuleActivation | None:
            self._require_active_company(company_id)
            return self._activations.get(company_id=company_id, module_id=module_id)

        return boundary.run(operation)

    def is_enabled(
        self,
        context: TenantContext,
        company_id: UUID,
        module_id: str,
    ) -> bool:
        self._require_registered(module_id)
        boundary = self._transactions.for_tenant(context)

        def operation() -> bool:
            company = self._companies.get_by_id(company_id)
            if company is None or not company.is_active:
                return False
            activation = self._activations.get(
                company_id=company_id,
                module_id=module_id,
            )
            return (
                activation is not None
                and activation.state is ModuleActivationState.ENABLED
            )

        return boundary.run(operation)

    def require_enabled(
        self,
        context: TenantContext,
        company_id: UUID,
        module_id: str,
    ) -> ModuleDefinition:
        definition = self._require_registered(module_id)
        boundary = self._transactions.for_tenant(context)

        def operation() -> None:
            self._require_active_company(company_id)
            activation = self._activations.get(
                company_id=company_id,
                module_id=module_id,
            )
            if activation is None or activation.state is not ModuleActivationState.ENABLED:
                raise module_not_enabled()

        boundary.run(operation)
        return definition

    def list_company_modules(
        self,
        context: TenantContext,
        company_id: UUID,
    ) -> Sequence[CompanyModuleStatus]:
        boundary = self._transactions.for_tenant(context)

        def operation() -> Sequence[CompanyModuleStatus]:
            self._require_active_company(company_id)
            activations = {
                activation.module_id: activation
                for activation in self._activations.list_for_company(company_id)
            }
            if any(not self._registry.contains(module_id) for module_id in activations):
                raise module_not_registered()

            statuses: list[CompanyModuleStatus] = []
            for definition in self._registry.list():
                activation = activations.get(definition.module_id)
                if activation is None:
                    statuses.append(
                        CompanyModuleStatus(
                            definition=definition,
                            state=ModuleActivationState.DISABLED,
                            version=0,
                            activation_present=False,
                            effective_enabled=False,
                        )
                    )
                else:
                    statuses.append(
                        CompanyModuleStatus(
                            definition=definition,
                            state=activation.state,
                            version=activation.version,
                            activation_present=True,
                            effective_enabled=(
                                activation.state is ModuleActivationState.ENABLED
                            ),
                        )
                    )
            return tuple(statuses)

        return boundary.run(operation)

    def _require_registered(self, module_id: str) -> ModuleDefinition:
        try:
            return self._registry.get(module_id)
        except ModuleNotRegisteredError:
            raise module_not_registered() from None

    def _require_active_company(self, company_id: UUID) -> None:
        company = self._companies.get_by_id(company_id)
        if company is None or not company.is_active:
            raise module_activation_not_available()


class ModuleActivationService:
    def __init__(
        self,
        registry: ModuleRegistry,
        activation_repository: ModuleActivationRepository,
        company_repository: CompanyRepository,
        command_execution: CommandExecutionService,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._activations = activation_repository
        self._companies = company_repository
        self._commands = command_execution
        self._clock = clock or SystemClock()

    def enable_module(
        self,
        command: ChangeModuleActivation,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        return self._change(
            command,
            target_state=ModuleActivationState.ENABLED,
            principal=principal,
        )

    def disable_module(
        self,
        command: ChangeModuleActivation,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        return self._change(
            command,
            target_state=ModuleActivationState.DISABLED,
            principal=principal,
        )

    def _change(
        self,
        command: ChangeModuleActivation,
        *,
        target_state: ModuleActivationState,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = CommandRequest(
            command_id=command.command_id,
            command_name=(
                "PLATFORM_MODULE_ENABLE"
                if target_state is ModuleActivationState.ENABLED
                else "PLATFORM_MODULE_DISABLE"
            ),
            command_schema_version=_SCHEMA_VERSION,
            scope=CommandScope.COMPANY,
            expected_version=command.expected_version,
        )
        payload: dict[str, object] = {
            "module_id": command.module_id,
            "target_state": target_state.value,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal),
            operation=lambda: self._change_operation(
                command,
                target_state=target_state,
                principal=principal,
            ),
        )

    def _change_operation(
        self,
        command: ChangeModuleActivation,
        *,
        target_state: ModuleActivationState,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        self._require_registered(command.module_id)
        company_id = self._company_id(principal)
        company = self._companies.get_by_id(company_id)
        if company is None or not company.is_active:
            raise module_activation_not_available()

        current = self._activations.get(
            company_id=company_id,
            module_id=command.module_id,
        )
        current_version = current.version if current is not None else 0
        if command.expected_version != current_version:
            raise ConcurrencyConflictSignal()

        if current is None:
            if target_state is ModuleActivationState.DISABLED:
                return self._result(
                    command.module_id,
                    state=ModuleActivationState.DISABLED,
                    version=0,
                    changed=False,
                )
            now = self._clock.now()
            created = CompanyModuleActivation(
                company_id=company_id,
                module_id=command.module_id,
                state=ModuleActivationState.ENABLED,
                version=1,
                created_at=now,
                created_by=principal.user_id,
            )
            self._activations.insert(created)
            return self._result(
                command.module_id,
                state=created.state,
                version=created.version,
                changed=True,
            )

        if current.state is target_state:
            return self._result(
                command.module_id,
                state=current.state,
                version=current.version,
                changed=False,
            )

        changed = self._activations.update_state(
            company_id=company_id,
            module_id=command.module_id,
            expected_version=command.expected_version,
            state=target_state,
            updated_at=self._clock.now(),
            updated_by=principal.user_id,
        )
        return self._result(
            command.module_id,
            state=changed.state,
            version=changed.version,
            changed=True,
        )

    @staticmethod
    def _result(
        module_id: str,
        *,
        state: ModuleActivationState,
        version: int,
        changed: bool,
    ) -> CommandResult:
        return CommandResult(
            "MODULE_ACTIVATION_CHANGED" if changed else "MODULE_ACTIVATION_UNCHANGED",
            {
                "module_id": module_id,
                "state": state.value,
                "version": version,
                "changed": changed,
            },
        )

    def _require_registered(self, module_id: str) -> ModuleDefinition:
        try:
            return self._registry.get(module_id)
        except ModuleNotRegisteredError:
            raise module_not_registered() from None

    @staticmethod
    def _authorizer(
        principal: AuthenticatedPrincipal,
    ) -> Callable[[], AuthenticatedPrincipal]:
        def authorize() -> AuthenticatedPrincipal:
            if not principal.has_operational_context:
                raise access_denied()
            if PERM_MANAGE_MODULES not in principal.effective_permissions:
                raise access_denied()
            return principal

        return authorize

    @staticmethod
    def _company_id(principal: AuthenticatedPrincipal) -> UUID:
        if principal.company_id is None or principal.tenant_id is None:
            raise access_denied()
        return principal.company_id
