from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.infrastructure.security.credentials import Argon2idPasswordHasher, SecureRefreshTokenGenerator
from app.infrastructure.security.tokens import Hs256AccessTokenCodec
from app.platform.identity.authorization import effective_permissions
from app.platform.identity.model import Role, RoleAssignment, RoleScope
from app.platform.identity.policy import PasswordPolicy, PasswordPolicyError, normalize_login
from app.platform.identity.security import AccessTokenClaims


def test_login_normalization_is_deterministic() -> None:
    assert normalize_login("  USER@Example.COM  ") == "user@example.com"


def test_password_policy_uses_approved_eight_character_minimum() -> None:
    policy = PasswordPolicy()
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


def test_jwt_codec_validates_issuer_audience_and_context() -> None:
    codec = Hs256AccessTokenCodec(secret="x" * 32, issuer="erp-platform", audience="erp-first-party")
    now = datetime.now(UTC)
    claims = AccessTokenClaims(
        issuer="erp-platform",
        audience="erp-first-party",
        user_id=uuid4(),
        session_id=uuid4(),
        token_id=uuid4(),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        tenant_id=uuid4(),
        company_id=uuid4(),
    )
    decoded = codec.decode(codec.encode(claims))
    assert decoded.user_id == claims.user_id
    assert decoded.session_id == claims.session_id
    assert decoded.tenant_id == claims.tenant_id
    assert decoded.company_id == claims.company_id


def test_rbac_scopes_do_not_leak_between_tenants_or_companies() -> None:
    user_id = uuid4()
    role = Role(uuid4(), "operator", RoleScope.COMPANY, "Operator")
    tenant_a, tenant_b = uuid4(), uuid4()
    company_a, company_b = uuid4(), uuid4()
    assignment = RoleAssignment(
        id=uuid4(),
        user_id=user_id,
        role_id=role.id,
        scope=RoleScope.COMPANY,
        tenant_id=tenant_a,
        company_id=company_a,
    )
    permissions = {role.id: frozenset({"identity.user.read"})}
    roles = {role.id: role}
    assert effective_permissions(
        user_id=user_id,
        tenant_id=tenant_a,
        company_id=company_a,
        assignments=[assignment],
        roles=roles,
        role_permissions=permissions,
    ) == frozenset({"identity.user.read"})
    assert not effective_permissions(
        user_id=user_id,
        tenant_id=tenant_b,
        company_id=company_b,
        assignments=[assignment],
        roles=roles,
        role_permissions=permissions,
    )
