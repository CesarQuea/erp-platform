from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.model import ModuleDefinition
from app.platform.modules.registry import ModuleRegistry
from app.platform.sync.model import (
    BootstrapPage,
    SyncBatch,
    SyncChange,
    SyncChangeKind,
    SyncProjection,
)
from app.platform.sync.query import SyncQueryService
from app.platform.sync.registry import SyncProviderRegistry
from app.platform.sync.token import SyncTokenCodec


class _Boundary:
    def run(self, operation):
        return operation()


class _Transactions:
    def for_tenant(self, context):
        del context
        return _Boundary()


class _Availability:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, str]] = []

    def require_enabled(self, context, company_id: UUID, module_id: str):
        self.calls.append((context.tenant_id, company_id, module_id))


class _Journal:
    def __init__(self, *, position: int = 0, batches: tuple[SyncBatch, ...] = ()) -> None:
        self.position = position
        self.batches = batches

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
        return tuple(
            batch for batch in self.batches if batch.position > after_position
        )[:limit]


class _Provider:
    module_id = "testsync"
    stream_ids = ("default",)

    def __init__(self) -> None:
        self.rows: list[tuple[str, SyncProjection]] = []
        self.authorized = 0

    def authorize(self, *, principal, stream_id: str) -> None:
        assert principal.company_id is not None
        assert stream_id == "default"
        self.authorized += 1

    def bootstrap_page(
        self,
        *,
        principal,
        stream_id: str,
        after_key: str | None,
        limit: int,
    ) -> BootstrapPage:
        del principal
        assert stream_id == "default"
        rows = sorted(self.rows, key=lambda row: row[0])
        if after_key is not None:
            rows = [row for row in rows if row[0] > after_key]
        selected = rows[:limit]
        has_more = len(rows) > limit
        next_key = selected[-1][0] if has_more and selected else None
        return BootstrapPage(
            items=tuple(value for _, value in selected),
            next_key=next_key,
            has_more=has_more,
        )


def _principal(*, company_id: UUID | None = None) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        company_id=company_id or uuid4(),
        effective_permissions=frozenset({"testsync.read"}),
    )


def _registry(provider: _Provider) -> SyncProviderRegistry:
    modules = ModuleRegistry(
        [
            ModuleDefinition(
                module_id="testsync",
                module_version="1.0.0",
                configuration_namespace="testsync",
            )
        ]
    )
    modules.freeze()
    registry = SyncProviderRegistry(modules, [provider])
    registry.freeze()
    return registry


def _batch(company_id: UUID, position: int) -> SyncBatch:
    entity_id = uuid4()
    return SyncBatch(
        batch_id=uuid4(),
        company_id=company_id,
        module_id="testsync",
        stream_id="default",
        position=position,
        sync_protocol_version="1",
        recorded_at=datetime.now(timezone.utc),
        changes=(
            SyncChange(
                entity_type="record",
                entity_id=entity_id,
                change_kind=SyncChangeKind.UPSERT,
                schema_version="1",
                entity_version=position,
                payload={"id": str(entity_id), "position": position},
            ),
        ),
    )


def _projection(key: str) -> SyncProjection:
    entity_id = uuid4()
    return SyncProjection(
        entity_type="record",
        entity_id=entity_id,
        schema_version="1",
        entity_version=1,
        payload={"id": str(entity_id), "key": key},
    )


def test_sync_token_is_tamper_evident_and_scope_bound() -> None:
    codec = SyncTokenCodec(b"x" * 32)
    tenant_id = uuid4()
    company_id = uuid4()
    token = codec.encode_cursor(
        tenant_id=tenant_id,
        company_id=company_id,
        module_id="testsync",
        stream_id="default",
        position=7,
    )
    assert codec.decode_cursor(
        token,
        tenant_id=tenant_id,
        company_id=company_id,
        module_id="testsync",
        stream_id="default",
    ) == 7

    with pytest.raises(Exception) as wrong_scope:
        codec.decode_cursor(
            token,
            tenant_id=tenant_id,
            company_id=uuid4(),
            module_id="testsync",
            stream_id="default",
        )
    assert getattr(wrong_scope.value, "code", None) == "SYNC_CURSOR_INVALID"

    payload, signature = token.split(".")
    mutated = f"{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    with pytest.raises(Exception) as tampered:
        codec.decode_cursor(
            mutated,
            tenant_id=tenant_id,
            company_id=company_id,
            module_id="testsync",
            stream_id="default",
        )
    assert getattr(tampered.value, "code", None) == "SYNC_CURSOR_INVALID"


def test_pull_is_ordered_paginated_and_cursor_driven() -> None:
    principal = _principal()
    assert principal.company_id is not None
    provider = _Provider()
    journal = _Journal(
        position=3,
        batches=tuple(_batch(principal.company_id, value) for value in (1, 2, 3)),
    )
    availability = _Availability()
    service = SyncQueryService(
        _registry(provider),
        journal,
        _Transactions(),
        availability,
        SyncTokenCodec(b"y" * 32),
    )

    first = service.changes(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        cursor=None,
        limit=2,
        sync_protocol_version="1",
    )
    assert [batch.position for batch in first.batches] == [1, 2]
    assert first.has_more is True

    second = service.changes(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        cursor=first.next_cursor,
        limit=2,
        sync_protocol_version="1",
    )
    assert [batch.position for batch in second.batches] == [3]
    assert second.has_more is False
    assert provider.authorized == 2
    assert len(availability.calls) == 2


def test_bootstrap_keeps_original_start_cursor_across_keyset_pages() -> None:
    principal = _principal()
    provider = _Provider()
    provider.rows = [(key, _projection(key)) for key in ("001", "002", "003")]
    journal = _Journal(position=5)
    codec = SyncTokenCodec(b"z" * 32)
    service = SyncQueryService(
        _registry(provider),
        journal,
        _Transactions(),
        _Availability(),
        codec,
    )

    first = service.bootstrap(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        page_token=None,
        limit=2,
        sync_protocol_version="1",
    )
    assert [item.payload["key"] for item in first.items] == ["001", "002"]
    assert first.has_more is True
    assert first.next_page_token is not None

    # Cloud continues publishing while bootstrap pages are being read. The
    # continuation must retain S=5, not advance to the now-current 7.
    journal.position = 7
    second = service.bootstrap(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        page_token=first.next_page_token,
        limit=2,
        sync_protocol_version="1",
    )
    assert [item.payload["key"] for item in second.items] == ["003"]
    assert second.has_more is False
    assert second.next_page_token is None

    assert principal.tenant_id is not None
    assert principal.company_id is not None
    start_one = codec.decode_cursor(
        first.bootstrap_start_cursor,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        module_id="testsync",
        stream_id="default",
    )
    start_two = codec.decode_cursor(
        second.bootstrap_start_cursor,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        module_id="testsync",
        stream_id="default",
    )
    assert start_one == start_two == 5


def test_unsupported_protocol_fails_closed_before_reading_journal() -> None:
    principal = _principal()
    provider = _Provider()
    service = SyncQueryService(
        _registry(provider),
        _Journal(position=0),
        _Transactions(),
        _Availability(),
        SyncTokenCodec(b"p" * 32),
    )
    with pytest.raises(Exception) as captured:
        service.changes(
            principal=principal,
            module_id="testsync",
            stream_id="default",
            cursor=None,
            limit=10,
            sync_protocol_version="2",
        )
    assert getattr(captured.value, "code", None) == "SYNC_PROTOCOL_UNSUPPORTED"
