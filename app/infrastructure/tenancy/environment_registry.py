from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from app.platform.tenancy.errors import (
    TenantNotConfiguredError,
    TenantRegistryConfigurationError,
)
from app.platform.tenancy.registry import TenantConnectionConfig


class EnvironmentTenantRegistry:
    """Configuration-backed registry intended for bootstrap/test until a control plane exists."""

    def __init__(self, entries: Mapping[UUID, TenantConnectionConfig] | None = None) -> None:
        self._entries: dict[UUID, TenantConnectionConfig] = {}
        for tenant_id, config in (entries or {}).items():
            if not isinstance(tenant_id, UUID):
                raise TenantRegistryConfigurationError("Tenant registry key must be a UUID")
            if config.tenant_id != tenant_id:
                raise TenantRegistryConfigurationError(
                    "Tenant registry key must match connection config tenant_id"
                )
            self._entries[tenant_id] = config

    @classmethod
    def from_json(cls, payload: str | None) -> "EnvironmentTenantRegistry":
        if payload is None or not payload.strip():
            return cls()
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            raise TenantRegistryConfigurationError("TENANT_DATABASES_JSON is not valid JSON") from None
        if not isinstance(raw, dict):
            raise TenantRegistryConfigurationError("TENANT_DATABASES_JSON must be a JSON object")

        entries: dict[UUID, TenantConnectionConfig] = {}
        for raw_tenant_id, raw_config in raw.items():
            try:
                tenant_id = UUID(str(raw_tenant_id))
            except (TypeError, ValueError, AttributeError):
                raise TenantRegistryConfigurationError("Tenant registry contains an invalid tenant UUID") from None
            if not isinstance(raw_config, dict):
                raise TenantRegistryConfigurationError("Each tenant registry entry must be a JSON object")
            database_url = raw_config.get("database_url")
            is_active = raw_config.get("active", True)
            if not isinstance(database_url, str) or not database_url.strip():
                raise TenantRegistryConfigurationError("Tenant registry entry requires database_url")
            if not isinstance(is_active, bool):
                raise TenantRegistryConfigurationError("Tenant registry active flag must be boolean")
            entries[tenant_id] = TenantConnectionConfig(
                tenant_id=tenant_id,
                database_url=database_url,
                is_active=is_active,
            )
        return cls(entries)

    def get(self, tenant_id: UUID) -> TenantConnectionConfig:
        try:
            return self._entries[tenant_id]
        except KeyError:
            raise TenantNotConfiguredError(f"Tenant {tenant_id} is not configured") from None
