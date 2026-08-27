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


_TEST_ENV = "P5_MIGRATION_TEST_TENANT_DATABASES_JSON"
_O4_HEAD = "0004_o4_milking_lifecycle_hardening"
_P5_HEAD = "0005_p5_module_activation"


def _entries() -> list[tuple[UUID, str]]:
    raw = os.getenv(_TEST_ENV)
    if not raw:
        pytest.skip(f"{_TEST_ENV} is required for P-5 forward migration tests")
    entries: list[tuple[UUID, str]] = []
    for raw_tenant_id, config in json.loads(raw).items():
        url = config["database_url"]
        if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            entries.append((UUID(str(raw_tenant_id)), url))
    if len(entries) < 2:
        pytest.skip(f"{_TEST_ENV} must contain two dedicated PostgreSQL Tenant DBs")
    return entries[:2]


def test_forward_migration_o4_to_p5_on_two_physical_tenant_databases():
    entries = _entries()
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, url in entries
        }
    )
    root = Path(__file__).resolve().parents[1]
    o4_runner = TenantMigrationRunner(
        repository_root=root,
        target_revision=_O4_HEAD,
    )

    # Dedicated verification databases may be reused across runs. If a prior
    # run already reached P-5, restore the exact O-4 starting point first.
    for _, url in entries:
        current = o4_runner.current_revision(url)
        if current is not None and current != _O4_HEAD:
            command.downgrade(o4_runner._config(url), _O4_HEAD)

    o4_provisioner = TenantProvisioner(registry, migration_runner=o4_runner)
    for tenant_id, url in entries:
        assert o4_provisioner.provision(TenantContext(tenant_id)) == _O4_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            assert "platform_module_activations" not in inspect(engine).get_table_names()
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

    p5_runner = TenantMigrationRunner(repository_root=root)
    p5_provisioner = TenantProvisioner(registry, migration_runner=p5_runner)
    for tenant_id, url in entries:
        assert p5_provisioner.provision(TenantContext(tenant_id)) == _P5_HEAD
        assert p5_provisioner.provision(TenantContext(tenant_id)) == _P5_HEAD
        from sqlalchemy import create_engine

        engine = create_engine(normalize_database_url(url))
        try:
            inspector = inspect(engine)
            assert "platform_module_activations" in inspector.get_table_names()
            pk = inspector.get_pk_constraint("platform_module_activations")
            assert pk["constrained_columns"] == ["company_id", "module_id"]
            with engine.connect() as connection:
                metadata = connection.execute(
                    select(
                        TenantMetadataRecord.tenant_id,
                        TenantMetadataRecord.schema_version,
                    )
                ).one()
            assert metadata.tenant_id == tenant_id
            assert metadata.schema_version == _P5_HEAD
        finally:
            engine.dispose()
