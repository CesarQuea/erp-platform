from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings
from app.infrastructure.identity.migrations import PlatformMigrationRunner
from app.platform.identity.model import RoleScope
from app.platform.tenancy.context import TenantContext


_TENANT_ENV = "P6_TEST_TENANT_DATABASES_JSON"
_IDENTITY_ENV = "P6_TEST_IDENTITY_DATABASE_URL"
_CURRENT_TENANT_HEAD = "0005_p5_module_activation"
_MANAGE_MODULES = "platform.modules.manage"
_MILKING_READ = "milking.session.read"


def _two_postgres_tenants() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TENANT_ENV)
    if not raw:
        pytest.skip(f"{_TENANT_ENV} is required for P-6 PostgreSQL verification")
    values: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            values.append((UUID(str(raw_tenant_id)), url))
    if len(values) < 2:
        pytest.skip(f"{_TENANT_ENV} must contain at least two PostgreSQL tenant databases")
    return values[:2]


def _identity_url() -> str:
    value = os.getenv(_IDENTITY_ENV)
    if not value or not value.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        pytest.skip(f"{_IDENTITY_ENV} must point to a PostgreSQL Platform Identity database")
    return value


def _select_context(client: TestClient, global_token: str, tenant_id: UUID, company_id: UUID) -> dict[str, str]:
    selected = client.post(
        "/api/v1/auth/context",
        headers={"Authorization": f"Bearer {global_token}"},
        json={"tenant_id": str(tenant_id), "company_id": str(company_id)},
    )
    assert selected.status_code == 200
    return {"Authorization": f"Bearer {selected.json()['access_token']}"}


def _milking_status(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.get("/api/v1/modules", headers=headers)
    assert response.status_code == 200
    return next(item for item in response.json() if item["module_id"] == "milking")


def test_real_p6_module_api_and_enforcement_are_tenant_company_isolated() -> None:
    tenants = _two_postgres_tenants()
    identity_url = _identity_url()
    root = Path(__file__).resolve().parents[1]
    PlatformMigrationRunner(repository_root=root).upgrade(identity_url)

    tenant_json = {
        str(tenant_id): {"database_url": url}
        for tenant_id, url in tenants
    }
    settings = Settings(
        environment="test",
        database_url=identity_url,
        tenant_databases_json=json.dumps(tenant_json),
        jwt_signing_secret="p6-test-jwt-signing-secret-material-32-bytes-minimum",
    )
    app = create_app(settings=settings)
    suffix = uuid4().hex[:12]
    password = "P6-test-password-123!"
    login_name = f"p6-{suffix}@example.test"

    with TestClient(app) as client:
        tenant_runtime = app.state.tenant_platform
        companies = []
        for index, (tenant_id, _) in enumerate(tenants, start=1):
            assert (
                tenant_runtime.provisioner.provision(TenantContext(tenant_id))
                == _CURRENT_TENANT_HEAD
            )
            companies.append(
                tenant_runtime.company_service.register_company(
                    TenantContext(tenant_id),
                    code=f"P6-{index}-{suffix}",
                    legal_name=f"P-6 Verification Company {index} {suffix}",
                )
            )

        provisioning = app.state.identity_platform.provisioning
        user = provisioning.create_user(
            login=login_name,
            password=password,
            display_name="P-6 Module Administrator",
        )
        for (tenant_id, _), company in zip(tenants, companies, strict=True):
            provisioning.grant_membership(user.id, tenant_id)
            provisioning.grant_company_access(user.id, tenant_id, company.id)

        permissions = [
            provisioning.ensure_permission(
                code,
                description=f"P-6 verification {code}",
            )
            for code in (_MANAGE_MODULES, _MILKING_READ)
        ]
        role = provisioning.ensure_role(
            f"P6_MODULE_ADMIN_{suffix}",
            name="P-6 Module Administration Verification",
            scope=RoleScope.COMPANY,
        )
        for permission in permissions:
            provisioning.grant_permission_to_role(role.id, permission.id)
        for (tenant_id, _), company in zip(tenants, companies, strict=True):
            provisioning.assign_role(
                user.id,
                role.id,
                tenant_id=tenant_id,
                company_id=company.id,
            )

        login = client.post(
            "/api/v1/auth/login",
            json={"login": login_name, "password": password},
        )
        assert login.status_code == 200
        global_token = login.json()["access_token"]

        tenant_a, tenant_b = tenants[0][0], tenants[1][0]
        company_a, company_b = companies
        headers_a = _select_context(client, global_token, tenant_a, company_a.id)
        headers_b = _select_context(client, global_token, tenant_b, company_b.id)

        status_a = _milking_status(client, headers_a)
        status_b = _milking_status(client, headers_b)
        assert status_a["state"] == "DISABLED" and status_a["version"] == 0
        assert status_b["state"] == "DISABLED" and status_b["version"] == 0
        assert not status_a["activation_present"]
        assert not status_b["activation_present"]

        blocked = client.get("/api/v1/milking/sessions", headers=headers_a)
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "MODULE_NOT_ENABLED"

        shared_command_id = uuid4()
        enabled_a = client.post(
            "/api/v1/modules/milking/enable",
            headers=headers_a,
            json={"command_id": str(shared_command_id), "expected_version": 0},
        )
        assert enabled_a.status_code == 200
        assert enabled_a.json()["replayed"] is False
        assert enabled_a.json()["data"]["version"] == 1

        replay_a = client.post(
            "/api/v1/modules/milking/enable",
            headers=headers_a,
            json={"command_id": str(shared_command_id), "expected_version": 0},
        )
        assert replay_a.status_code == 200
        assert replay_a.json()["replayed"] is True
        assert replay_a.json()["data"] == enabled_a.json()["data"]

        fingerprint_conflict = client.post(
            "/api/v1/modules/milking/disable",
            headers=headers_a,
            json={"command_id": str(shared_command_id), "expected_version": 1},
        )
        assert fingerprint_conflict.status_code == 409
        assert fingerprint_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

        stale = client.post(
            "/api/v1/modules/milking/disable",
            headers=headers_a,
            json={"command_id": str(uuid4()), "expected_version": 0},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "CONCURRENCY_CONFLICT"

        allowed = client.get("/api/v1/milking/sessions", headers=headers_a)
        assert allowed.status_code == 200
        assert allowed.json() == []

        still_isolated_b = _milking_status(client, headers_b)
        assert still_isolated_b["state"] == "DISABLED"
        assert still_isolated_b["version"] == 0

        enabled_b = client.post(
            "/api/v1/modules/milking/enable",
            headers=headers_b,
            json={"command_id": str(shared_command_id), "expected_version": 0},
        )
        assert enabled_b.status_code == 200
        assert enabled_b.json()["replayed"] is False
        assert enabled_b.json()["data"]["version"] == 1

        disabled_a = client.post(
            "/api/v1/modules/milking/disable",
            headers=headers_a,
            json={"command_id": str(uuid4()), "expected_version": 1},
        )
        assert disabled_a.status_code == 200
        assert disabled_a.json()["data"]["version"] == 2
        assert disabled_a.json()["data"]["state"] == "DISABLED"

        blocked_again = client.get("/api/v1/milking/sessions", headers=headers_a)
        assert blocked_again.status_code == 409
        assert blocked_again.json()["error"]["code"] == "MODULE_NOT_ENABLED"

        allowed_b = client.get("/api/v1/milking/sessions", headers=headers_b)
        assert allowed_b.status_code == 200
        assert allowed_b.json() == []
