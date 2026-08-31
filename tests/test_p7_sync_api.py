from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings
from app.platform.identity.errors import access_denied
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.errors import module_not_enabled
from app.platform.modules.model import ModuleDefinition
from app.platform.modules.registry import ModuleRegistry
from app.platform.sync.model import (
    BootstrapPage,
    SyncBatch,
    SyncChange,
    SyncChangeKind,
    SyncProjection,
)
from app.platform.sync.provider import SyncProvider
from app.platform.sync.query import SyncQueryService
from app.platform.sync.registry import SyncProviderRegistry
from app.platform.sync.token import SyncTokenCodec


class _DatabaseRuntime:
    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


class _TenantRuntime:
    def dispose(self) -> None:
        pass


class _ModuleRuntime:
    def dispose(self) -> None:
        pass


class _Authentication:
    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self.principal = principal

    def principal_from_access_token(self, token: str) -> AuthenticatedPrincipal:
        assert token == "p7-token"
        return self.principal


class _IdentityRuntime:
    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self.authentication = _Authentication(principal)

    def dispose(self) -> None:
        pass


class _Boundary:
    def run(self, operation):
        return operation()


class _Transactions:
    def for_tenant(self, context):
        del context
        return _Boundary()


class _Availability:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls: list[tuple[UUID, UUID, str]] = []

    def require_enabled(self, context, company_id: UUID, module_id: str):
        self.calls.append((context.tenant_id, company_id, module_id))
        if not self.enabled:
            raise module_not_enabled()


class _Journal:
    def __init__(self, company_id: UUID) -> None:
        self.position = 1
        entity_id = uuid4()
        self.batches = (
            SyncBatch(
                batch_id=uuid4(),
                company_id=company_id,
                module_id="testsync",
                stream_id="default",
                position=1,
                sync_protocol_version="1",
                recorded_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
                changes=(
                    SyncChange(
                        entity_type="record",
                        entity_id=entity_id,
                        change_kind=SyncChangeKind.UPSERT,
                        schema_version="1",
                        entity_version=1,
                        payload={"id": str(entity_id), "name": "value"},
                    ),
                ),
            ),
        )

    def current_position(self, *, company_id, module_id, stream_id):
        del company_id, module_id, stream_id
        return self.position

    def list_batches(
        self,
        *,
        company_id,
        module_id,
        stream_id,
        after_position: int,
        limit: int,
    ):
        del company_id, module_id, stream_id
        return tuple(batch for batch in self.batches if batch.position > after_position)[:limit]


class _Provider:
    module_id = "testsync"
    stream_ids = ("default",)

    def __init__(self) -> None:
        self.authorize_calls = 0
        entity_id = uuid4()
        self.projection = SyncProjection(
            entity_type="record",
            entity_id=entity_id,
            schema_version="1",
            entity_version=1,
            payload={"id": str(entity_id), "name": "baseline"},
        )

    def authorize(self, *, principal, stream_id: str) -> None:
        assert stream_id == "default"
        self.authorize_calls += 1
        if "testsync.read" not in principal.effective_permissions:
            raise access_denied()

    def bootstrap_page(
        self,
        *,
        principal,
        stream_id: str,
        after_key: str | None,
        limit: int,
    ) -> BootstrapPage:
        del principal, limit
        assert stream_id == "default"
        if after_key is None:
            return BootstrapPage(items=(self.projection,), next_key=None, has_more=False)
        return BootstrapPage(items=(), next_key=None, has_more=False)


class _SyncRuntime:
    def __init__(self, query: SyncQueryService) -> None:
        self.query = query

    def dispose(self) -> None:
        pass


def _module_registry() -> ModuleRegistry:
    registry = ModuleRegistry(
        [
            ModuleDefinition(
                module_id="testsync",
                module_version="1.0.0",
                configuration_namespace="testsync",
            )
        ]
    )
    registry.freeze()
    return registry


def _principal(
    *,
    tenant_id: UUID | None = None,
    company_id: UUID | None = None,
    operational: bool = True,
    readable: bool = True,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=(tenant_id or uuid4()) if operational else None,
        company_id=(company_id or uuid4()) if operational else None,
        effective_permissions=(
            frozenset({"testsync.read"}) if readable else frozenset()
        ),
    )


def _client(
    principal: AuthenticatedPrincipal,
    *,
    secret: bytes = b"p7-api-token-secret-32-bytes-minimum!!",
    enabled: bool = True,
):
    assert principal.company_id is not None or not principal.has_operational_context
    provider = _Provider()
    sync_registry = SyncProviderRegistry(_module_registry(), [provider])
    sync_registry.freeze()
    company_for_journal = principal.company_id or uuid4()
    availability = _Availability(enabled=enabled)
    query = SyncQueryService(
        sync_registry,
        _Journal(company_for_journal),
        _Transactions(),
        availability,
        SyncTokenCodec(secret),
    )
    sync_runtime = _SyncRuntime(query)
    identity = _IdentityRuntime(principal)
    modules = _ModuleRuntime()
    app = create_app(
        settings=Settings(environment="test"),
        database_runtime_factory=lambda settings: _DatabaseRuntime(),
        tenant_platform_factory=lambda settings: _TenantRuntime(),
        identity_platform_factory=lambda settings, tenant: identity,
        milking_platform_factory=lambda tenant: None,
        module_platform_factory=lambda tenant: modules,
        sync_platform_factory=lambda settings, tenant, module: sync_runtime,
    )
    return TestClient(app), provider, availability


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer p7-token"}


def test_sync_pull_http_shape_uses_authenticated_scope_only() -> None:
    principal = _principal()
    client, provider, availability = _client(principal)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sync_protocol_version"] == "1"
    assert body["module_id"] == "testsync"
    assert body["stream_id"] == "default"
    assert body["has_more"] is False
    assert len(body["batches"]) == 1
    assert body["batches"][0]["position"] == 1
    assert body["batches"][0]["changes"][0]["change_kind"] == "UPSERT"
    assert "tenant_id" not in body
    assert "company_id" not in body
    assert provider.authorize_calls == 1
    assert principal.tenant_id is not None and principal.company_id is not None
    assert availability.calls == [
        (principal.tenant_id, principal.company_id, "testsync")
    ]


def test_sync_bootstrap_http_shape_uses_start_cursor_and_no_observed_cursor() -> None:
    principal = _principal()
    client, _, _ = _client(principal)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/bootstrap",
            headers=_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sync_protocol_version"] == "1"
    assert body["module_id"] == "testsync"
    assert body["stream_id"] == "default"
    assert len(body["items"]) == 1
    assert body["next_page_token"] is None
    assert body["has_more"] is False
    assert isinstance(body["bootstrap_start_cursor"], str)
    assert body["bootstrap_start_cursor"]
    assert "observed_through_cursor" not in str(body)


def test_sync_requires_bearer_authentication() -> None:
    principal = _principal()
    client, provider, availability = _client(principal)
    with client:
        response = client.get("/api/v1/sync/testsync/changes")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert provider.authorize_calls == 0
    assert availability.calls == []


def test_sync_requires_operational_tenant_company_context() -> None:
    principal = _principal(operational=False)
    client, provider, availability = _client(principal)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
    assert provider.authorize_calls == 0
    assert availability.calls == []


def test_sync_provider_permission_is_fail_closed() -> None:
    principal = _principal(readable=False)
    client, provider, availability = _client(principal)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
    assert provider.authorize_calls == 1
    assert len(availability.calls) == 1


def test_sync_module_activation_is_rechecked_each_request() -> None:
    principal = _principal()
    client, provider, availability = _client(principal, enabled=False)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODULE_NOT_ENABLED"
    assert provider.authorize_calls == 0
    assert len(availability.calls) == 1


def test_sync_unknown_stream_is_not_exposed_as_data() -> None:
    principal = _principal()
    client, provider, _ = _client(principal)
    with client:
        response = client.get(
            "/api/v1/sync/testsync/changes?stream_id=other",
            headers=_headers(),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SYNC_STREAM_NOT_FOUND"
    assert provider.authorize_calls == 0


def test_sync_cursor_cannot_cross_company_scope() -> None:
    tenant_id = uuid4()
    company_a = uuid4()
    company_b = uuid4()
    secret = b"p7-cross-company-secret-32-bytes!!"

    client_a, _, _ = _client(
        _principal(tenant_id=tenant_id, company_id=company_a),
        secret=secret,
    )
    with client_a:
        first = client_a.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
        )
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]

    client_b, provider_b, _ = _client(
        _principal(tenant_id=tenant_id, company_id=company_b),
        secret=secret,
    )
    with client_b:
        crossed = client_b.get(
            "/api/v1/sync/testsync/changes",
            headers=_headers(),
            params={"cursor": cursor},
        )

    assert crossed.status_code == 400
    assert crossed.json()["error"]["code"] == "SYNC_CURSOR_INVALID"
    # Module/functional authorization is re-evaluated before interpreting the
    # cursor, but the cursor itself grants no authority and exposes no origin.
    assert provider_b.authorize_calls == 1
    assert str(company_a) not in crossed.text


def test_sync_protocol_and_request_validation_fail_closed() -> None:
    principal = _principal()
    client, provider, availability = _client(principal)
    with client:
        unsupported = client.get(
            "/api/v1/sync/testsync/changes?sync_protocol_version=2",
            headers=_headers(),
        )
        invalid = client.get(
            "/api/v1/sync/INVALID MODULE/changes?stream_id=bad-stream&limit=0",
            headers={**_headers(), "X-Correlation-ID": "p7-invalid-sync"},
        )

    assert unsupported.status_code == 409
    assert unsupported.json()["error"]["code"] == "SYNC_PROTOCOL_UNSUPPORTED"
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "Request validation failed.",
            "correlation_id": "p7-invalid-sync",
        }
    }
    assert provider.authorize_calls == 0
    assert availability.calls == []


def test_p7_exposes_no_generic_row_scoped_feed_contract() -> None:
    provider_parameters = set(inspect.signature(SyncProvider.bootstrap_page).parameters)
    query_parameters = set(inspect.signature(SyncQueryService.changes).parameters)
    forbidden = {"farm_id", "warehouse_id", "site_id", "location_id", "work_center_id"}
    assert forbidden.isdisjoint(provider_parameters)
    assert forbidden.isdisjoint(query_parameters)
