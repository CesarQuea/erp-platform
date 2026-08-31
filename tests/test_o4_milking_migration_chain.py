from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]


def _scripts() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_tenant_migration_chain_preserves_o4_p5_and_extends_to_p7_without_branching() -> None:
    scripts = _scripts()
    assert scripts.get_current_head() == "0006_p7_sync_foundation"
    o3 = scripts.get_revision("0003_o4_milking_general")
    o4 = scripts.get_revision("0004_o4_milking_lifecycle_hardening")
    p5 = scripts.get_revision("0005_p5_module_activation")
    p7 = scripts.get_revision("0006_p7_sync_foundation")
    assert o3 is not None and o3.down_revision == "0002_p4_command_execution"
    assert o4 is not None and o4.down_revision == "0003_o4_milking_general"
    assert p5 is not None and p5.down_revision == "0004_o4_milking_lifecycle_hardening"
    assert p7 is not None and p7.down_revision == "0005_p5_module_activation"
    assert scripts.get_heads() == ["0006_p7_sync_foundation"]


def test_historical_migration_target_does_not_change_default_head_behavior() -> None:
    from app.infrastructure.database.migrations import TenantMigrationRunner

    pinned = TenantMigrationRunner(repository_root=ROOT, target_revision="0002_p4_command_execution")
    current = TenantMigrationRunner(repository_root=ROOT)
    assert pinned._target_revision == "0002_p4_command_execution"
    assert current._target_revision == "head"
