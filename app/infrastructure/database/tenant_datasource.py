from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Callable
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

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


@dataclass(slots=True)
class SqlAlchemyTenantDataSource:
    tenant_id: UUID
    _engine: Engine = field(repr=False)

    @property
    def engine(self) -> Engine:
        return self._engine


class SqlAlchemyTenantDataSourceResolver:
    """Resolve one validated SQLAlchemy engine per tenant with a bounded LRU cache."""

    def __init__(
        self,
        registry: TenantRegistry,
        *,
        max_cached_engines: int = 32,
        engine_factory: EngineFactory = create_engine,
    ) -> None:
        if max_cached_engines <= 0:
            raise ValueError("max_cached_engines must be greater than zero")
        self._registry = registry
        self._max_cached_engines = max_cached_engines
        self._engine_factory = engine_factory
        self._cache: OrderedDict[UUID, SqlAlchemyTenantDataSource] = OrderedDict()
        self._lock = RLock()

    def resolve(self, context: TenantContext) -> SqlAlchemyTenantDataSource:
        config = self._registry.get(context.tenant_id)
        if not config.is_active:
            raise TenantInactiveError(f"Tenant {context.tenant_id} is inactive")

        with self._lock:
            cached = self._cache.get(context.tenant_id)
            if cached is not None:
                self._cache.move_to_end(context.tenant_id)
                return cached

            engine = self._engine_factory(
                normalize_database_url(config.database_url),
                pool_pre_ping=True,
            )
            try:
                self._validate_identity(engine, context.tenant_id)
            except Exception:
                engine.dispose()
                raise

            datasource = SqlAlchemyTenantDataSource(context.tenant_id, engine)
            self._cache[context.tenant_id] = datasource
            self._evict_if_needed()
            return datasource

    def dispose(self) -> None:
        with self._lock:
            while self._cache:
                _, datasource = self._cache.popitem(last=False)
                datasource.engine.dispose()

    def _evict_if_needed(self) -> None:
        while len(self._cache) > self._max_cached_engines:
            _, datasource = self._cache.popitem(last=False)
            datasource.engine.dispose()

    @staticmethod
    def _validate_identity(engine: Engine, requested_tenant_id: UUID) -> None:
        try:
            statement = select(TenantMetadataRecord.tenant_id).where(
                TenantMetadataRecord.singleton_key == 1
            )
            with engine.connect() as connection:
                rows = connection.execute(statement).scalars().all()
        except SQLAlchemyError:
            raise TenantDatabaseUnavailableError(
                f"Tenant database is unavailable for {requested_tenant_id}"
            ) from None

        if len(rows) != 1 or rows[0] != requested_tenant_id:
            raise TenantDatabaseIdentityError(
                f"Tenant database identity mismatch for {requested_tenant_id}"
            )
