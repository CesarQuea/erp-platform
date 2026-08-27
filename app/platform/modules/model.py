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


def validate_module_id(module_id: str) -> None:
    if not isinstance(module_id, str) or not _MODULE_ID_RE.fullmatch(module_id):
        raise ValueError("module_id must match ^[a-z][a-z0-9_]{0,63}$")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


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
        validate_module_id(self.module_id)
        if not isinstance(self.module_version, str) or not _SEMVER_RE.fullmatch(
            self.module_version
        ):
            raise ValueError("module_version must be SemVer compatible")
        if not isinstance(self.configuration_namespace, str) or not _NAMESPACE_RE.fullmatch(
            self.configuration_namespace
        ):
            raise ValueError("configuration_namespace is invalid")
        if self.configuration_namespace != self.module_id:
            raise ValueError(
                "P-5 v0.1 requires configuration_namespace to equal module_id"
            )
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
        validate_module_id(self.module_id)
        _require_aware(self.created_at, "created_at")
        if self.updated_at is not None:
            _require_aware(self.updated_at, "updated_at")
        if (self.updated_at is None) != (self.updated_by is None):
            raise ValueError("updated_at and updated_by must be set together")
        if self.version == 1 and self.updated_at is not None:
            raise ValueError("version 1 activation cannot have update metadata")
        if self.version > 1 and self.updated_at is None:
            raise ValueError("version > 1 activation requires update metadata")


@dataclass(frozen=True, slots=True)
class ChangeModuleActivation:
    command_id: UUID
    module_id: str
    expected_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, UUID):
            raise TypeError("command_id must be a UUID")
        validate_module_id(self.module_id)
        if not isinstance(self.expected_version, int) or isinstance(
            self.expected_version, bool
        ):
            raise TypeError("expected_version must be an int")
        if self.expected_version < 0:
            raise ValueError("expected_version cannot be negative")


@dataclass(frozen=True, slots=True)
class CompanyModuleStatus:
    definition: ModuleDefinition
    state: ModuleActivationState
    version: int
    activation_present: bool
    effective_enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.definition, ModuleDefinition):
            raise TypeError("definition must be a ModuleDefinition")
        if not isinstance(self.state, ModuleActivationState):
            raise TypeError("state must be a ModuleActivationState")
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise TypeError("version must be an int")
        if self.version < 0:
            raise ValueError("version cannot be negative")
        if not isinstance(self.activation_present, bool):
            raise TypeError("activation_present must be a bool")
        if not isinstance(self.effective_enabled, bool):
            raise TypeError("effective_enabled must be a bool")

        if not self.activation_present:
            if self.version != 0:
                raise ValueError("absent activation must have version 0")
            if self.state is not ModuleActivationState.DISABLED:
                raise ValueError("absent activation must be effectively DISABLED")
            if self.effective_enabled:
                raise ValueError("absent activation cannot be effectively enabled")
            return

        if self.version < 1:
            raise ValueError("present activation must have a positive version")
        if self.effective_enabled != (self.state is ModuleActivationState.ENABLED):
            raise ValueError("effective_enabled must match persisted activation state")
