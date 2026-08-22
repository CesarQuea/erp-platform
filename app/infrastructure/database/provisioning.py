from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import create_engine, inspect, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.migrations import TenantMigrationRunner
from app.infrastructure.database.models import TenantMetadataRecord
from app.infrastructure.database.runtime import normalize_database_url
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.errors import (
    TenantDatabaseIdentityError,
    TenantDatabaseUnavailableError,
    TenantInactiveError,
)
from app.platform.tenancy.registry import TenantRegistry

EngineFactory = Callable[..., Engine]


class TenantProvisioner:
    """Provision or re-validate one tenant database without exposing its DSN to callers."""

    def __init__(
        self,
        registry: TenantRegistry,
        *,
        migration_runner: TenantMigrationRunner | None = None,
        engine_factory: EngineFactory = create_engine,
    ) -> None:
        self._registry = registry
        self._migration_runner = migration_runner or TenantMigrationRunner()
        self._engine_factory = engine_factory

    def provision(self, context: TenantContext) -> str:
        config = self._registry.get(context.tenant_id)
        if not config.is_active:
            raise TenantInactiveError(f"Tenant {context.tenant_id} is inactive")

        engine = self._engine_factory(
            normalize_database_url(config.database_url),
            pool_pre_ping=True,
        )
        try:
            self._validate_existing_identity_if_present(engine, context)
        finally:
            engine.dispose()

        try:
            self._migration_runner.upgrade(config.database_url)
            revision = self._migration_runner.current_revision(config.database_url)
        except Exception:
            raise TenantDatabaseUnavailableError(
                f"Tenant database provisioning failed for {context.tenant_id}"
            ) from None
        if revision is None:
            raise TenantDatabaseUnavailableError(
                f"Tenant database migration state is unavailable for {context.tenant_id}"
            )

        engine = self._engine_factory(
            normalize_database_url(config.database_url),
            pool_pre_ping=True,
        )
        try:
            with engine.begin() as connection:
                statement = select(TenantMetadataRecord.tenant_id).where(
                    TenantMetadataRecord.singleton_key == 1
                )
                rows = connection.execute(statement).scalars().all()
                if not rows:
                    connection.execute(
                        insert(TenantMetadataRecord).values(
                            singleton_key=1,
                            tenant_id=context.tenant_id,
                            schema_version=revision,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                elif len(rows) == 1 and rows[0] == context.tenant_id:
                    connection.execute(
                        update(TenantMetadataRecord)
                        .where(TenantMetadataRecord.singleton_key == 1)
                        .values(schema_version=revision)
                    )
                else:
                    raise TenantDatabaseIdentityError(
                        f"Tenant database identity mismatch for {context.tenant_id}"
                    )
        except TenantDatabaseIdentityError:
            raise
        except SQLAlchemyError:
            raise TenantDatabaseUnavailableError(
                f"Tenant database provisioning failed for {context.tenant_id}"
            ) from None
        finally:
            engine.dispose()
        return revision

    @staticmethod
    def _validate_existing_identity_if_present(
        engine: Engine,
        context: TenantContext,
    ) -> None:
        try:
            inspector = inspect(engine)
            if not inspector.has_table("platform_tenant_metadata"):
                return
            statement = select(TenantMetadataRecord.tenant_id).where(
                TenantMetadataRecord.singleton_key == 1
            )
            with engine.connect() as connection:
                rows = connection.execute(statement).scalars().all()
        except SQLAlchemyError:
            raise TenantDatabaseUnavailableError(
                f"Tenant database is unavailable for {context.tenant_id}"
            ) from None
        if len(rows) != 1 or rows[0] != context.tenant_id:
            raise TenantDatabaseIdentityError(
                f"Tenant database identity mismatch for {context.tenant_id}"
            )
