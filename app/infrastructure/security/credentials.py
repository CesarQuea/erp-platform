from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.platform.identity.security import RefreshTokenMaterial


class Argon2idPasswordHasher:
    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False


class SecureRefreshTokenGenerator:
    def __init__(self, *, bytes_length: int = 32) -> None:
        if bytes_length < 32:
            raise ValueError("refresh token entropy must be at least 256 bits")
        self._bytes_length = bytes_length

    def generate(self) -> RefreshTokenMaterial:
        token = secrets.token_urlsafe(self._bytes_length)
        return RefreshTokenMaterial(token, self.hash_token(token))

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
