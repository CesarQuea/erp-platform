from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings


class FakeDatabaseRuntime:
    def __init__(self, ready: bool):
        self._ready = ready
        self.disposed = False

    def check_ready(self) -> bool:
        return self._ready

    def dispose(self) -> None:
        self.disposed = True


class FakeDatabaseRuntimeFactory:
    def __init__(self, ready: bool):
        self.runtime = FakeDatabaseRuntime(ready)

    def __call__(self, settings: Settings) -> FakeDatabaseRuntime:
        return self.runtime


def _client(*, ready: bool, database_url: str | None = None) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=database_url,
    )
    factory = FakeDatabaseRuntimeFactory(ready)
    return TestClient(
        create_app(
            settings=settings,
            database_runtime_factory=factory,
        )
    )


def test_live_returns_correlation_id():
    with _client(ready=False) as client:
        response = client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["X-Correlation-ID"]


def test_valid_client_correlation_id_is_preserved():
    with _client(ready=False) as client:
        response = client.get(
            "/api/v1/live",
            headers={"X-Correlation-ID": "client-request-123"},
        )

    assert response.headers["X-Correlation-ID"] == "client-request-123"


def test_invalid_client_correlation_id_is_replaced():
    with _client(ready=False) as client:
        response = client.get(
            "/api/v1/live",
            headers={"X-Correlation-ID": "secret value with spaces"},
        )

    assert response.headers["X-Correlation-ID"] != "secret value with spaces"


def test_ready_returns_200_when_database_is_ready():
    with _client(ready=True) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}


def test_ready_returns_safe_error_when_database_is_unavailable():
    with _client(ready=False) as client:
        response = client.get("/api/v1/ready")

    payload = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "PLATFORM_NOT_READY"
    assert payload["error"]["correlation_id"]
    assert "DATABASE_URL" not in response.text


def test_health_is_read_only_safe_summary_and_does_not_expose_secret():
    database_url = "postgresql://user:very-secret-password@db.example/erp"

    with _client(ready=False, database_url=database_url) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "service": "erp-platform",
        "environment": "test",
        "database": "unavailable",
    }
    assert "very-secret-password" not in response.text
    assert database_url not in response.text


def test_legacy_db_info_endpoint_is_removed():
    with _client(ready=True) as client:
        response = client.get("/db-info")

    assert response.status_code == 404
