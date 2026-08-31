from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]


def _scripts() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_p5_extends_o4_tenant_schema_linearly_and_is_preserved_under_p7():
    scripts = _scripts()
    p5 = scripts.get_revision("0005_p5_module_activation")
    p7 = scripts.get_revision("0006_p7_sync_foundation")
    assert p5 is not None
    assert p5.down_revision == "0004_o4_milking_lifecycle_hardening"
    assert p7 is not None
    assert p7.down_revision == "0005_p5_module_activation"
    assert scripts.get_current_head() == "0006_p7_sync_foundation"
    assert scripts.get_heads() == ["0006_p7_sync_foundation"]
