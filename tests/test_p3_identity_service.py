from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.identity.migrations import PlatformMigrationRunner
from app.infrastructure.identity.repository import SqlAlchemyIdentityRepository
from app.infrastructure.identity.session_scope import PlatformSessionScope
from app.infrastructure.security.credentials import (
    Argon2idPasswordHasher,
    SecureRefreshTokenGenerator,
)
from app.infrastructure.security.tokens import Hs256AccessTokenCodec
from app.platform.company.model import Company
from app.platform.identity.model import RoleScope, UserStatus
from app.platform.identity.service import (
    AuthenticationService,
    IdentityProvisioningService,
)
from app.platform.tenancy.registry import TenantConnectionConfig


class Transaction:
    def __init__(self, engine, scope: PlatformSessionScope) -> None:
        self._factory = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )
        self._scope = scope

    def run(self, operation):
        with self._factory() as session:
            with session.begin():
                with self._scope.activate(session):
                    return operation()


class Registry:
    def __init__(self, tenant_id: UUID) -> None:
        self._tenant_id = tenant_id

    def get(self, tenant_id: UUID) -> TenantConnectionConfig:
        if tenant_id != self._tenant_id:
            raise KeyError(tenant_id)
        return TenantConnectionConfig(
            tenant_id=tenant_id,
            database_url="sqlite+pysqlite:///:memory:",
        )


class CompanyDirectory:
    def __init__(self, tenant_id: UUID, company_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.company_id = company_id
        self.active = True

    def get_company(self, tenant_id: UUID, company_id: UUID) -> Company | None:
        if tenant_id != self.tenant_id or company_id != self.company_id:
            return None
        now = datetime.now(UTC)
        return Company(
            id=company_id,
            code="A1",
            legal_name="Company A1",
            is_active=self.active,
            created_at=now,
            updated_at=now,
        )


@pytest.fixture()
def services(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'identity.db'}"
    runner = PlatformMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    runner.upgrade(database_url)
    engine = create_engine(database_url)
    scope = PlatformSessionScope()
    repository = SqlAlchemyIdentityRepository(scope)
    transaction = Transaction(engine, scope)
    tenant_id = uuid4()
    company_id = uuid4()
    directory = CompanyDirectory(tenant_id, company_id)
    password_hasher = Argon2idPasswordHasher()
    token_codec = Hs256AccessTokenCodec(
        secret="x" * 32,
        issuer="erp-platform",
        audience="erp-first-party",
    )
    provisioning = IdentityProvisioningService(
        repository,
        transaction,
        password_hasher,
        Registry(tenant_id),
        directory,
    )
    authentication = AuthenticationService(
        repository,
        transaction,
        password_hasher,
        token_codec,
        SecureRefreshTokenGenerator(),
        directory,
        issuer="erp-platform",
        audience="erp-first-party",
    )
    try:
        yield provisioning, authentication, tenant_id, company_id, directory
    finally:
        engine.dispose()


def _authorized_user(services):
    provisioning, authentication, tenant_id, company_id, _ = services
    user = provisioning.create_user(
        login="ana",
        password="12345678!",
        display_name="Ana",
    )
    provisioning.grant_membership(user.id, tenant_id)
    provisioning.grant_company_access(user.id, tenant_id, company_id)
    return user, provisioning, authentication, tenant_id, company_id


def test_login_context_and_company_rbac_are_scope_bound(services) -> None:
    user, provisioning, authentication, tenant_id, company_id = _authorized_user(services)
    permission = provisioning.ensure_permission("identity.user.read")
    role = provisioning.ensure_role(
        "company_operator",
        name="Company Operator",
        scope=RoleScope.COMPANY,
    )
    provisioning.grant_permission_to_role(role.id, permission.id)
    provisioning.assign_role(
        user.id,
        role.id,
        tenant_id=tenant_id,
        company_id=company_id,
    )

    pair = authentication.login(login="ana", password="12345678!")
    identity = authentication.principal_from_access_token(pair.access_token)
    assert identity.effective_permissions == frozenset()

    contexts = authentication.list_contexts(identity)
    assert [(item.tenant_id, item.company_id) for item in contexts] == [
        (tenant_id, company_id)
    ]

    operational = authentication.select_context(
        identity,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    principal = authentication.principal_from_access_token(
        operational.access_token
    )
    assert principal.effective_permissions == frozenset({"identity.user.read"})

    provisioning.revoke_membership(user.id, tenant_id)
    with pytest.raises(Exception) as revoked:
        authentication.principal_from_access_token(operational.access_token)
    assert getattr(revoked.value, "code", None) == "AUTHENTICATION_FAILED"


def test_refresh_rotation_replay_revokes_the_session(
    services,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, _, authentication, _, _ = _authorized_user(services)
    first = authentication.login(login="ana", password="12345678!")
    second = authentication.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token

    with caplog.at_level(logging.WARNING, logger="app.platform.identity.service"):
        with pytest.raises(Exception) as replay:
            authentication.refresh(first.refresh_token)
    assert getattr(replay.value, "code", None) == "AUTHENTICATION_FAILED"
    assert "refresh_replay_detected" in [record.getMessage() for record in caplog.records]
    assert first.refresh_token not in caplog.text

    with pytest.raises(Exception) as revoked:
        authentication.principal_from_access_token(second.access_token)
    assert getattr(revoked.value, "code", None) == "AUTHENTICATION_FAILED"


def test_logout_is_idempotent_and_revokes_refresh(services) -> None:
    _, _, authentication, _, _ = _authorized_user(services)
    pair = authentication.login(login="ana", password="12345678!")
    authentication.logout(pair.access_token)
    authentication.logout(pair.access_token)

    with pytest.raises(Exception) as refresh:
        authentication.refresh(pair.refresh_token)
    assert getattr(refresh.value, "code", None) == "AUTHENTICATION_FAILED"


def test_password_change_and_user_suspension_revoke_access(services) -> None:
    user, provisioning, authentication, _, _ = _authorized_user(services)
    pair = authentication.login(login="ana", password="12345678!")
    provisioning.change_password(user.id, new_password="87654321!")

    with pytest.raises(Exception) as old_session:
        authentication.principal_from_access_token(pair.access_token)
    assert getattr(old_session.value, "code", None) == "AUTHENTICATION_FAILED"

    with pytest.raises(Exception):
        authentication.login(login="ana", password="12345678!")
    new_pair = authentication.login(login="ana", password="87654321!")
    assert authentication.principal_from_access_token(new_pair.access_token).user_id == user.id

    provisioning.set_user_status(user.id, UserStatus.SUSPENDED)
    with pytest.raises(Exception) as suspended:
        authentication.principal_from_access_token(new_pair.access_token)
    assert getattr(suspended.value, "code", None) == "AUTHENTICATION_FAILED"
