from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config.settings import Settings


EngineFactory = Callable[..., Engine]


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


class DatabaseRuntime:
    """P-1 single-database runtime used only for read-only readiness checks."""

    def __init__(
        self,
        settings: Settings,
        *,
        engine_factory: EngineFactory = create_engine,
    ) -> None:
        self._engine: Engine | None = None
        if settings.database_url:
            self._engine = engine_factory(
                normalize_database_url(settings.database_url),
                pool_pre_ping=True,
            )

    def check_ready(self) -> bool:
        if self._engine is None:
            return False

        try:
            with self._engine.connect() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
