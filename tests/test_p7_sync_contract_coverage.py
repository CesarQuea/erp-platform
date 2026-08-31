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
from app.platform.sync.serialization import change_from_document, change_to_document
from app.platform.sync.token import SyncTokenCodec


class _Boundary:
    def run(self, operation):
        return operation()


class _Transactions:
    def for_tenant(self, context):
        del context
        return _Boundary()


class _Availability:
    def require_enabled(self, context, company_id: UUID, module_id: str):
        del context, company_id, module_id


class _Journal:
    def __init__(self, *, position: int, batches: tuple[SyncBatch, ...] = ()) -> None:
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
        entity_id = uuid4()
        self.baseline = SyncProjection(
            entity_type="record",
            entity_id=entity_id,
            schema_version="1",
            entity_version=1,
            payload={"id": str(entity_id), "value": "baseline"},
        )

    def authorize(self, *, principal, stream_id: str) -> None:
        del principal
        assert stream_id == "default"

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
            return BootstrapPage(items=(self.baseline,), next_key=None, has_more=False)
        return BootstrapPage(items=(), next_key=None, has_more=False)


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        session_id=uuid4(),
        tenant_id=uuid4(),
        company_id=uuid4(),
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


def _change(*, value: str, kind: SyncChangeKind = SyncChangeKind.UPSERT) -> SyncChange:
    entity_id = uuid4()
    return SyncChange(
        entity_type="record",
        entity_id=entity_id,
        change_kind=kind,
        schema_version="1",
        entity_version=1,
        payload=(None if kind is SyncChangeKind.TOMBSTONE else {"id": str(entity_id), "value": value}),
    )


def _batch(company_id: UUID, position: int, changes: tuple[SyncChange, ...]) -> SyncBatch:
    return SyncBatch(
        batch_id=uuid4(),
        company_id=company_id,
        module_id="testsync",
        stream_id="default",
        position=position,
        sync_protocol_version="1",
        recorded_at=datetime.now(timezone.utc),
        changes=changes,
    )


def _service(
    principal: AuthenticatedPrincipal,
    journal: _Journal,
    *,
    secret: bytes = b"p7-contract-coverage-secret-32-bytes!!",
) -> SyncQueryService:
    del principal
    provider = _Provider()
    return SyncQueryService(
        _registry(provider),
        journal,
        _Transactions(),
        _Availability(),
        SyncTokenCodec(secret),
    )


def test_tombstone_round_trips_without_payload() -> None:
    tombstone = _change(value="deleted", kind=SyncChangeKind.TOMBSTONE)
    document = change_to_document(tombstone)
    restored = change_from_document(document)

    assert document["change_kind"] == "TOMBSTONE"
    assert document["payload"] is None
    assert restored == tombstone


def test_cursor_rejects_every_cross_scope_dimension() -> None:
    codec = SyncTokenCodec(b"p7-cross-scope-secret-32-bytes-min!!")
    tenant_id = uuid4()
    company_id = uuid4()
    token = codec.encode_cursor(
        tenant_id=tenant_id,
        company_id=company_id,
        module_id="testsync",
        stream_id="default",
        position=7,
    )

    wrong_scopes = (
        dict(tenant_id=uuid4(), company_id=company_id, module_id="testsync", stream_id="default"),
        dict(tenant_id=tenant_id, company_id=uuid4(), module_id="testsync", stream_id="default"),
        dict(tenant_id=tenant_id, company_id=company_id, module_id="othermodule", stream_id="default"),
        dict(tenant_id=tenant_id, company_id=company_id, module_id="testsync", stream_id="otherstream"),
    )

    for scope in wrong_scopes:
        with pytest.raises(Exception) as captured:
            codec.decode_cursor(token, **scope)
        assert getattr(captured.value, "code", None) == "SYNC_CURSOR_INVALID"


def test_pull_limit_never_splits_an_indivisible_batch() -> None:
    principal = _principal()
    assert principal.company_id is not None
    first = _batch(
        principal.company_id,
        1,
        (_change(value="one"), _change(value="two")),
    )
    second = _batch(principal.company_id, 2, (_change(value="three"),))
    journal = _Journal(position=2, batches=(first, second))
    service = _service(principal, journal)

    page = service.changes(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        cursor=None,
        limit=1,
        sync_protocol_version="1",
    )

    assert len(page.batches) == 1
    assert page.batches[0].position == 1
    assert len(page.batches[0].changes) == 2
    assert page.has_more is True


def test_bootstrap_start_cursor_drives_required_incremental_catch_up() -> None:
    principal = _principal()
    assert principal.company_id is not None
    journal = _Journal(position=5)
    service = _service(principal, journal)

    bootstrap = service.bootstrap(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        page_token=None,
        limit=100,
        sync_protocol_version="1",
    )
    assert len(bootstrap.items) == 1
    assert bootstrap.has_more is False

    # Cloud publishes S+1 and S+2 while/after the baseline is downloaded.
    journal.position = 7
    journal.batches = (
        _batch(principal.company_id, 6, (_change(value="six"),)),
        _batch(principal.company_id, 7, (_change(value="seven"),)),
    )

    catch_up = service.changes(
        principal=principal,
        module_id="testsync",
        stream_id="default",
        cursor=bootstrap.bootstrap_start_cursor,
        limit=100,
        sync_protocol_version="1",
    )

    assert [batch.position for batch in catch_up.batches] == [6, 7]
    assert catch_up.has_more is False
