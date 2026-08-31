from __future__ import annotations

from typing import Protocol

from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.sync.model import BootstrapPage


class SyncProvider(Protocol):
    """Bounded-context adapter consumed by the transversal Sync foundation."""

    @property
    def module_id(self) -> str: ...

    @property
    def stream_ids(self) -> tuple[str, ...]: ...

    def authorize(
        self,
        *,
        principal: AuthenticatedPrincipal,
        stream_id: str,
    ) -> None: ...

    def bootstrap_page(
        self,
        *,
        principal: AuthenticatedPrincipal,
        stream_id: str,
        after_key: str | None,
        limit: int,
    ) -> BootstrapPage: ...
