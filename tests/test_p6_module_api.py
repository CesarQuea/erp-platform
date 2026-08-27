from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings
from app.platform.commands.model import CommandExecutionOutcome, CommandResult
from app.platform.identity.errors import access_denied
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.model import (
    CompanyModuleStatus,
    ModuleActivationState,
    ModuleDefinition,
)
from app.platform.modules.service import PERM_MANAGE_MODULES


class FakeDatabaseRuntime:
    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


class FakeTenantRuntime:
    def dispose(self) -> None:
        pass


class FakeAuthentication:
    def __init__(self, *, operational: bool = True, manage: bool = False) -> None:
        self.tenant_id = uuid4() if operational else None
        self.company_id = uuid4() if operational else None
        permissions = {PERM_MANAGE_MODULES} if manage else set()
        self.principal = AuthenticatedPrincipal(
            user_id=uuid4(),
            session_id=uuid4(),
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            effective_permissions=frozenset(permissions),
        )

    def principal_from_access_token(self, token: str) -> AuthenticatedPrincipal:
        assert token == "p6-token"
        return self.principal


class FakeIdentityRuntime:
    def __init__(self, **kwargs) -> None:
        self.authentication = FakeAuthentication(**kwargs)

    def dispose(self) -> None:
        pass


class FakeAvailability:
    definition = ModuleDefinition(
        module_id="milking",
        module_version="1.0.0",
        configuration_namespace="milking",
        description="Milking",
    )

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.last_context = None
        self.last_company_id = None

    def list_company_modules(self, context, company_id):
        self.last_context = context
        self.last_company_id = company_id
        return (
            CompanyModuleStatus(
                definition=self.definition,
                state=(
                    ModuleActivationState.ENABLED
                    if self.enabled
                    else ModuleActivationState.DISABLED
                ),
                version=1 if self.enabled else 0,
                activation_present=self.enabled,
                effective_enabled=self.enabled,
            ),
        )

    def require_enabled(self, context, company_id, module_id):
        raise AssertionError("Milking enforcement is not exercised by module API tests")


class FakeActivations:
    def __init__(self) -> None:
        self.last_command = None
        self.last_principal = None
        self.state = ModuleActivationState.DISABLED
        self.version = 0

    def _require_manage(self, principal):
        if PERM_MANAGE_MODULES not in principal.effective_permissions:
            raise access_denied()

    def enable_module(self, command, *, principal):
        self._require_manage(principal)
        self.last_command = command
        self.last_principal = principal
        self.state = ModuleActivationState.ENABLED
        self.version = 1
        return CommandExecutionOutcome(
            result=CommandResult(
                "MODULE_ACTIVATION_CHANGED",
                {
                    "module_id": command.module_id,
                    "state": self.state.value,
                    "version": self.version,
                    "changed": True,
                },
            ),
            replayed=False,
        )

    def disable_module(self, command, *, principal):
        self._require_manage(principal)
        self.last_command = command
        self.last_principal = principal
        self.state = ModuleActivationState.DISABLED
        self.version = max(self.version + 1, 1)
        return CommandExecutionOutcome(
            result=CommandResult(
                "MODULE_ACTIVATION_CHANGED",
                {
                    "module_id": command.module_id,
                    "state": self.state.value,
                    "version": self.version,
                    "changed": True,
                },
            ),
            replayed=False,
        )


class FakeModuleRuntime:
    def __init__(self, *, enabled: bool = False) -> None:
        self.availability = FakeAvailability(enabled=enabled)
        self.activations = FakeActivations()

    def dispose(self) -> None:
        pass


def _client(*, operational: bool = True, manage: bool = False, enabled: bool = False):
    identity = FakeIdentityRuntime(operational=operational, manage=manage)
    modules = FakeModuleRuntime(enabled=enabled)
    app = create_app(
        settings=Settings(environment="test"),
        database_runtime_factory=lambda settings: FakeDatabaseRuntime(),
        tenant_platform_factory=lambda settings: FakeTenantRuntime(),
        identity_platform_factory=lambda settings, tenant: identity,
        milking_platform_factory=lambda tenant: None,
        module_platform_factory=lambda tenant: modules,
    )
    return TestClient(app), identity, modules


def _headers():
    return {"Authorization": "Bearer p6-token"}


def test_get_modules_uses_only_authenticated_operational_company_context() -> None:
    client, identity, modules = _client()
    with client:
        response = client.get("/api/v1/modules", headers=_headers())

    assert response.status_code == 200
    assert response.json() == [
        {
            "module_id": "milking",
            "module_version": "1.0.0",
            "description": "Milking",
            "state": "DISABLED",
            "version": 0,
            "activation_present": False,
            "effective_enabled": False,
        }
    ]
    assert modules.availability.last_context.tenant_id == identity.authentication.tenant_id
    assert modules.availability.last_company_id == identity.authentication.company_id


def test_get_modules_requires_operational_context() -> None:
    client, _, _ = _client(operational=False)
    with client:
        response = client.get("/api/v1/modules", headers=_headers())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"


def test_enable_module_requires_platform_manage_permission() -> None:
    client, _, modules = _client(manage=False)
    with client:
        response = client.post(
            "/api/v1/modules/milking/enable",
            headers=_headers(),
            json={"command_id": str(uuid4()), "expected_version": 0},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
    assert modules.activations.last_command is None


def test_enable_module_preserves_p4_command_response_shape() -> None:
    client, identity, modules = _client(manage=True)
    command_id = uuid4()
    with client:
        response = client.post(
            "/api/v1/modules/milking/enable",
            headers=_headers(),
            json={"command_id": str(command_id), "expected_version": 0},
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "MODULE_ACTIVATION_CHANGED",
        "replayed": False,
        "data": {
            "module_id": "milking",
            "state": "ENABLED",
            "version": 1,
            "changed": True,
        },
    }
    assert modules.activations.last_command.command_id == command_id
    assert modules.activations.last_command.expected_version == 0
    assert modules.activations.last_principal == identity.authentication.principal


def test_invalid_module_path_is_sanitized_422_before_activation_service() -> None:
    client, _, modules = _client(manage=True)
    correlation_id = "p6-invalid-module"
    with client:
        response = client.post(
            "/api/v1/modules/INVALID MODULE/enable",
            headers={**_headers(), "X-Correlation-ID": correlation_id},
            json={"command_id": str(uuid4()), "expected_version": 0},
        )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "Request validation failed.",
            "correlation_id": correlation_id,
        }
    }
    assert modules.activations.last_command is None


def test_module_activation_request_rejects_negative_expected_version() -> None:
    client, _, modules = _client(manage=True)
    with client:
        response = client.post(
            "/api/v1/modules/milking/enable",
            headers=_headers(),
            json={"command_id": str(uuid4()), "expected_version": -1},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert modules.activations.last_command is None
