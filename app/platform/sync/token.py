from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from uuid import UUID

from app.platform.sync.errors import sync_cursor_invalid, sync_protocol_unsupported
from app.platform.sync.model import SYNC_PROTOCOL_VERSION


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


@dataclass(frozen=True, slots=True)
class BootstrapContinuation:
    start_position: int
    after_key: str


class SyncTokenCodec:
    """Tamper-evident, opaque first-party cursor/continuation tokens."""

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, bytes):
            raise TypeError("Sync token secret must be bytes")
        if len(secret) < 32:
            raise ValueError("Sync token secret must contain at least 256 bits")
        self._secret = secret

    def encode_cursor(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        position: int,
    ) -> str:
        if position < 0:
            raise ValueError("cursor position cannot be negative")
        return self._encode(
            {
                "kind": "cursor",
                "protocol": SYNC_PROTOCOL_VERSION,
                "tenant_id": str(tenant_id),
                "company_id": str(company_id),
                "module_id": module_id,
                "stream_id": stream_id,
                "position": position,
            }
        )

    def decode_cursor(
        self,
        token: str,
        *,
        tenant_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
    ) -> int:
        document = self._decode_scoped(
            token,
            expected_kind="cursor",
            tenant_id=tenant_id,
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
        )
        position = document.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            raise sync_cursor_invalid()
        return position

    def encode_bootstrap_continuation(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
        start_position: int,
        after_key: str,
    ) -> str:
        if start_position < 0:
            raise ValueError("bootstrap start position cannot be negative")
        if not after_key:
            raise ValueError("bootstrap after_key cannot be blank")
        return self._encode(
            {
                "kind": "bootstrap",
                "protocol": SYNC_PROTOCOL_VERSION,
                "tenant_id": str(tenant_id),
                "company_id": str(company_id),
                "module_id": module_id,
                "stream_id": stream_id,
                "start_position": start_position,
                "after_key": after_key,
            }
        )

    def decode_bootstrap_continuation(
        self,
        token: str,
        *,
        tenant_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
    ) -> BootstrapContinuation:
        document = self._decode_scoped(
            token,
            expected_kind="bootstrap",
            tenant_id=tenant_id,
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
        )
        start_position = document.get("start_position")
        after_key = document.get("after_key")
        if (
            not isinstance(start_position, int)
            or isinstance(start_position, bool)
            or start_position < 0
            or not isinstance(after_key, str)
            or not after_key
        ):
            raise sync_cursor_invalid()
        return BootstrapContinuation(start_position=start_position, after_key=after_key)

    def _encode(self, document: dict[str, object]) -> str:
        raw = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        signature = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return f"{_b64encode(raw)}.{_b64encode(signature)}"

    def _decode_scoped(
        self,
        token: str,
        *,
        expected_kind: str,
        tenant_id: UUID,
        company_id: UUID,
        module_id: str,
        stream_id: str,
    ) -> dict[str, object]:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            raw = _b64decode(encoded_payload)
            supplied_signature = _b64decode(encoded_signature)
            expected_signature = hmac.new(self._secret, raw, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("signature mismatch")
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("token payload is not an object")
        except Exception:
            raise sync_cursor_invalid() from None

        protocol = decoded.get("protocol")
        if protocol != SYNC_PROTOCOL_VERSION:
            raise sync_protocol_unsupported()
        if (
            decoded.get("kind") != expected_kind
            or decoded.get("tenant_id") != str(tenant_id)
            or decoded.get("company_id") != str(company_id)
            or decoded.get("module_id") != module_id
            or decoded.get("stream_id") != stream_id
        ):
            # Deliberately do not disclose which scope field mismatched.
            raise sync_cursor_invalid()
        return decoded
