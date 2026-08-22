from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import ConfigurationError, Settings
from app.platform.identity.model import AuthenticatedPrincipal, UserAccount, UserStatus
from app.platform.identity.service import AuthorizedContext, ContextToken, TokenPair


TEST_REFRESH_TOKEN = "r" * 43


class FakeDatabaseRuntime:
    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


class FakeIdentityAuthentication:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.session_id = uuid4()
        self.tenant_id = uuid4()
        self.company_id = uuid4()
        self.now = datetime.now(UTC)

    def _pair(self) -> TokenPair:
        return TokenPair(
            access_token="access-token",
            refresh_token=TEST_REFRESH_TOKEN,
            session_id=self.session_id,
            access_expires_at=self.now + timedelta(minutes=15),
            refresh_expires_at=self.now + timedelta(days=30),
        )

    def login(self, **kwargs) -> TokenPair:
        return self._pair()

    def refresh(self, refresh_token: str) -> TokenPair:
        return self._pair()

    def principal_from_access_token(self, token: str) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            user_id=self.user_id,
            session_id=self.session_id,
        )

    def logout(self, token: str) -> None:
        pass

    def get_user(self, principal: AuthenticatedPrincipal) -> UserAccount:
        return UserAccount(
            id=self.user_id,
            login="ana",
            login_normalized="ana",
            display_name="Ana",
            email="ana@example.com",
            status=UserStatus.ACTIVE,
            created_at=self.now,
            updated_at=self.now,
        )

    def list_contexts(self, principal: AuthenticatedPrincipal):
        return [
            AuthorizedContext(
                tenant_id=self.tenant_id,
                company_id=self.company_id,
                company_code="A1",
                company_name="Company A1",
            )
        ]

    def select_context(self, principal, *, tenant_id, company_id):
        return ContextToken(
            access_token="operational-token",
            expires_at=self.now + timedelta(minutes=15),
        )


class FakeIdentityRuntime:
    def __init__(self) -> None:
        self.authentication = FakeIdentityAuthentication()

    def dispose(self) -> None:
        pass


class FakeTenantRuntime:
    def dispose(self) -> None:
        pass


def _client(identity_runtime):
    return TestClient(
        create_app(
            settings=Settings(environment="test"),
            database_runtime_factory=lambda settings: FakeDatabaseRuntime(),
            tenant_platform_factory=lambda settings: FakeTenantRuntime(),
            identity_platform_factory=lambda settings, tenant: identity_runtime,
        )
    )


def test_auth_endpoints_are_wired_without_exposing_tenant_database_details() -> None:
    runtime = FakeIdentityRuntime()
    with _client(runtime) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"login": "ana", "password": "12345678!"},
        )
        assert login.status_code == 200
        assert login.json()["access_token"] == "access-token"

        headers = {"Authorization": "Bearer access-token"}
        me = client.get("/api/v1/auth/me", headers=headers)
        contexts = client.get("/api/v1/auth/contexts", headers=headers)
        selected = client.post(
            "/api/v1/auth/context",
            headers=headers,
            json={
                "tenant_id": str(runtime.authentication.tenant_id),
                "company_id": str(runtime.authentication.company_id),
            },
        )
        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": TEST_REFRESH_TOKEN},
        )
        logout = client.post("/api/v1/auth/logout", headers=headers)

    assert me.status_code == 200
    assert contexts.status_code == 200
    assert contexts.json()[0]["company_code"] == "A1"
    assert selected.json()["access_token"] == "operational-token"
    assert refreshed.status_code == 200
    assert logout.json() == {"status": "logged_out"}
    combined = " ".join(
        [login.text, me.text, contexts.text, selected.text, refreshed.text]
    )
    assert "postgresql://" not in combined
    assert "database_url" not in combined


def test_auth_fails_closed_when_identity_runtime_is_not_configured() -> None:
    with _client(None) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "ana", "password": "12345678!"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "IDENTITY_UNAVAILABLE"


def test_missing_bearer_token_is_401() -> None:
    with _client(FakeIdentityRuntime()) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_validation_errors_never_reflect_password_or_refresh_token() -> None:
    password_marker = "PASSWORD-MUST-NEVER-BE-REFLECTED-" + ("x" * 160)
    refresh_marker = "REFRESH-MUST-NEVER-BE-REFLECTED-" + ("y" * 600)
    with _client(FakeIdentityRuntime()) as client:
        invalid_login = client.post(
            "/api/v1/auth/login",
            json={"login": "ana", "password": password_marker},
        )
        invalid_refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_marker},
        )

    for response, marker in (
        (invalid_login, password_marker),
        (invalid_refresh, refresh_marker),
    ):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
        assert marker not in response.text
        assert "input" not in response.text.lower()


def test_identity_secrets_are_hidden_and_short_secrets_rejected() -> None:
    settings = Settings(
        environment="test",
        jwt_signing_secret="x" * 32,
    )
    assert "x" * 32 not in repr(settings)
    try:
        Settings(environment="test", jwt_signing_secret="short")
    except ConfigurationError:
        pass
    else:
        raise AssertionError("short JWT signing secret must be rejected")
