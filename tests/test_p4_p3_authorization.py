from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors.models import PlatformError
from app.infrastructure.identity.migrations import PlatformMigrationRunner
from app.infrastructure.identity.repository import SqlAlchemyIdentityRepository
from app.infrastructure.identity.session_scope import PlatformSessionScope
from app.infrastructure.security.credentials import (
    Argon2idPasswordHasher,
    SecureRefreshTokenGenerator,
)
from app.infrastructure.security.tokens import Hs256AccessTokenCodec
from app.platform.commands.model import CommandExecutionRecord, CommandRequest, CommandResult, CommandScope
from app.platform.commands.service import CommandExecutionService
from app.platform.company.model import Company
from app.platform.identity.service import AuthenticationService, IdentityProvisioningService
from app.platform.tenancy.registry import TenantConnectionConfig


class PlatformTransaction:
    def __init__(self, engine, scope: PlatformSessionScope) -> None:
        self._factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
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
            code="P4",
            legal_name="P-4 Company",
            is_active=self.active,
            created_at=now,
            updated_at=now,
        )


class MemoryCommandRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, CommandExecutionRecord] = {}

    def claim(self, record: CommandExecutionRecord) -> bool:
        if record.command_id in self.records:
            return False
        self.records[record.command_id] = record
        return True

    def get(self, command_id: UUID) -> CommandExecutionRecord | None:
        return self.records.get(command_id)

    def complete(self, command_id, *, result_code, result_json, committed_at):
        old = self.records[command_id]
        self.records[command_id] = CommandExecutionRecord(
            command_id=old.command_id,
            command_name=old.command_name,
            command_schema_version=old.command_schema_version,
            scope=old.scope,
            company_id=old.company_id,
            actor_user_id=old.actor_user_id,
            fingerprint=old.fingerprint,
            result_code=result_code,
            result_json=dict(result_json),
            committed_at=committed_at,
        )


class MemoryBoundary:
    def __init__(self, repository: MemoryCommandRepository) -> None:
        self.repository = repository

    def run(self, operation):
        snapshot = deepcopy(self.repository.records)
        try:
            return operation()
        except Exception:
            self.repository.records = snapshot
            raise


class MemoryBoundaryFactory:
    def __init__(self, repository: MemoryCommandRepository) -> None:
        self.repository = repository

    def for_tenant(self, context):
        return MemoryBoundary(self.repository)


@pytest.fixture()
def p3_p4(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'identity.db'}"
    PlatformMigrationRunner(repository_root=Path(__file__).resolve().parents[1]).upgrade(
        database_url
    )
    engine = create_engine(database_url)
    scope = PlatformSessionScope()
    repository = SqlAlchemyIdentityRepository(scope)
    transaction = PlatformTransaction(engine, scope)
    tenant_id, company_id = uuid4(), uuid4()
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
    command_repository = MemoryCommandRepository()
    command_service = CommandExecutionService(
        command_repository,
        MemoryBoundaryFactory(command_repository),
    )
    try:
        yield provisioning, authentication, tenant_id, company_id, directory, command_service
    finally:
        engine.dispose()


def _operational_user(p3_p4):
    provisioning, authentication, tenant_id, company_id, _, _ = p3_p4
    user = provisioning.create_user(
        login="p4-user",
        password="12345678!",
        display_name="P4 User",
    )
    provisioning.grant_membership(user.id, tenant_id)
    provisioning.grant_company_access(user.id, tenant_id, company_id)
    pair = authentication.login(login="p4-user", password="12345678!")
    identity = authentication.principal_from_access_token(pair.access_token)
    operational = authentication.select_context(
        identity,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    return user, pair, operational.access_token


def _commit_then_replay(service, operational_token, authentication):
    request = CommandRequest(uuid4(), "p4.auth.replay", "1", CommandScope.COMPANY)
    authorize = lambda: authentication.principal_from_access_token(operational_token)
    service.execute(
        request,
        {"value": 1},
        authorize=authorize,
        operation=lambda: CommandResult("OK", {"id": "one"}),
    )
    return request, authorize


def test_membership_revocation_blocks_existing_replay(p3_p4):
    provisioning, authentication, tenant_id, _, _, service = p3_p4
    user, _, token = _operational_user(p3_p4)
    request, authorize = _commit_then_replay(service, token, authentication)
    provisioning.revoke_membership(user.id, tenant_id)
    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {"value": 1},
            authorize=authorize,
            operation=lambda: pytest.fail("replay must not execute"),
        )
    assert exc.value.code == "AUTHENTICATION_FAILED"


def test_company_access_revocation_blocks_existing_replay(p3_p4):
    provisioning, authentication, tenant_id, company_id, _, service = p3_p4
    user, _, token = _operational_user(p3_p4)
    request, authorize = _commit_then_replay(service, token, authentication)
    provisioning.revoke_company_access(user.id, tenant_id, company_id)
    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {"value": 1},
            authorize=authorize,
            operation=lambda: pytest.fail("replay must not execute"),
        )
    assert exc.value.code == "AUTHENTICATION_FAILED"


def test_inactive_company_blocks_existing_replay(p3_p4):
    _, authentication, _, _, directory, service = p3_p4
    _, _, token = _operational_user(p3_p4)
    request, authorize = _commit_then_replay(service, token, authentication)
    directory.active = False
    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {"value": 1},
            authorize=authorize,
            operation=lambda: pytest.fail("replay must not execute"),
        )
    assert exc.value.code == "ACCESS_DENIED"


def test_revoked_session_blocks_existing_replay(p3_p4):
    _, authentication, _, _, _, service = p3_p4
    _, pair, token = _operational_user(p3_p4)
    request, authorize = _commit_then_replay(service, token, authentication)
    authentication.logout(pair.access_token)
    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {"value": 1},
            authorize=authorize,
            operation=lambda: pytest.fail("replay must not execute"),
        )
    assert exc.value.code == "AUTHENTICATION_FAILED"
