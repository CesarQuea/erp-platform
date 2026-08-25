from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.errors.models import PlatformError
from app.platform.commands.model import (
    CommandExecutionRecord,
    CommandRequest,
    CommandResult,
    CommandScope,
)
from app.platform.commands.service import CommandExecutionService
from app.platform.identity.model import AuthenticatedPrincipal


class FixedClock:
    def now(self):
        return datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)


class InMemoryRepository:
    def __init__(self):
        self.records = {}

    def claim(self, record: CommandExecutionRecord) -> bool:
        if record.command_id in self.records:
            return False
        self.records[record.command_id] = record
        return True

    def get(self, command_id):
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
        )


class SnapshotBoundary:
    def __init__(self, repo, state):
        self.repo = repo
        self.state = state

    def run(self, operation):
        records = deepcopy(self.repo.records)
        state = deepcopy(self.state)
        try:
            return operation()
        except Exception:
            self.repo.records = records
            self.state.clear()
            self.state.update(state)
            raise


class BoundaryFactory:
    def __init__(self, repo, state):
        self.repo = repo
        self.state = state
        self.tenants = []

    def for_tenant(self, context):
        self.tenants.append(context.tenant_id)
        return SnapshotBoundary(self.repo, self.state)


def make_principal(*, user=None, tenant=None, company=None, session=None):
    return AuthenticatedPrincipal(
        user_id=user or uuid4(),
        session_id=session or uuid4(),
        tenant_id=tenant or uuid4(),
        company_id=company or uuid4(),
    )


def test_first_execution_and_replay_have_single_effect_and_reauthorize():
    repo, state = InMemoryRepository(), {"effects": 0}
    factory = BoundaryFactory(repo, state)
    service = CommandExecutionService(repo, factory, clock=FixedClock())
    p = make_principal()
    auth_calls = {"n": 0}

    def authorize():
        auth_calls["n"] += 1
        return p

    def operation():
        state["effects"] += 1
        return CommandResult("OK", {"id": "resource-1"})

    request = CommandRequest(uuid4(), "test.create", "1", CommandScope.COMPANY)
    first = service.execute(request, {"value": 10}, authorize=authorize, operation=operation)
    replay = service.execute(request, {"value": 10}, authorize=authorize, operation=operation)

    assert not first.replayed
    assert replay.replayed
    assert first.result == replay.result
    assert state["effects"] == 1
    assert auth_calls["n"] == 2


def test_same_command_id_with_different_payload_is_conflict():
    repo, state = InMemoryRepository(), {"effects": 0}
    service = CommandExecutionService(repo, BoundaryFactory(repo, state), clock=FixedClock())
    p = make_principal()
    request = CommandRequest(uuid4(), "test.update", "1", CommandScope.COMPANY)
    operation = lambda: CommandResult("OK", {"ok": True})
    service.execute(request, {"value": 1}, authorize=lambda: p, operation=operation)
    with pytest.raises(PlatformError) as exc:
        service.execute(request, {"value": 2}, authorize=lambda: p, operation=operation)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_same_command_id_with_different_actor_or_company_is_conflict():
    repo, state = InMemoryRepository(), {}
    service = CommandExecutionService(repo, BoundaryFactory(repo, state), clock=FixedClock())
    tenant, company, user = uuid4(), uuid4(), uuid4()
    p1 = make_principal(user=user, tenant=tenant, company=company)
    p2 = make_principal(user=uuid4(), tenant=tenant, company=company)
    p3 = make_principal(user=user, tenant=tenant, company=uuid4())
    request = CommandRequest(uuid4(), "test.update", "1", CommandScope.COMPANY)
    op = lambda: CommandResult("OK", {})
    service.execute(request, {}, authorize=lambda: p1, operation=op)
    for other in (p2, p3):
        with pytest.raises(PlatformError) as exc:
            service.execute(request, {}, authorize=lambda other=other: other, operation=op)
        assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_failed_operation_rolls_back_claim_and_can_retry():
    repo, state = InMemoryRepository(), {"effects": 0}
    service = CommandExecutionService(repo, BoundaryFactory(repo, state), clock=FixedClock())
    p = make_principal()
    request = CommandRequest(uuid4(), "test.fail", "1", CommandScope.COMPANY)

    def fail():
        state["effects"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        service.execute(request, {}, authorize=lambda: p, operation=fail)
    assert state["effects"] == 0
    assert request.command_id not in repo.records

    ok = service.execute(
        request,
        {},
        authorize=lambda: p,
        operation=lambda: CommandResult("OK", {"ok": True}),
    )
    assert not ok.replayed


def test_replay_is_not_returned_when_current_authorization_fails():
    repo, state = InMemoryRepository(), {}
    service = CommandExecutionService(repo, BoundaryFactory(repo, state), clock=FixedClock())
    p = make_principal()
    request = CommandRequest(uuid4(), "test.secure", "1", CommandScope.COMPANY)
    service.execute(
        request,
        {},
        authorize=lambda: p,
        operation=lambda: CommandResult("OK", {"secret": "not-logged"}),
    )

    def denied():
        raise PlatformError("ACCESS_DENIED", "denied", 403)

    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {},
            authorize=denied,
            operation=lambda: pytest.fail("must not execute"),
        )
    assert exc.value.code == "ACCESS_DENIED"


def test_oversized_replay_result_rolls_back():
    repo, state = InMemoryRepository(), {}
    service = CommandExecutionService(
        repo,
        BoundaryFactory(repo, state),
        clock=FixedClock(),
        replay_limit_bytes=32,
    )
    p = make_principal()
    request = CommandRequest(uuid4(), "test.large", "1", CommandScope.COMPANY)
    with pytest.raises(PlatformError) as exc:
        service.execute(
            request,
            {},
            authorize=lambda: p,
            operation=lambda: CommandResult("OK", {"value": "x" * 100}),
        )
    assert exc.value.code == "IDEMPOTENCY_RESULT_TOO_LARGE"
    assert request.command_id not in repo.records
