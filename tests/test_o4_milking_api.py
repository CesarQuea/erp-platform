from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings
from app.platform.commands.model import CommandExecutionOutcome, CommandResult
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.errors import module_not_enabled


ALL_MILKING_PERMISSIONS = frozenset(
    {
        "milking.session.create",
        "milking.session.update_draft",
        "milking.session.confirm",
        "milking.session.cancel",
        "milking.session.read",
        "milking.config.read",
        "milking.config.manage",
        "milking.output_profile.read",
        "milking.output_profile.manage",
    }
)


class FakeDatabaseRuntime:
    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


class FakeTenantRuntime:
    def dispose(self) -> None:
        pass


class FakeAuthentication:
    def __init__(self, permissions=ALL_MILKING_PERMISSIONS) -> None:
        self.user_id = uuid4()
        self.session_id = uuid4()
        self.tenant_id = uuid4()
        self.company_id = uuid4()
        self.permissions = permissions

    def principal_from_access_token(self, token: str) -> AuthenticatedPrincipal:
        assert token == "operational-token"
        return AuthenticatedPrincipal(
            user_id=self.user_id,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            effective_permissions=self.permissions,
        )


class FakeIdentityRuntime:
    def __init__(self, permissions=ALL_MILKING_PERMISSIONS) -> None:
        self.authentication = FakeAuthentication(permissions)

    def dispose(self) -> None:
        pass


class FakeModuleAvailability:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls = 0

    def require_enabled(self, context, company_id, module_id):
        self.calls += 1
        assert module_id == "milking"
        if not self.enabled:
            raise module_not_enabled()
        return None


class FakeModuleRuntime:
    def __init__(self, *, enabled: bool = True) -> None:
        self.availability = FakeModuleAvailability(enabled=enabled)
        self.activations = None

    def dispose(self) -> None:
        pass


class FakeCommands:
    def __init__(self) -> None:
        self.last_principal: AuthenticatedPrincipal | None = None
        self.last_command = None

    def _outcome(self, command, principal) -> CommandExecutionOutcome:
        self.last_command = command
        self.last_principal = principal
        return CommandExecutionOutcome(
            result=CommandResult(
                "MILKING_TEST_OK",
                {
                    "session_id": str(uuid4()),
                    "version": 1,
                    "status": "DRAFT",
                    "output_id": None,
                },
            ),
            replayed=False,
        )

    def create_session(self, command, *, principal):
        return self._outcome(command, principal)

    def set_general(self, command, *, principal):
        return self._outcome(command, principal)

    def set_notes(self, command, *, principal):
        return self._outcome(command, principal)

    def set_use_discard(self, command, *, principal):
        return self._outcome(command, principal)

    def confirm(self, command, *, principal):
        return self._outcome(command, principal)

    def cancel_draft(self, command, *, principal):
        return self._outcome(command, principal)

    def request_annulment(self, command, *, principal):
        return self._outcome(command, principal)


class FakeQuery:
    def __init__(self) -> None:
        self.last_principal: AuthenticatedPrincipal | None = None

    def list_sessions(self, *, principal, **kwargs):
        self.last_principal = principal
        return ()

    def list_outputs(self, *, principal, **kwargs):
        self.last_principal = principal
        return ()


class FakeAdmin:
    def __init__(self) -> None:
        self.last_principal: AuthenticatedPrincipal | None = None

    def list_output_profiles(self, *, principal, **kwargs):
        self.last_principal = principal
        return ()

    def list_configurations(self, *, principal, **kwargs):
        self.last_principal = principal
        return ()

    def create_output_profile(self, command, *, principal):
        self.last_principal = principal
        return CommandExecutionOutcome(
            result=CommandResult(
                "MILKING_OUTPUT_PROFILE_CREATED",
                {
                    "profile_id": str(uuid4()),
                    "profile_version": 1,
                    "version": 1,
                    "is_active": True,
                },
            ),
            replayed=False,
        )


class FakeMilkingRuntime:
    def __init__(self) -> None:
        self.commands = FakeCommands()
        self.query = FakeQuery()
        self.admin = FakeAdmin()

    def dispose(self) -> None:
        pass


def _client(
    *,
    milking_runtime=None,
    permissions=ALL_MILKING_PERMISSIONS,
    module_enabled: bool = True,
):
    identity = FakeIdentityRuntime(permissions)
    runtime = milking_runtime if milking_runtime is not None else FakeMilkingRuntime()
    modules = FakeModuleRuntime(enabled=module_enabled)
    app = create_app(
        settings=Settings(environment="test"),
        database_runtime_factory=lambda settings: FakeDatabaseRuntime(),
        tenant_platform_factory=lambda settings: FakeTenantRuntime(),
        identity_platform_factory=lambda settings, tenant: identity,
        milking_platform_factory=lambda tenant: runtime,
        module_platform_factory=lambda tenant: modules,
    )
    return TestClient(app), identity, runtime, modules


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer operational-token"}


def _base_command() -> dict[str, object]:
    return {
        "command_id": str(uuid4()),
        "client_occurred_at": datetime.now(UTC).isoformat(),
        "client_instance_id": "android-test",
    }


def test_create_session_uses_authenticated_company_context_not_client_authority() -> None:
    client, identity, runtime, modules = _client()
    payload = {
        **_base_command(),
        "farm_id": str(uuid4()),
        "milking_date": date.today().isoformat(),
        "shift_code": "MORNING",
    }
    with client:
        response = client.post("/api/v1/milking/sessions", headers=_headers(), json=payload)

    assert response.status_code == 200
    assert response.json()["code"] == "MILKING_TEST_OK"
    assert modules.availability.calls == 1
    principal = runtime.commands.last_principal
    assert principal is not None
    assert principal.tenant_id == identity.authentication.tenant_id
    assert principal.company_id == identity.authentication.company_id
    assert not hasattr(runtime.commands.last_command, "company_id")
    assert not hasattr(runtime.commands.last_command, "actor_id")


def test_milking_endpoints_require_bearer_authentication() -> None:
    client, _, _, _ = _client()
    with client:
        response = client.get("/api/v1/milking/sessions")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_milking_read_is_company_context_scoped_through_principal() -> None:
    client, identity, runtime, _ = _client()
    with client:
        response = client.get("/api/v1/milking/sessions", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert runtime.query.last_principal.company_id == identity.authentication.company_id


def test_minimal_administration_routes_are_exposed() -> None:
    client, _, runtime, _ = _client()
    profile_payload = {
        **_base_command(),
        "product_id": str(uuid4()),
        "quantity_uom_id": str(uuid4()),
    }
    with client:
        created = client.post(
            "/api/v1/milking/output-profiles",
            headers=_headers(),
            json=profile_payload,
        )
        profiles = client.get("/api/v1/milking/output-profiles", headers=_headers())
        configurations = client.get("/api/v1/milking/configurations", headers=_headers())

    assert created.status_code == 200
    assert created.json()["code"] == "MILKING_OUTPUT_PROFILE_CREATED"
    assert profiles.status_code == 200 and profiles.json() == []
    assert configurations.status_code == 200 and configurations.json() == []
    assert runtime.admin.last_principal is not None


def test_no_generic_commands_endpoint_is_exposed() -> None:
    client, _, _, _ = _client()
    with client:
        response = client.post(
            "/api/v1/milking/commands",
            headers=_headers(),
            json=_base_command(),
        )
    assert response.status_code == 404


def test_milking_fails_closed_when_runtime_is_unavailable() -> None:
    identity = FakeIdentityRuntime()
    modules = FakeModuleRuntime(enabled=True)
    app = create_app(
        settings=Settings(environment="test"),
        database_runtime_factory=lambda settings: FakeDatabaseRuntime(),
        tenant_platform_factory=lambda settings: FakeTenantRuntime(),
        identity_platform_factory=lambda settings, tenant: identity,
        milking_platform_factory=lambda tenant: None,
        module_platform_factory=lambda tenant: modules,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/milking/sessions", headers=_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MILKING_UNAVAILABLE"


def test_milking_is_blocked_before_domain_when_module_is_disabled() -> None:
    client, _, runtime, modules = _client(module_enabled=False)
    with client:
        response = client.get("/api/v1/milking/sessions", headers=_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODULE_NOT_ENABLED"
    assert modules.availability.calls == 1
    assert runtime.query.last_principal is None


def test_naive_client_timestamp_is_rejected_before_service_execution() -> None:
    client, _, runtime, _ = _client()
    payload = {
        "command_id": str(uuid4()),
        "client_occurred_at": "2026-08-25T08:00:00",
        "farm_id": str(uuid4()),
        "milking_date": "2026-08-25",
        "shift_code": "MORNING",
    }
    with client:
        response = client.post("/api/v1/milking/sessions", headers=_headers(), json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert runtime.commands.last_command is None
