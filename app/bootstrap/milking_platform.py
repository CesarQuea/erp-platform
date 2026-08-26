from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.tenant_platform import TenantPlatformRuntime
from app.infrastructure.database.command_repository import SqlAlchemyCommandExecutionRepository
from app.infrastructure.database.milking_admin_repository import SqlAlchemyMilkingAdminRepository
from app.infrastructure.database.milking_query_repository import SqlAlchemyMilkingQueryRepository
from app.infrastructure.database.milking_repository import SqlAlchemyMilkingRepository
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.modules.milking.admin import MilkingAdminService
from app.modules.milking.query import MilkingQueryService
from app.modules.milking.service import MilkingCommandApplicationService
from app.platform.commands.service import CommandExecutionService


@dataclass(slots=True)
class MilkingPlatformRuntime:
    commands: MilkingCommandApplicationService
    query: MilkingQueryService
    admin: MilkingAdminService

    def dispose(self) -> None:
        # Tenant engines are owned and disposed by TenantPlatformRuntime.
        pass


def build_milking_platform(
    tenant_platform: TenantPlatformRuntime,
) -> MilkingPlatformRuntime | None:
    # Test doubles used by pre-existing Platform API tests intentionally do not
    # expose a datasource resolver. In production TenantPlatformRuntime always does.
    resolver = getattr(tenant_platform, "resolver", None)
    if resolver is None:
        return None

    session_scope = TenantSessionScope()
    transaction_factory = SqlAlchemyTenantTransactionBoundaryFactory(
        resolver,
        session_scope,
    )
    command_execution = CommandExecutionService(
        SqlAlchemyCommandExecutionRepository(session_scope),
        transaction_factory,
    )

    command_repository = SqlAlchemyMilkingRepository(session_scope)
    query_repository = SqlAlchemyMilkingQueryRepository(session_scope)
    admin_repository = SqlAlchemyMilkingAdminRepository(session_scope)

    return MilkingPlatformRuntime(
        commands=MilkingCommandApplicationService(
            command_repository,
            command_execution,
        ),
        query=MilkingQueryService(
            query_repository,
            transaction_factory,
        ),
        admin=MilkingAdminService(
            admin_repository,
            command_execution,
            transaction_factory,
        ),
    )
