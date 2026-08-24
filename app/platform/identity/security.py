from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    issuer: str
    audience: str
    user_id: UUID
    session_id: UUID
    token_id: UUID
    issued_at: datetime
    expires_at: datetime
    tenant_id: UUID | None = None
    company_id: UUID | None = None


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class AccessTokenCodec(Protocol):
    def encode(self, claims: AccessTokenClaims) -> str: ...

    def decode(self, token: str) -> AccessTokenClaims: ...


@dataclass(frozen=True, slots=True)
class RefreshTokenMaterial:
    plaintext: str
    token_hash: str


class RefreshTokenGenerator(Protocol):
    def generate(self) -> RefreshTokenMaterial: ...

    def hash_token(self, token: str) -> str: ...
