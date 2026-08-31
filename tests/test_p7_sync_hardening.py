from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.infrastructure.observability.logging import JsonLogFormatter
from app.platform.sync.model import SyncBatch, SyncChange, SyncChangeKind
from app.platform.sync.service import SyncPublisher


class _RecordingRepository:
    def __init__(self) -> None:
        self.append_calls = 0

    def current_position(self, **kwargs) -> int:
        del kwargs
        return 0

    def list_batches(self, **kwargs):
        del kwargs
        return ()

    def append_batch(self, **kwargs) -> SyncBatch:
        self.append_calls += 1
        return SyncBatch(
            batch_id=kwargs["batch_id"],
            company_id=kwargs["company_id"],
            module_id=kwargs["module_id"],
            stream_id=kwargs["stream_id"],
            position=1,
            sync_protocol_version=kwargs["sync_protocol_version"],
            source_command_id=kwargs["source_command_id"],
            recorded_at=kwargs["recorded_at"],
            changes=kwargs["changes"],
        )


class _RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _change(secret: str = "functional-secret") -> SyncChange:
    entity_id = uuid4()
    return SyncChange(
        entity_type="record",
        entity_id=entity_id,
        change_kind=SyncChangeKind.UPSERT,
        schema_version="1",
        entity_version=1,
        payload={"id": str(entity_id), "secret": secret},
    )


def test_sync_publisher_rejects_invalid_scope_before_repository_access() -> None:
    repository = _RecordingRepository()
    publisher = SyncPublisher(repository, max_batch_bytes=64 * 1024)
    company_id = uuid4()

    invalid_calls = (
        {"company_id": "not-a-uuid", "module_id": "testsync", "stream_id": "default", "changes": (_change(),)},
        {"company_id": company_id, "module_id": "BadModule", "stream_id": "default", "changes": (_change(),)},
        {"company_id": company_id, "module_id": "testsync", "stream_id": "bad-stream", "changes": (_change(),)},
        {"company_id": company_id, "module_id": "testsync", "stream_id": "default", "changes": [_change()]},
        {"company_id": company_id, "module_id": "testsync", "stream_id": "default", "changes": (_change(),), "source_command_id": "not-a-uuid"},
    )

    for values in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            publisher.publish(**values)
        assert repository.append_calls == 0


def test_sync_publisher_rejects_naive_clock_before_repository_access() -> None:
    repository = _RecordingRepository()
    publisher = SyncPublisher(
        repository,
        max_batch_bytes=64 * 1024,
        clock=lambda: datetime(2026, 8, 30, 12, 0, 0),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        publisher.publish(
            company_id=uuid4(),
            module_id="testsync",
            stream_id="default",
            changes=(_change(),),
        )
    assert repository.append_calls == 0


def test_sync_publisher_logs_ids_counts_and_position_without_payload() -> None:
    repository = _RecordingRepository()
    publisher = SyncPublisher(
        repository,
        max_batch_bytes=64 * 1024,
        clock=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
    )
    command_id = uuid4()
    secret = "must-never-appear-in-sync-log"

    logger = logging.getLogger("app.platform.sync.service")
    collector = _RecordCollector()
    previous_level = logger.level
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    try:
        batch = publisher.publish(
            company_id=uuid4(),
            module_id="testsync",
            stream_id="default",
            changes=(_change(secret),),
            source_command_id=command_id,
        )
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous_level)

    record = next(
        record
        for record in collector.records
        if record.getMessage() == "sync_batch_published"
    )
    assert record.batch_id == str(batch.batch_id)
    assert record.command_id == str(command_id)
    assert record.module_id == "testsync"
    assert record.stream_id == "default"
    assert record.position == 1
    assert record.change_count == 1
    assert not hasattr(record, "payload")
    assert not hasattr(record, "changes_json")
    assert secret not in record.getMessage()


def test_json_log_formatter_drops_sync_payload_tokens_and_cursors() -> None:
    record = logging.LogRecord(
        name="app.platform.sync.query",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="sync_pull_succeeded",
        args=(),
        exc_info=None,
    )
    record.batch_id = str(uuid4())
    record.module_id = "testsync"
    record.stream_id = "default"
    record.position = 7
    record.batch_count = 2
    record.payload = {"secret": "payload-secret"}
    record.changes_json = [{"secret": "changes-secret"}]
    record.cursor = "opaque-cursor-secret"
    record.page_token = "opaque-page-token-secret"
    record.access_token = "access-token-secret"

    rendered = JsonLogFormatter().format(record)
    document = json.loads(rendered)

    assert document["batch_id"] == record.batch_id
    assert document["module_id"] == "testsync"
    assert document["position"] == 7
    assert document["batch_count"] == 2
    for forbidden in (
        "payload",
        "changes_json",
        "cursor",
        "page_token",
        "access_token",
    ):
        assert forbidden not in document
    assert "secret" not in rendered
