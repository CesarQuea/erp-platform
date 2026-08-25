from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, inspect, select

from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.models import TenantMetadataRecord
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.errors import TenantDatabaseIdentityError, TenantInactiveError
from app.platform.tenancy.registry import TenantConnectionConfig


def test_provisioning_runs_alembic_and_is_idempotent(tmp_path: Path):
    tenant_id = uuid4()
    database_path = tmp_path / "tenant.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, database_url)}
    )
    runner = TenantMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    provisioner = TenantProvisioner(registry, migration_runner=runner)

    revision = provisioner.provision(TenantContext(tenant_id))
    assert revision == "0002_p4_command_execution"
    assert provisioner.provision(TenantContext(tenant_id)) == revision

    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "companies",
            "platform_command_executions",
            "platform_tenant_metadata",
        }
        with engine.connect() as connection:
            row = connection.execute(
                select(
                    TenantMetadataRecord.tenant_id,
                    TenantMetadataRecord.schema_version,
                )
            ).one()
        assert row.tenant_id == tenant_id
        assert row.schema_version == revision
    finally:
        engine.dispose()


class FailIfCalledMigrationRunner:
    def upgrade(self, database_url: str) -> None:
        raise AssertionError("migration must not run after tenant identity mismatch")

    def current_revision(self, database_url: str) -> str | None:
        raise AssertionError("revision must not be queried after tenant identity mismatch")


def test_provisioning_rejects_existing_database_with_other_tenant_before_migration(
    tmp_path: Path,
):
    requested_tenant = uuid4()
    actual_tenant = uuid4()
    database_path = tmp_path / "wrong-tenant.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    TenantMetadataRecord.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(TenantMetadataRecord).values(
                singleton_key=1,
                tenant_id=actual_tenant,
                schema_version="existing",
                created_at=datetime.now(timezone.utc),
            )
        )
    engine.dispose()

    registry = EnvironmentTenantRegistry(
        {requested_tenant: TenantConnectionConfig(requested_tenant, database_url)}
    )
    provisioner = TenantProvisioner(
        registry,
        migration_runner=FailIfCalledMigrationRunner(),
    )

    with pytest.raises(TenantDatabaseIdentityError):
        provisioner.provision(TenantContext(requested_tenant))


def test_provisioning_rejects_inactive_tenant(tmp_path: Path):
    tenant_id = uuid4()
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(
                tenant_id,
                f"sqlite+pysqlite:///{tmp_path / 'inactive.db'}",
                is_active=False,
            )
        }
    )
    with pytest.raises(TenantInactiveError):
        TenantProvisioner(registry).provision(TenantContext(tenant_id))
