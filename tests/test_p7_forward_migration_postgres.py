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

_TEST_ENV = "P7_MIGRATION_TEST_TENANT_DATABASES_JSON"
_P5_HEAD = "0005_p5_module_activation"
_P7_HEAD = "0006_p7_sync_foundation"


def _entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for P-7 forward migration tests")
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain two dedicated PostgreSQL Tenant DBs")
    return entries[:2]


def test_forward_migration_p5_to_p7_on_two_physical_tenant_databases() -> None:
    entries = _entries()
    root = Path(__file__).resolve().parents[1]
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    p5_runner = TenantMigrationRunner(repository_root=root, target_revision=_P5_HEAD)

    for _, url in entries:
        current = p5_runner.current_revision(url)
        if current is not None and current != _P5_HEAD:
            command.downgrade(p5_runner._config(url), _P5_HEAD)

    p5 = TenantProvisioner(registry, migration_runner=p5_runner)
    for tenant_id, url in entries:
        assert p5.provision(TenantContext(tenant_id)) == _P5_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            tables = inspect(engine).get_table_names()
            assert "platform_module_activations" in tables
            assert "platform_sync_streams" not in tables
            assert "platform_sync_batches" not in tables
        finally:
            engine.dispose()

    p7_runner = TenantMigrationRunner(repository_root=root)
    p7 = TenantProvisioner(registry, migration_runner=p7_runner)
    for tenant_id, url in entries:
        assert p7.provision(TenantContext(tenant_id)) == _P7_HEAD
        assert p7.provision(TenantContext(tenant_id)) == _P7_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            assert "platform_sync_streams" in tables
            assert "platform_sync_batches" in tables
            stream_pk = inspector.get_pk_constraint("platform_sync_streams")
            assert stream_pk["constrained_columns"] == ["company_id", "module_id", "stream_id"]
            batch_pk = inspector.get_pk_constraint("platform_sync_batches")
            assert batch_pk["constrained_columns"] == ["batch_id"]
            unique_sets = {
                tuple(item["column_names"])
                for item in inspector.get_unique_constraints("platform_sync_batches")
            }
            assert ("company_id", "module_id", "stream_id", "position") in unique_sets
            with engine.connect() as connection:
                metadata = connection.execute(
                    select(
                        TenantMetadataRecord.tenant_id,
                        TenantMetadataRecord.schema_version,
                    )
                ).one()
            assert metadata.tenant_id == tenant_id
            assert metadata.schema_version == _P7_HEAD
        finally:
            engine.dispose()
