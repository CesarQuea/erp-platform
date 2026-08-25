from __future__ import annotations

import json
import logging

from app.infrastructure.observability.logging import JsonLogFormatter


def test_p4_audit_logging_only_emits_allowlisted_safe_fields():
    record = logging.LogRecord(
        name="app.platform.commands.service",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="command_succeeded",
        args=(),
        exc_info=None,
    )
    record.command_id = "11111111-1111-1111-1111-111111111111"
    record.command_name = "test.command"
    record.scope = "COMPANY"
    record.expected_version = 3
    record.outcome = "SUCCEEDED"
    record.tenant_id = "22222222-2222-2222-2222-222222222222"
    record.company_id = "33333333-3333-3333-3333-333333333333"
    record.payload = {"secret": "must-not-leak"}
    record.result_json = {"secret": "must-not-leak"}
    record.password = "must-not-leak"
    record.access_token = "must-not-leak"

    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["command_id"] == record.command_id
    assert payload["command_name"] == "test.command"
    assert payload["scope"] == "COMPANY"
    assert payload["expected_version"] == 3
    assert payload["outcome"] == "SUCCEEDED"
    assert "payload" not in payload
    assert "result_json" not in payload
    assert "password" not in payload
    assert "access_token" not in payload
