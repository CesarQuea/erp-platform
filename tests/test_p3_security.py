from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.infrastructure.observability.logging import JsonLogFormatter
from app.infrastructure.security.credentials import (
    Argon2idPasswordHasher,
    SecureRefreshTokenGenerator,
)
from app.infrastructure.security.tokens import (
    AccessTokenValidationError,
    Hs256AccessTokenCodec,
)
from app.platform.identity.authorization import AuthorizationService, effective_permissions
from app.platform.identity.model import (
    AuthenticatedPrincipal,
    Role,
    RoleAssignment,
    RoleScope,
)
from app.platform.identity.policy import PasswordPolicy, PasswordPolicyError, normalize_login
from app.platform.identity.security import AccessTokenClaims


def test_login_normalization_is_deterministic() -> None:
    assert normalize_login("  USER@Example.COM  ") == "user@example.com"


def test_password_policy_uses_approved_eight_character_minimum() -> None:
    policy = PasswordPolicy()
    policy.validate(password="abcdefgh", login="operator")
    policy.validate(password="abc 123!", login="operator")
    with pytest.raises(PasswordPolicyError):
        policy.validate(password="short7", login="operator")
    with pytest.raises(PasswordPolicyError):
        policy.validate(password="operator", login="operator")


def test_argon2id_password_hash_round_trip() -> None:
    hasher = Argon2idPasswordHasher()
    password_hash = hasher.hash("a secure passphrase")
    assert password_hash.startswith("$argon2id$")
    assert hasher.verify("a secure passphrase", password_hash)
    assert not hasher.verify("wrong password", password_hash)


def test_refresh_tokens_are_random_and_only_hash_is_stable() -> None:
    generator = SecureRefreshTokenGenerator()
    first = generator.generate()
    second = generator.generate()
    assert first.plaintext != second.plaintext
    assert first.token_hash == generator.hash_token(first.plaintext)
    assert first.plaintext not in first.token_hash


def _claims(*, issuer: str = "erp-platform", audience: str = "erp-first-party", expired: bool = False) -> AccessTokenClaims:
    now = datetime.now(UTC)
    return AccessTokenClaims(
        issuer=issuer,
        audience=audience,
        user_id=uuid4(),
        session_id=uuid4(),
        token_id=uuid4(),
        issued_at=now - timedelta(minutes=2) if expired else now,
        expires_at=now - timedelta(minutes=1) if expired else now + timedelta(minutes=15),
        tenant_id=uuid4(),
        company_id=uuid4(),
    )


def test_jwt_codec_validates_issuer_audience_and_context() -> None:
    codec = Hs256AccessTokenCodec(
        secret="x" * 32,
        issuer="erp-platform",
        audience="erp-first-party",
    )
    claims = _claims()
    decoded = codec.decode(codec.encode(claims))
    assert decoded.user_id == claims.user_id
    assert decoded.session_id == claims.session_id
    assert decoded.tenant_id == claims.tenant_id
    assert decoded.company_id == claims.company_id

    with pytest.raises(AccessTokenValidationError):
        codec.decode(codec.encode(_claims(issuer="other-issuer")))
    with pytest.raises(AccessTokenValidationError):
        codec.decode(codec.encode(_claims(audience="other-audience")))
    with pytest.raises(AccessTokenValidationError):
        codec.decode(codec.encode(_claims(expired=True)))


def test_rbac_scopes_do_not_leak_between_tenants_or_companies() -> None:
    user_id = uuid4()
    tenant_a, tenant_b = uuid4(), uuid4()
    company_a, company_b = uuid4(), uuid4()
    platform_role = Role(uuid4(), "platform_reader", RoleScope.PLATFORM, "Platform Reader")
    tenant_role = Role(uuid4(), "tenant_reader", RoleScope.TENANT, "Tenant Reader")
    company_role = Role(uuid4(), "company_reader", RoleScope.COMPANY, "Company Reader")
    assignments = [
        RoleAssignment(
            id=uuid4(),
            user_id=user_id,
            role_id=platform_role.id,
            scope=RoleScope.PLATFORM,
        ),
        RoleAssignment(
            id=uuid4(),
            user_id=user_id,
            role_id=tenant_role.id,
            scope=RoleScope.TENANT,
            tenant_id=tenant_a,
        ),
        RoleAssignment(
            id=uuid4(),
            user_id=user_id,
            role_id=company_role.id,
            scope=RoleScope.COMPANY,
            tenant_id=tenant_a,
            company_id=company_a,
        ),
    ]
    roles = {role.id: role for role in (platform_role, tenant_role, company_role)}
    permissions = {
        platform_role.id: frozenset({"platform.read"}),
        tenant_role.id: frozenset({"tenant.read"}),
        company_role.id: frozenset({"company.read"}),
    }

    assert effective_permissions(
        user_id=user_id,
        tenant_id=tenant_a,
        company_id=company_a,
        assignments=assignments,
        roles=roles,
        role_permissions=permissions,
    ) == frozenset({"platform.read", "tenant.read", "company.read"})
    assert effective_permissions(
        user_id=user_id,
        tenant_id=tenant_b,
        company_id=company_b,
        assignments=assignments,
        roles=roles,
        role_permissions=permissions,
    ) == frozenset({"platform.read"})


def test_authorization_is_deny_by_default() -> None:
    principal = AuthenticatedPrincipal(user_id=uuid4(), session_id=uuid4())
    with pytest.raises(Exception) as denied:
        AuthorizationService().require(principal, "unknown.permission")
    assert getattr(denied.value, "code", None) == "ACCESS_DENIED"
    assert getattr(denied.value, "status_code", None) == 403


def test_json_audit_formatter_emits_only_allowlisted_security_metadata() -> None:
    record = logging.LogRecord(
        name="test.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="membership_granted",
        args=(),
        exc_info=None,
    )
    record.user_id = "user-safe-id"
    record.tenant_id = "tenant-safe-id"
    record.password = "must-never-appear"
    record.refresh_token = "must-never-appear-either"
    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["user_id"] == "user-safe-id"
    assert payload["tenant_id"] == "tenant-safe-id"
    assert "password" not in payload
    assert "refresh_token" not in payload
    assert "must-never-appear" not in json.dumps(payload)
