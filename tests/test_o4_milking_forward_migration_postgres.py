from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import inspect, select

from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.models import TenantMetadataRecord
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.database.runtime import normalize_database_url
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


_TEST_ENV = "O4_MIGRATION_TEST_TENANT_DATABASES_JSON"
_P4_HEAD = "0002_p4_command_execution"
_O4_HEAD = "0004_o4_milking_lifecycle_hardening"
_MILKING_TABLES = {
    "milking_output_profiles",
    "milking_configurations",
    "milking_sessions",
    "milking_outputs",
    "milking_annulment_requests",
    "milking_audit_events",
}


def _entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for O-4 forward migration tests")
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain two dedicated PostgreSQL tenant databases")
    return entries[:2]


def test_forward_migration_p4_to_o4_on_two_physical_tenant_databases() -> None:
    entries = _entries()
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    root = Path(__file__).resolve().parents[1]
    p4_runner = TenantMigrationRunner(
        repository_root=root,
        target_revision=_P4_HEAD,
    )

    # Dedicated verification databases may be reused across runs and may already
    # be at O-4/P-5. Restore the exact historical P-4 starting point before
    # proving the original P-4 -> O-4 migration path.
    for _, url in entries:
        current = p4_runner.current_revision(url)
        if current is not None and current != _P4_HEAD:
            command.downgrade(p4_runner._config(url), _P4_HEAD)

    p4_provisioner = TenantProvisioner(registry, migration_runner=p4_runner)
    for tenant_id, url in entries:
        context = TenantContext(tenant_id)
        assert p4_provisioner.provision(context) == _P4_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            tables = set(inspect(engine).get_table_names())
            assert "platform_command_executions" in tables
            assert _MILKING_TABLES.isdisjoint(tables)
        finally:
            engine.dispose()

    o4_runner = TenantMigrationRunner(
        repository_root=root,
        target_revision=_O4_HEAD,
    )
    o4_provisioner = TenantProvisioner(registry, migration_runner=o4_runner)
    for tenant_id, url in entries:
        context = TenantContext(tenant_id)
        assert o4_provisioner.provision(context) == _O4_HEAD
        assert o4_provisioner.provision(context) == _O4_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            tables = set(inspect(engine).get_table_names())
            assert _MILKING_TABLES <= tables
            with engine.connect() as connection:
                metadata = connection.execute(
                    select(
                        TenantMetadataRecord.tenant_id,
                        TenantMetadataRecord.schema_version,
                    )
                ).one()
            assert metadata.tenant_id == tenant_id
            assert metadata.schema_version == _O4_HEAD
        finally:
            engine.dispose()
