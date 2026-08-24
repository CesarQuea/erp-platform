import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.infrastructure.identity.migrations import PlatformMigrationRunner


def test_platform_identity_migration_is_separate_and_reproducible(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'platform.db'}"
    runner = PlatformMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    runner.upgrade(url)
    assert runner.current_revision(url) == "0001_p3_identity_access"
    runner.upgrade(url)
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version", "auth_sessions", "membership_company_access", "password_credentials", "permissions", "principal_role_assignments", "refresh_tokens", "role_permissions", "roles", "tenant_memberships", "user_accounts"}
    finally:
        engine.dispose()


def test_platform_migration_preserves_existing_application_loggers(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'platform-logging.db'}"
    runner = PlatformMigrationRunner(repository_root=Path(__file__).resolve().parents[1])
    service_logger = logging.getLogger("app.platform.identity.service")
    previous_disabled = service_logger.disabled
    service_logger.disabled = False
    try:
        runner.upgrade(url)
        assert service_logger.disabled is False
    finally:
        service_logger.disabled = previous_disabled
