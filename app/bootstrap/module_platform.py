from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.tenant_platform import TenantPlatformRuntime
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.module_repository import SqlAlchemyModuleActivationRepository
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.modules.milking.module import MILKING_MODULE_DEFINITION
from app.platform.commands.service import CommandExecutionService
from app.platform.modules.registry import ModuleRegistry
from app.platform.modules.service import ModuleActivationService, ModuleAvailabilityService


@dataclass(slots=True)
class ModulePlatformRuntime:
    registry: ModuleRegistry
    availability: ModuleAvailabilityService | None
    activations: ModuleActivationService | None

    def dispose(self) -> None:
        # Tenant engines remain owned by TenantPlatformRuntime.
        pass


def build_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(MILKING_MODULE_DEFINITION)
    registry.freeze()
    return registry


def build_module_platform(
    tenant_platform: TenantPlatformRuntime,
) -> ModulePlatformRuntime:
    registry = build_module_registry()
    resolver = getattr(tenant_platform, "resolver", None)
    if resolver is None:
        # Preserve lightweight application test doubles while still exposing
        # the deterministic registry built at bootstrap.
        return ModulePlatformRuntime(
            registry=registry,
            availability=None,
            activations=None,
        )

    session_scope = TenantSessionScope()
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    company_repository = SqlAlchemyCompanyRepository(session_scope)
    activation_repository = SqlAlchemyModuleActivationRepository(session_scope)
    command_execution = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(session_scope),
        transaction_factory,
    )

    return ModulePlatformRuntime(
        registry=registry,
        availability=ModuleAvailabilityService(
            registry,
            activation_repository,
            company_repository,
            transaction_factory,
        ),
        activations=ModuleActivationService(
            registry,
            activation_repository,
            company_repository,
            command_execution,
        ),
    )
