from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.infrastructure.database.runtime import normalize_database_url


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TenantMigrationRunner:
    def __init__(
        self,
        *,
        repository_root: Path | None = None,
        target_revision: str = "head",
    ) -> None:
        normalized_target = target_revision.strip()
        if not normalized_target:
            raise ValueError("target_revision cannot be blank")
        self._repository_root = repository_root or _REPOSITORY_ROOT
        self._target_revision = normalized_target

    def upgrade(self, database_url: str) -> None:
        config = self._config(database_url)
        command.upgrade(config, self._target_revision)

    def current_revision(self, database_url: str) -> str | None:
        engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                return MigrationContext.configure(connection).get_current_revision()
        finally:
            engine.dispose()

    def _config(self, database_url: str) -> Config:
        config = Config(str(self._repository_root / "alembic.ini"))
        config.set_main_option(
            "script_location",
            str(self._repository_root / "migrations"),
        )
        config.set_main_option("sqlalchemy.url", normalize_database_url(database_url))
        return config
