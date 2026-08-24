from __future__ import annotations

import unicodedata
from dataclasses import dataclass


class PasswordPolicyError(ValueError):
    pass


def normalize_login(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not normalized:
        raise ValueError("login cannot be blank")
    return normalized


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    minimum_length: int = 8
    maximum_length: int = 128

    def validate(self, *, password: str, login: str) -> None:
        if len(password) < self.minimum_length:
            raise PasswordPolicyError(
                f"password must contain at least {self.minimum_length} characters"
            )
        if len(password) > self.maximum_length:
            raise PasswordPolicyError(
                f"password must contain at most {self.maximum_length} characters"
            )
        if normalize_login(password) == normalize_login(login):
            raise PasswordPolicyError("password cannot equal login")
