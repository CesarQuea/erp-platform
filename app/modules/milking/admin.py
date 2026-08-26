from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from app.core.errors.models import PlatformError
from app.core.time.clock import Clock, SystemClock
from app.modules.milking.admin_commands import (
    CreateMilkingConfiguration,
    CreateOutputProfile,
    CreateOutputProfileVersion,
    SetOutputProfileActive,
    UpdateMilkingConfiguration,
)
from app.modules.milking.admin_repository import MilkingAdminRepository
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.errors import (
    access_denied,
    business_conflict,
    from_domain_error,
    from_repository_conflict,
    resource_not_available,
)
from app.modules.milking.domain import MilkingDomainError
from app.modules.milking.repository import MilkingRepositoryConflict
from app.platform.commands.model import (
    CommandExecutionOutcome,
    CommandRequest,
    CommandResult,
    CommandScope,
)
from app.platform.commands.service import CommandExecutionService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory


PERM_PROFILE_READ = "milking.output_profile.read"
PERM_PROFILE_MANAGE = "milking.output_profile.manage"
PERM_CONFIG_READ = "milking.config.read"
PERM_CONFIG_MANAGE = "milking.config.manage"
_SCHEMA_VERSION = "1"


class MilkingAdminService:
    def __init__(
        self,
        repository: MilkingAdminRepository,
        command_execution: CommandExecutionService,
        transaction_factory: TenantTransactionBoundaryFactory,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._commands = command_execution
        self._transaction_factory = transaction_factory
        self._clock = clock or SystemClock()

    def create_output_profile(
        self,
        command: CreateOutputProfile,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = self._request(command.command_id, "MILKING_OUTPUT_PROFILE_CREATE")
        payload = {
            "product_id": command.product_id,
            "quantity_uom_id": command.quantity_uom_id,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_PROFILE_MANAGE),
            operation=lambda: self._guard(
                lambda: self._create_output_profile_operation(command, principal)
            ),
        )

    def create_output_profile_version(
        self,
        command: CreateOutputProfileVersion,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = self._request(command.command_id, "MILKING_OUTPUT_PROFILE_NEW_VERSION")
        payload = {
            "profile_id": command.profile_id,
            "product_id": command.product_id,
            "quantity_uom_id": command.quantity_uom_id,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_PROFILE_MANAGE),
            operation=lambda: self._guard(
                lambda: self._create_output_profile_version_operation(command, principal)
            ),
        )

    def set_output_profile_active(
        self,
        command: SetOutputProfileActive,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = self._request(
            command.command_id,
            "MILKING_OUTPUT_PROFILE_SET_ACTIVE",
            expected_version=command.expected_version,
        )
        payload = {
            "profile_id": command.profile_id,
            "profile_version": command.profile_version,
            "is_active": command.is_active,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_PROFILE_MANAGE),
            operation=lambda: self._guard(
                lambda: self._set_output_profile_active_operation(command, principal)
            ),
        )

    def create_configuration(
        self,
        command: CreateMilkingConfiguration,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = self._request(command.command_id, "MILKING_CONFIGURATION_CREATE")
        payload = {
            "farm_id": command.farm_id,
            "shift_code": command.shift_code,
            "output_profile_id": command.output_profile_id,
            "output_profile_version": command.output_profile_version,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CONFIG_MANAGE),
            operation=lambda: self._guard(
                lambda: self._create_configuration_operation(command, principal)
            ),
        )

    def update_configuration(
        self,
        command: UpdateMilkingConfiguration,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CommandExecutionOutcome:
        request = self._request(
            command.command_id,
            "MILKING_CONFIGURATION_UPDATE",
            expected_version=command.expected_version,
        )
        payload = {
            "configuration_id": command.configuration_id,
            "output_profile_id": command.output_profile_id,
            "output_profile_version": command.output_profile_version,
            "is_active": command.is_active,
            "client_occurred_at": command.client_occurred_at,
            "client_instance_id": command.client_instance_id,
        }
        return self._commands.execute(
            request,
            payload,
            authorize=self._authorizer(principal, PERM_CONFIG_MANAGE),
            operation=lambda: self._guard(
                lambda: self._update_configuration_operation(command, principal)
            ),
        )

    def list_output_profiles(
        self,
        *,
        principal: AuthenticatedPrincipal,
        profile_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingOutputProfile, ...]:
        tenant_id, company_id = self._read_context(principal, PERM_PROFILE_READ)
        return tuple(
            self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
                lambda: self._repository.list_output_profiles(
                    company_id=company_id,
                    profile_id=profile_id,
                    active=active,
                    limit=limit,
                    offset=offset,
                )
            )
        )

    def list_configurations(
        self,
        *,
        principal: AuthenticatedPrincipal,
        farm_id: UUID | None = None,
        active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MilkingConfiguration, ...]:
        tenant_id, company_id = self._read_context(principal, PERM_CONFIG_READ)
        return tuple(
            self._transaction_factory.for_tenant(TenantContext(tenant_id)).run(
                lambda: self._repository.list_configurations(
                    company_id=company_id,
                    farm_id=farm_id,
                    active=active,
                    limit=limit,
                    offset=offset,
                )
            )
        )

    def _create_output_profile_operation(
        self,
        command: CreateOutputProfile,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        profile = MilkingOutputProfile(
            profile_id=uuid4(),
            profile_version=1,
            company_id=company_id,
            product_id=command.product_id,
            quantity_uom_id=command.quantity_uom_id,
            is_active=True,
            row_version=1,
            created_at=self._clock.now(),
            created_by=principal.user_id,
        )
        self._repository.insert_output_profile(profile)
        return self._profile_result(profile, "MILKING_OUTPUT_PROFILE_CREATED")

    def _create_output_profile_version_operation(
        self,
        command: CreateOutputProfileVersion,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        latest = self._repository.latest_output_profile(
            company_id=company_id,
            profile_id=command.profile_id,
        )
        if latest is None:
            raise resource_not_available()
        profile = MilkingOutputProfile(
            profile_id=command.profile_id,
            profile_version=latest.profile_version + 1,
            company_id=company_id,
            product_id=command.product_id,
            quantity_uom_id=command.quantity_uom_id,
            is_active=True,
            row_version=1,
            created_at=self._clock.now(),
            created_by=principal.user_id,
        )
        self._repository.insert_output_profile(profile)
        return self._profile_result(profile, "MILKING_OUTPUT_PROFILE_VERSION_CREATED")

    def _set_output_profile_active_operation(
        self,
        command: SetOutputProfileActive,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        profile = self._repository.get_output_profile(
            company_id=company_id,
            profile_id=command.profile_id,
            profile_version=command.profile_version,
        )
        if profile is None:
            raise resource_not_available()
        if not command.is_active and self._repository.has_active_configuration_for_profile(
            company_id=company_id,
            profile_id=command.profile_id,
            profile_version=command.profile_version,
        ):
            raise business_conflict("OUTPUT_PROFILE_IN_USE")
        next_version = self._repository.update_output_profile_active(
            company_id=company_id,
            profile_id=command.profile_id,
            profile_version=command.profile_version,
            expected_row_version=command.expected_version,
            is_active=command.is_active,
        )
        changed = profile.with_active(
            active=command.is_active,
            expected_row_version=command.expected_version,
        )
        if changed.row_version != next_version:
            raise RuntimeError("Milking output profile domain/database version diverged")
        return self._profile_result(changed, "MILKING_OUTPUT_PROFILE_UPDATED")

    def _create_configuration_operation(
        self,
        command: CreateMilkingConfiguration,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        self._require_active_profile(
            company_id,
            command.output_profile_id,
            command.output_profile_version,
        )
        configuration = MilkingConfiguration(
            id=uuid4(),
            company_id=company_id,
            farm_id=command.farm_id,
            shift_code=command.shift_code,
            output_profile_id=command.output_profile_id,
            output_profile_version=command.output_profile_version,
            is_active=True,
            version=1,
            created_at=self._clock.now(),
            created_by=principal.user_id,
        )
        self._repository.insert_configuration(configuration)
        return self._configuration_result(configuration, "MILKING_CONFIGURATION_CREATED")

    def _update_configuration_operation(
        self,
        command: UpdateMilkingConfiguration,
        principal: AuthenticatedPrincipal,
    ) -> CommandResult:
        company_id = self._company_id(principal)
        current = self._repository.get_configuration_by_id(
            company_id=company_id,
            configuration_id=command.configuration_id,
        )
        if current is None:
            raise resource_not_available()
        next_profile_id = command.output_profile_id or current.output_profile_id
        next_profile_version = (
            command.output_profile_version
            if command.output_profile_version is not None
            else current.output_profile_version
        )
        next_active = current.is_active if command.is_active is None else command.is_active
        profile_is_changed = command.output_profile_id is not None
        if next_active or profile_is_changed:
            self._require_active_profile(company_id, next_profile_id, next_profile_version)
        changed = current.update(
            output_profile_id=command.output_profile_id,
            output_profile_version=command.output_profile_version,
            is_active=command.is_active,
            expected_version=command.expected_version,
            actor_user_id=principal.user_id,
            occurred_at=self._clock.now(),
        )
        self._repository.update_configuration(
            changed,
            expected_version=command.expected_version,
        )
        return self._configuration_result(changed, "MILKING_CONFIGURATION_UPDATED")

    def _require_active_profile(
        self,
        company_id: UUID,
        profile_id: UUID,
        profile_version: int,
    ) -> MilkingOutputProfile:
        profile = self._repository.get_output_profile(
            company_id=company_id,
            profile_id=profile_id,
            profile_version=profile_version,
        )
        if profile is None or not profile.is_active:
            raise resource_not_available()
        return profile

    @staticmethod
    def _profile_result(profile: MilkingOutputProfile, code: str) -> CommandResult:
        return CommandResult(
            code,
            {
                "profile_id": str(profile.profile_id),
                "profile_version": profile.profile_version,
                "version": profile.row_version,
                "is_active": profile.is_active,
            },
        )

    @staticmethod
    def _configuration_result(
        configuration: MilkingConfiguration,
        code: str,
    ) -> CommandResult:
        return CommandResult(
            code,
            {
                "configuration_id": str(configuration.id),
                "version": configuration.version,
                "is_active": configuration.is_active,
                "farm_id": str(configuration.farm_id),
                "shift_code": configuration.shift_code,
                "output_profile_id": str(configuration.output_profile_id),
                "output_profile_version": configuration.output_profile_version,
            },
        )

    @staticmethod
    def _request(
        command_id: UUID,
        command_name: str,
        *,
        expected_version: int | None = None,
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
            if (
                not principal.has_operational_context
                or permission not in principal.effective_permissions
            ):
                raise access_denied()
            return principal

        return authorize

    @staticmethod
    def _read_context(
        principal: AuthenticatedPrincipal,
        permission: str,
    ) -> tuple[UUID, UUID]:
        if (
            principal.tenant_id is None
            or principal.company_id is None
            or permission not in principal.effective_permissions
        ):
            raise access_denied()
        return principal.tenant_id, principal.company_id

    @staticmethod
    def _company_id(principal: AuthenticatedPrincipal) -> UUID:
        if principal.tenant_id is None or principal.company_id is None:
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
