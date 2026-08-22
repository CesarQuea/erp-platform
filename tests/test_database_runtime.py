from sqlalchemy import create_engine, event

from app.core.config.settings import Settings
from app.infrastructure.database.runtime import (
    DatabaseRuntime,
    normalize_database_url,
)


def test_postgresql_urls_are_normalized_to_psycopg3_driver():
    assert (
        normalize_database_url("postgresql://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )


def test_database_runtime_without_database_url_is_not_ready():
    runtime = DatabaseRuntime(Settings(environment="test"))

    assert runtime.check_ready() is False


def test_database_runtime_readiness_executes_select_only():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_statement(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        statements.append(statement.strip())

    runtime = DatabaseRuntime(
        Settings(environment="test", database_url="sqlite+pysqlite:///:memory:"),
        engine_factory=lambda *args, **kwargs: engine,
    )

    assert runtime.check_ready() is True
    assert statements == ["SELECT 1"]

    runtime.dispose()
