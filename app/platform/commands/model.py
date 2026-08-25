from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping
from uuid import UUID

from app.platform.identity.model import AuthenticatedPrincipal


class CommandScope(StrEnum):
    TENANT = "TENANT"
    COMPANY = "COMPANY"


@dataclass(frozen=True, slots=True)
class CommandRequest:
    command_id: UUID
    command_name: str
    command_schema_version: str
    scope: CommandScope
    expected_version: int | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, UUID):
            raise TypeError("command_id must be a UUID")
        if not isinstance(self.scope, CommandScope):
            raise TypeError("scope must be a CommandScope")
        if not self.command_name.strip():
            raise ValueError("command_name cannot be blank")
        if len(self.command_name) > 128:
            raise ValueError("command_name cannot exceed 128 characters")
        if not self.command_schema_version.strip():
            raise ValueError("command_schema_version cannot be blank")
        if len(self.command_schema_version) > 32:
            raise ValueError("command_schema_version cannot exceed 32 characters")
        if self.expected_version is not None:
            if not isinstance(self.expected_version, int) or isinstance(
                self.expected_version, bool
            ):
                raise TypeError("expected_version must be an int")
            if self.expected_version < 0:
                raise ValueError("expected_version cannot be negative")
        if self.correlation_id is not None:
            if not self.correlation_id or len(self.correlation_id) > 128:
                raise ValueError("correlation_id must contain 1..128 characters")


@dataclass(frozen=True, slots=True)
class CommandContext:
    command_id: UUID
    command_name: str
    command_schema_version: str
    scope: CommandScope
    tenant_id: UUID
    company_id: UUID | None
    actor_user_id: UUID
    session_id: UUID
    expected_version: int | None = None
    correlation_id: str | None = None

    @classmethod
    def from_principal(
        cls,
        request: CommandRequest,
        principal: AuthenticatedPrincipal,
    ) -> "CommandContext":
        if principal.tenant_id is None:
            raise ValueError("principal has no authorized tenant context")
        company_id: UUID | None = None
        if request.scope is CommandScope.COMPANY:
            if principal.company_id is None:
                raise ValueError("principal has no authorized company context")
            company_id = principal.company_id
        return cls(
            command_id=request.command_id,
            command_name=request.command_name.strip(),
            command_schema_version=request.command_schema_version.strip(),
            scope=request.scope,
            tenant_id=principal.tenant_id,
            company_id=company_id,
            actor_user_id=principal.user_id,
            session_id=principal.session_id,
            expected_version=request.expected_version,
            correlation_id=request.correlation_id,
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    code: str
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("result code cannot be blank")
        if len(self.code) > 128:
            raise ValueError("result code cannot exceed 128 characters")


@dataclass(frozen=True, slots=True)
class CommandExecutionOutcome:
    result: CommandResult
    replayed: bool


@dataclass(frozen=True, slots=True)
class CommandExecutionRecord:
    command_id: UUID
    command_name: str
    command_schema_version: str
    scope: CommandScope
    company_id: UUID | None
    actor_user_id: UUID
    fingerprint: str
    result_code: str | None = None
    result_json: Mapping[str, object] | None = None
    committed_at: datetime | None = None
