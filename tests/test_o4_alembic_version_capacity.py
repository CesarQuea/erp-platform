from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
O4_ALEMBIC_VERSION_CAPACITY = 128
O4_HEAD = "0004_o4_milking_lifecycle_hardening"


def _scripts() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_tenant_revision_ids_fit_o4_alembic_version_capacity() -> None:
    revisions = list(_scripts().walk_revisions())
    assert revisions
    assert max(len(item.revision) for item in revisions) <= O4_ALEMBIC_VERSION_CAPACITY
    # Documents the regression that motivated the O-4 capacity expansion.
    assert len(O4_HEAD) > 32


def test_o4_0003_expands_alembic_version_column_before_long_head() -> None:
    source = (ROOT / "migrations" / "versions" / "0003_o4_milking_general.py").read_text(
        encoding="utf-8"
    )
    assert '"alembic_version"' in source
    assert '"version_num"' in source
    assert "type_=sa.String(length=128)" in source
    assert "existing_type=sa.String(length=32)" in source
