from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


_MODULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class ModuleActivationState(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    module_id: str
    module_version: str
    configuration_namespace: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not _MODULE_ID_RE.fullmatch(
            self.module_id
        ):
            raise ValueError(
                "module_id must match ^[a-z][a-z0-9_]{0,63}$"
            )
        if not isinstance(self.module_version, str) or not _SEMVER_RE.fullmatch(
            self.module_version
        ):
            raise ValueError("module_version must be SemVer compatible")
        if not isinstance(self.configuration_namespace, str) or not _NAMESPACE_RE.fullmatch(
            self.configuration_namespace
        ):
            raise ValueError("configuration_namespace is invalid")
        if self.description is not None:
            if not isinstance(self.description, str):
                raise TypeError("description must be a string or None")
            if not self.description.strip():
                raise ValueError("description cannot be blank")
            if len(self.description) > 255:
                raise ValueError("description cannot exceed 255 characters")


@dataclass(frozen=True, slots=True)
class CompanyModuleActivation:
    company_id: UUID
    module_id: str
    state: ModuleActivationState
    version: int
    created_at: datetime
    created_by: UUID
    updated_at: datetime | None = None
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.company_id, UUID):
            raise TypeError("company_id must be a UUID")
        if not isinstance(self.created_by, UUID):
            raise TypeError("created_by must be a UUID")
        if self.updated_by is not None and not isinstance(self.updated_by, UUID):
            raise TypeError("updated_by must be a UUID or None")
        if not isinstance(self.state, ModuleActivationState):
            raise TypeError("state must be a ModuleActivationState")
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise TypeError("version must be an int")
        if self.version < 1:
            raise ValueError("persisted activation version must be positive")
        if not _MODULE_ID_RE.fullmatch(self.module_id):
            raise ValueError("module_id is invalid")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        if (self.updated_at is None) != (self.updated_by is None):
            raise ValueError("updated_at and updated_by must be set together")
