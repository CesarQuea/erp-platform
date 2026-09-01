from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.application import create_app
from app.core.config.settings import Settings
from app.infrastructure.identity.migrations import PlatformMigrationRunner
from app.platform.identity.model import RoleScope
from app.platform.tenancy.context import TenantContext


_TENANT_ENV = "O4_TEST_TENANT_DATABASES_JSON"
_IDENTITY_ENV = "O4_TEST_IDENTITY_DATABASE_URL"
_CURRENT_TENANT_HEAD = "0006_p7_sync_foundation"
_MODULE_MANAGE_PERMISSION = "platform.modules.manage"
_MILKING_PERMISSIONS = (
    "milking.session.create",
    "milking.session.update_draft",
    "milking.session.confirm",
    "milking.session.cancel",
    "milking.session.read",
    "milking.config.read",
    "milking.config.manage",
    "milking.output_profile.read",
    "milking.output_profile.manage",
)


def _first_postgres_tenant() -> tuple[UUID, str]:
    raw = os.getenv(_TENANT_ENV)
    if not raw:
        pytest.skip(f"{_TENANT_ENV} is required for O-4 P-3 API integration")
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            return UUID(str(raw_tenant_id)), url
    pytest.skip(f"{_TENANT_ENV} contains no PostgreSQL tenant database")


def _identity_url() -> str:
    value = os.getenv(_IDENTITY_ENV)
    if not value or not value.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        pytest.skip(f"{_IDENTITY_ENV} must point to a PostgreSQL Platform Identity database")
    return value


def _command_payload(**extra):
    return {
        "command_id": str(uuid4()),
        "client_occurred_at": datetime.now(UTC).isoformat(),
        "client_instance_id": "o4-p3-integration",
        **extra,
    }


def _enable_milking(client: TestClient, headers: dict[str, str]) -> None:
    modules = client.get("/api/v1/modules", headers=headers)
    assert modules.status_code == 200
    milking = next(item for item in modules.json() if item["module_id"] == "milking")
    if milking["effective_enabled"]:
        return
    enabled = client.post(
        "/api/v1/modules/milking/enable",
        headers=headers,
        json={"command_id": str(uuid4()), "expected_version": milking["version"]},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["state"] == "ENABLED"


def test_real_p3_operational_token_authorizes_o4_end_to_end() -> None:
    tenant_id, tenant_url = _first_postgres_tenant()
    identity_url = _identity_url()
    root = Path(__file__).resolve().parents[1]
    PlatformMigrationRunner(repository_root=root).upgrade(identity_url)

    settings = Settings(
        environment="test",
        database_url=identity_url,
        tenant_databases_json=json.dumps(
            {str(tenant_id): {"database_url": tenant_url}}
        ),
        jwt_signing_secret="o4-test-jwt-signing-secret-material-32-bytes-minimum",
    )
    app = create_app(settings=settings)
    password = "O4-test-password-123!"
    suffix = uuid4().hex[:12]
    login_name = f"o4-{suffix}@example.test"

    with TestClient(app) as client:
        tenant_runtime = app.state.tenant_platform
        assert (
            tenant_runtime.provisioner.provision(TenantContext(tenant_id))
            == _CURRENT_TENANT_HEAD
        )
        company = tenant_runtime.company_service.register_company(
            TenantContext(tenant_id),
            code=f"O4P3-{suffix}",
            legal_name=f"O-4 P-3 Integration {suffix}",
        )

        identity_runtime = app.state.identity_platform
        assert identity_runtime is not None
        provisioning = identity_runtime.provisioning
        user = provisioning.create_user(
            login=login_name,
            password=password,
            display_name="O-4 Integration Operator",
        )
        provisioning.grant_membership(user.id, tenant_id)
        provisioning.grant_company_access(user.id, tenant_id, company.id)

        permissions = [
            provisioning.ensure_permission(code, description=f"O-4 verification {code}")
            for code in (*_MILKING_PERMISSIONS, _MODULE_MANAGE_PERMISSION)
        ]
        role = provisioning.ensure_role(
            f"O4_MILKING_OPERATOR_{suffix}",
            name="O-4 Milking Verification Operator",
            scope=RoleScope.COMPANY,
        )
        for permission in permissions:
            provisioning.grant_permission_to_role(role.id, permission.id)
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
        selected = client.post(
            "/api/v1/auth/context",
            headers={"Authorization": f"Bearer {global_token}"},
            json={"tenant_id": str(tenant_id), "company_id": str(company.id)},
        )
        assert selected.status_code == 200
        operational_token = selected.json()["access_token"]
        headers = {"Authorization": f"Bearer {operational_token}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["tenant_id"] == str(tenant_id)
        assert me.json()["company_id"] == str(company.id)

        _enable_milking(client, headers)

        product_id, uom_id, farm_id = uuid4(), uuid4(), uuid4()
        profile = client.post(
            "/api/v1/milking/output-profiles",
            headers=headers,
            json=_command_payload(
                product_id=str(product_id),
                quantity_uom_id=str(uom_id),
            ),
        )
        assert profile.status_code == 200
        profile_data = profile.json()["data"]
        profile_id = profile_data["profile_id"]
        assert profile_data["profile_version"] == 1

        configuration = client.post(
            "/api/v1/milking/configurations",
            headers=headers,
            json=_command_payload(
                farm_id=str(farm_id),
                shift_code="MORNING",
                output_profile_id=profile_id,
                output_profile_version=1,
            ),
        )
        assert configuration.status_code == 200

        created = client.post(
            "/api/v1/milking/sessions",
            headers=headers,
            json=_command_payload(
                farm_id=str(farm_id),
                milking_date=date(2026, 8, 25).isoformat(),
                shift_code="MORNING",
                operator_id=None,
            ),
        )
        assert created.status_code == 200
        assert created.json()["code"] == "MILKING_SESSION_CREATED"
        session_id = created.json()["data"]["session_id"]

        fetched = client.get(
            f"/api/v1/milking/sessions/{session_id}",
            headers=headers,
        )
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["company_id"] == str(company.id)
        assert body["farm_id"] == str(farm_id)
        assert body["created_by"] == str(user.id)
        assert body["product_id"] == str(product_id)
        assert body["quantity_uom_id"] == str(uom_id)


def test_real_p3_context_without_milking_permission_is_denied_by_o4() -> None:
    tenant_id, tenant_url = _first_postgres_tenant()
    identity_url = _identity_url()
    root = Path(__file__).resolve().parents[1]
    PlatformMigrationRunner(repository_root=root).upgrade(identity_url)

    settings = Settings(
        environment="test",
        database_url=identity_url,
        tenant_databases_json=json.dumps(
            {str(tenant_id): {"database_url": tenant_url}}
        ),
        jwt_signing_secret="o4-test-jwt-signing-secret-material-32-bytes-minimum",
    )
    app = create_app(settings=settings)
    password = "O4-no-permission-password-123!"
    suffix = uuid4().hex[:12]
    login_name = f"o4-denied-{suffix}@example.test"

    with TestClient(app) as client:
        tenant_runtime = app.state.tenant_platform
        assert (
            tenant_runtime.provisioner.provision(TenantContext(tenant_id))
            == _CURRENT_TENANT_HEAD
        )
        company = tenant_runtime.company_service.register_company(
            TenantContext(tenant_id),
            code=f"O4NO-{suffix}",
            legal_name=f"O-4 No Permission {suffix}",
        )
        provisioning = app.state.identity_platform.provisioning
        user = provisioning.create_user(
            login=login_name,
            password=password,
            display_name="O-4 Unauthorized Operator",
        )
        provisioning.grant_membership(user.id, tenant_id)
        provisioning.grant_company_access(user.id, tenant_id, company.id)

        module_permission = provisioning.ensure_permission(
            _MODULE_MANAGE_PERMISSION,
            description="P-6 module activation verification",
        )
        role = provisioning.ensure_role(
            f"O4_MODULE_ADMIN_{suffix}",
            name="O-4 Module Activation Verification",
            scope=RoleScope.COMPANY,
        )
        provisioning.grant_permission_to_role(role.id, module_permission.id)
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
        global_token = login.json()["access_token"]
        selected = client.post(
            "/api/v1/auth/context",
            headers={"Authorization": f"Bearer {global_token}"},
            json={"tenant_id": str(tenant_id), "company_id": str(company.id)},
        )
        headers = {"Authorization": f"Bearer {selected.json()['access_token']}"}

        _enable_milking(client, headers)

        response = client.get("/api/v1/milking/sessions", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ACCESS_DENIED"
