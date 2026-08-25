from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, inspect

from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.provisioning import TenantProvisioner
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


def _provision(path: Path, tenant_id):
    database_url = f"sqlite+pysqlite:///{path}"
    registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, database_url)}
    )
    runner = TenantMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    revision = TenantProvisioner(registry, migration_runner=runner).provision(
        TenantContext(tenant_id)
    )
    return database_url, revision


def test_p4_migration_is_applied_to_two_independent_tenant_databases(tmp_path: Path):
    tenant_a, tenant_b = uuid4(), uuid4()
    url_a, revision_a = _provision(tmp_path / "tenant-a.db", tenant_a)
    url_b, revision_b = _provision(tmp_path / "tenant-b.db", tenant_b)

    assert revision_a == revision_b == "0002_p4_command_execution"
    for url in (url_a, url_b):
        engine = create_engine(url)
        try:
            inspector = inspect(engine)
            assert "platform_command_executions" in inspector.get_table_names()
            columns = {column["name"] for column in inspector.get_columns("platform_command_executions")}
            assert columns == {
                "command_id",
                "command_name",
                "command_schema_version",
                "scope",
                "company_id",
                "actor_user_id",
                "fingerprint",
                "result_code",
                "result_json",
                "committed_at",
            }
            foreign_keys = inspector.get_foreign_keys("platform_command_executions")
            assert any(
                fk["referred_table"] == "companies"
                and fk["constrained_columns"] == ["company_id"]
                for fk in foreign_keys
            )
        finally:
            engine.dispose()
