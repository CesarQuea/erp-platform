from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar


T = TypeVar("T")


class TransactionBoundary(Protocol):
    """Framework-neutral transaction boundary for future application services."""

    def run(self, operation: Callable[[], T]) -> T:
        """Run one application operation atomically."""
