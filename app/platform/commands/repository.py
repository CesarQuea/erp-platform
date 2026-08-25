from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol
from uuid import UUID

from app.platform.commands.model import CommandExecutionRecord


class CommandExecutionRepository(Protocol):
    def claim(self, record: CommandExecutionRecord) -> bool:
        """Claim command_id inside the active Tenant transaction."""

    def get(self, command_id: UUID) -> CommandExecutionRecord | None:
        """Read a command execution inside the active Tenant transaction."""

    def complete(
        self,
        command_id: UUID,
        *,
        result_code: str,
        result_json: Mapping[str, object],
        committed_at: datetime,
    ) -> None:
        """Persist the minimal replay result before the transaction commits."""
