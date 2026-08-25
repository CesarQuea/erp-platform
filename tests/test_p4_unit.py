from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.platform.commands.fingerprint import command_fingerprint
from app.platform.commands.model import CommandContext, CommandRequest, CommandScope
from app.platform.identity.model import AuthenticatedPrincipal


def principal(*, tenant=None, company=None, user=None, session=None):
    return AuthenticatedPrincipal(
        user_id=user or uuid4(),
        session_id=session or uuid4(),
        tenant_id=tenant,
        company_id=company,
    )


def test_company_context_is_derived_from_principal():
    tenant_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    p = principal(tenant=tenant_id, company=company_id, user=user_id)
    request = CommandRequest(uuid4(), "inventory.test", "1", CommandScope.COMPANY)
    context = CommandContext.from_principal(request, p)
    assert context.tenant_id == tenant_id
    assert context.company_id == company_id
    assert context.actor_user_id == user_id


def test_tenant_scope_does_not_fingerprint_company():
    tenant_id, company_id = uuid4(), uuid4()
    request = CommandRequest(uuid4(), "tenant.test", "1", CommandScope.TENANT)
    p = principal(tenant=tenant_id, company=company_id)
    context = CommandContext.from_principal(request, p)
    assert context.company_id is None


def test_company_scope_requires_authorized_company():
    request = CommandRequest(uuid4(), "x", "1", CommandScope.COMPANY)
    with pytest.raises(ValueError):
        CommandContext.from_principal(request, principal(tenant=uuid4(), company=None))


def test_fingerprint_is_deterministic_and_ignores_session_and_correlation():
    tenant_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    request = CommandRequest(
        uuid4(), "milking.confirm", "1", CommandScope.COMPANY, 7, "req-a"
    )
    p1 = principal(tenant=tenant_id, company=company_id, user=user_id, session=uuid4())
    p2 = principal(tenant=tenant_id, company=company_id, user=user_id, session=uuid4())
    c1 = CommandContext.from_principal(request, p1)
    c2 = CommandContext.from_principal(replace(request, correlation_id="req-b"), p2)
    payload_a = {"b": [1, Decimal("1.00")], "a": "á"}
    payload_b = {"a": "á", "b": [1, Decimal("1.0")]}
    assert command_fingerprint(c1, payload_a) == command_fingerprint(c2, payload_b)


def test_fingerprint_changes_with_semantic_context_or_payload():
    tenant_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    req = CommandRequest(uuid4(), "x", "1", CommandScope.COMPANY, 2)
    p = principal(tenant=tenant_id, company=company_id, user=user_id)
    base = CommandContext.from_principal(req, p)
    fp = command_fingerprint(base, {"value": 1})
    assert fp != command_fingerprint(replace(base, expected_version=3), {"value": 1})
    assert fp != command_fingerprint(replace(base, actor_user_id=uuid4()), {"value": 1})
    assert fp != command_fingerprint(replace(base, company_id=uuid4()), {"value": 1})
    assert fp != command_fingerprint(base, {"value": 2})


def test_fingerprint_rejects_float_and_naive_datetime():
    tenant_id, company_id = uuid4(), uuid4()
    req = CommandRequest(uuid4(), "x", "1", CommandScope.COMPANY)
    ctx = CommandContext.from_principal(req, principal(tenant=tenant_id, company=company_id))
    with pytest.raises(TypeError):
        command_fingerprint(ctx, {"value": 1.5})
    with pytest.raises(ValueError):
        command_fingerprint(ctx, {"when": datetime(2026, 1, 1)})
    command_fingerprint(ctx, {"when": datetime(2026, 1, 1, tzinfo=timezone.utc)})
