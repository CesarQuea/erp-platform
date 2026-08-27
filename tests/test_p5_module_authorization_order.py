from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors.models import PlatformError
from app.platform.commands.service import CommandExecutionService
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.model import ChangeModuleActivation, ModuleDefinition
from app.platform.modules.registry import ModuleRegistry
from app.platform.modules.service import ModuleActivationService


class FailIfCommandRepositoryUsed:
    def claim(self, record):
        raise AssertionError("authorization must fail before command claim")

    def get(self, command_id):
        raise AssertionError("authorization must fail before replay lookup")

    def complete(self, command_id, *, result_code, result_json, committed_at):
        raise AssertionError("authorization must fail before command completion")


class FailIfTransactionFactoryUsed:
    def for_tenant(self, context):
        raise AssertionError("authorization must fail before tenant transaction")


class FailIfActivationRepositoryUsed:
    def __getattr__(self, name):
        raise AssertionError(f"activation repository must not be used: {name}")


class FailIfCompanyRepositoryUsed:
    def __getattr__(self, name):
        raise AssertionError(f"company repository must not be used: {name}")


def test_unauthorized_caller_cannot_probe_unknown_module_registration() -> None:
    registry = ModuleRegistry(
        [ModuleDefinition("milking", "1.0.0", "milking")]
    )
    registry.freeze()
    commands = CommandExecutionService(
        FailIfCommandRepositoryUsed(),
        FailIfTransactionFactoryUsed(),
    )
    service = ModuleActivationService(
        registry,
        FailIfActivationRepositoryUsed(),
        FailIfCompanyRepositoryUsed(),
        commands,
    )
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        company_id=uuid4(),
        effective_permissions=frozenset(),
    )

    with pytest.raises(PlatformError) as exc:
        service.enable_module(
            ChangeModuleActivation(uuid4(), "inventory", 0),
            principal=principal,
        )

    assert exc.value.code == "ACCESS_DENIED"
