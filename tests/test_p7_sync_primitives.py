from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.platform.modules.model import ModuleDefinition
from app.platform.modules.registry import ModuleNotRegisteredError, ModuleRegistry
from app.platform.sync.errors import (
    sync_batch_too_large,
    sync_cursor_expired,
    sync_cursor_invalid,
    sync_protocol_unsupported,
    sync_schema_unsupported,
    sync_stream_not_found,
)
from app.platform.sync.model import (
    BootstrapPage,
    SyncBatch,
    SyncChange,
    SyncChangeKind,
    SyncProjection,
    validate_stream_id,
)
from app.platform.sync.registry import (
    SyncProviderRegistry,
    SyncProviderRegistryError,
    SyncProviderRegistryFrozenError,
    SyncStreamNotRegisteredError,
)


class _Provider:
    module_id = "testsync"
    stream_ids = ("default",)

    def authorize(self, *, principal, stream_id: str) -> None:
        del principal, stream_id

    def bootstrap_page(
        self,
        *,
        principal,
        stream_id: str,
        after_key: str | None,
        limit: int,
    ) -> BootstrapPage:
        del principal, stream_id, after_key, limit
        return BootstrapPage(items=(), next_key=None, has_more=False)


def _module_registry() -> ModuleRegistry:
    registry = ModuleRegistry(
        [
            ModuleDefinition(
                module_id="testsync",
                module_version="1.0.0",
                configuration_namespace="testsync",
            )
        ]
    )
    registry.freeze()
    return registry


def test_sync_change_and_batch_invariants() -> None:
    entity_id = uuid4()
    change = SyncChange(
        entity_type="record",
        entity_id=entity_id,
        change_kind=SyncChangeKind.UPSERT,
        schema_version="1",
        entity_version=2,
        payload={"id": str(entity_id), "name": "value"},
    )
    batch = SyncBatch(
        batch_id=uuid4(),
        company_id=uuid4(),
        module_id="testsync",
        stream_id="default",
        position=1,
        sync_protocol_version="1",
        recorded_at=datetime.now(timezone.utc),
        changes=(change,),
    )

    assert batch.changes == (change,)
    assert batch.position == 1

    with pytest.raises(ValueError, match="UPSERT"):
        SyncChange(
            entity_type="record",
            entity_id=uuid4(),
            change_kind=SyncChangeKind.UPSERT,
            schema_version="1",
            payload=None,
        )

    with pytest.raises(ValueError, match="cannot be empty"):
        SyncBatch(
            batch_id=uuid4(),
            company_id=uuid4(),
            module_id="testsync",
            stream_id="default",
            position=1,
            sync_protocol_version="1",
            recorded_at=datetime.now(timezone.utc),
            changes=(),
        )


def test_bootstrap_projection_and_page_are_strict() -> None:
    projection = SyncProjection(
        entity_type="record",
        entity_id=uuid4(),
        schema_version="1",
        entity_version=1,
        payload={"name": "value"},
    )
    page = BootstrapPage(items=(projection,), next_key="record-1", has_more=True)
    assert page.items == (projection,)

    with pytest.raises(ValueError, match="requires next_key"):
        BootstrapPage(items=(), next_key=None, has_more=True)
    with pytest.raises(ValueError, match="final bootstrap page"):
        BootstrapPage(items=(), next_key="unexpected", has_more=False)


def test_stream_ids_are_technical_and_stable() -> None:
    validate_stream_id("default")
    validate_stream_id("operational_2")
    for value in ("", "Default", "has-dash", "two words"):
        with pytest.raises(ValueError):
            validate_stream_id(value)


def test_sync_provider_registry_extends_p5_module_registry() -> None:
    registry = SyncProviderRegistry(_module_registry())
    provider = _Provider()
    registry.register(provider)
    registry.freeze()

    assert registry.get("testsync", "default") is provider
    assert tuple(registry.list_streams("testsync")) == ("default",)
    assert registry.is_frozen

    with pytest.raises(SyncStreamNotRegisteredError):
        registry.get("testsync", "other")
    with pytest.raises(SyncProviderRegistryFrozenError):
        registry.register(provider)


def test_sync_provider_requires_registered_module_and_unique_streams() -> None:
    missing_modules = ModuleRegistry()
    missing_modules.freeze()
    with pytest.raises(ModuleNotRegisteredError):
        SyncProviderRegistry(missing_modules).register(_Provider())

    class DuplicateStreamsProvider(_Provider):
        stream_ids = ("default", "default")

    with pytest.raises(SyncProviderRegistryError, match="duplicate stream_id"):
        SyncProviderRegistry(_module_registry()).register(DuplicateStreamsProvider())


def test_public_sync_errors_use_frozen_codes_and_statuses() -> None:
    errors = [
        (sync_stream_not_found(), "SYNC_STREAM_NOT_FOUND", 404),
        (sync_cursor_invalid(), "SYNC_CURSOR_INVALID", 400),
        (sync_cursor_expired(), "SYNC_CURSOR_EXPIRED", 410),
        (sync_protocol_unsupported(), "SYNC_PROTOCOL_UNSUPPORTED", 409),
        (sync_schema_unsupported(), "SYNC_SCHEMA_UNSUPPORTED", 409),
        (sync_batch_too_large(), "SYNC_BATCH_TOO_LARGE", 500),
    ]
    for error, code, status in errors:
        assert error.code == code
        assert error.status_code == status
