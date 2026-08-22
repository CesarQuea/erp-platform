from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlatformError(Exception):
    code: str
    message: str
    status_code: int = 400

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
