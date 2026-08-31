from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.contracts import (
    API_V1_PREFIX,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    PUBLIC_API_VERSION,
    CommandResponse,
    ErrorResponse,
)
from app.bootstrap.application import create_app
from app.core.config.settings import Settings


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_OPENAPI_BASELINE = _REPOSITORY_ROOT / "contracts" / "api" / "v1" / "openapi.json"


class FakeDatabaseRuntime:
    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


class FakeTenantRuntime:
    def dispose(self) -> None:
        pass


def _app():
    return create_app(
        settings=Settings(environment="test"),
        database_runtime_factory=lambda settings: FakeDatabaseRuntime(),
        tenant_platform_factory=lambda settings: FakeTenantRuntime(),
        identity_platform_factory=lambda settings, tenant: None,
        milking_platform_factory=lambda tenant: None,
    )


def test_public_api_contract_constants_are_explicit_and_separate() -> None:
    assert API_V1_PREFIX == "/api/v1"
    assert PUBLIC_API_VERSION == "1.1.0"
    assert DEFAULT_PAGE_LIMIT == 100
    assert MAX_PAGE_LIMIT == 500
    assert _app().version == PUBLIC_API_VERSION


def test_common_contract_models_preserve_existing_json_shapes() -> None:
    command = CommandResponse(code="OK", replayed=False, data={"version": 1})
    assert command.model_dump() == {
        "code": "OK",
        "replayed": False,
        "data": {"version": 1},
    }

    error = ErrorResponse.model_validate(
        {
            "error": {
                "code": "CONCURRENCY_CONFLICT",
                "message": "Conflict.",
                "correlation_id": "corr-1",
            }
        }
    )
    assert error.error.code == "CONCURRENCY_CONFLICT"
    assert error.error.correlation_id == "corr-1"


def test_openapi_exposes_v1_modules_preserves_milking_and_adds_sync_routes() -> None:
    schema = _app().openapi()
    paths = schema["paths"]

    assert schema["info"]["version"] == PUBLIC_API_VERSION
    assert "/api/v1/modules" in paths
    assert "/api/v1/modules/{module_id}/enable" in paths
    assert "/api/v1/modules/{module_id}/disable" in paths
    assert "/api/v1/milking/sessions" in paths
    assert "/api/v1/sync/{module_id}/changes" in paths
    assert "/api/v1/sync/{module_id}/bootstrap" in paths

    login_422 = paths["/api/v1/auth/login"]["post"]["responses"]["422"]
    assert "ErrorResponse" in str(login_422)
    schemas = schema["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert "CommandResponse" in schemas
    assert "ModuleStatusResponse" in schemas
    assert "SyncChangesResponse" in schemas
    assert "SyncBootstrapResponse" in schemas
    assert "description" in schemas["ModuleStatusResponse"]["properties"]

    assert set(paths["/api/v1/live"]["get"]["responses"]) == {"200", "500"}
    assert set(paths["/api/v1/ready"]["get"]["responses"]) == {"200", "500", "503"}
    assert set(paths["/api/v1/health"]["get"]["responses"]) == {"200", "500"}


def test_openapi_matches_versioned_v1_baseline_exactly() -> None:
    assert _OPENAPI_BASELINE.is_file(), "Generate contracts/api/v1/openapi.json first"
    baseline = json.loads(_OPENAPI_BASELINE.read_text(encoding="utf-8"))
    assert _app().openapi() == baseline


def test_correlation_header_is_preserved_and_validation_error_matches_body() -> None:
    app = _app()
    with TestClient(app) as client:
        health = client.get(
            "/api/v1/health",
            headers={"X-Correlation-ID": "p6-contract-123"},
        )
        invalid = client.post(
            "/api/v1/auth/login",
            headers={"X-Correlation-ID": "p6-validation-456"},
            json={"login": "user@example.test"},
        )

    assert health.status_code == 200
    assert health.headers["X-Correlation-ID"] == "p6-contract-123"

    assert invalid.status_code == 422
    assert invalid.headers["X-Correlation-ID"] == "p6-validation-456"
    body = invalid.json()["error"]
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["correlation_id"] == "p6-validation-456"
    assert "password" not in str(invalid.json()).lower()


def test_invalid_correlation_id_is_replaced_with_uuid() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Correlation-ID": "contains spaces and is invalid"},
        )
    assert response.status_code == 200
    generated = response.headers["X-Correlation-ID"]
    assert generated != "contains spaces and is invalid"
    UUID(generated)
