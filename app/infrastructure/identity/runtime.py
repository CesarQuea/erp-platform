from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config.settings import Settings
from app.core.transactions.boundary import TransactionBoundary
from app.infrastructure.database.runtime import normalize_database_url
from app.infrastructure.identity.session_scope import PlatformSessionScope

T = TypeVar("T")
EngineFactory = Callable[..., Engine]


class PlatformIdentityDatabaseNotConfiguredError(RuntimeError):
    pass


class SqlAlchemyPlatformTransactionBoundary(TransactionBoundary):
    def __init__(self, factory: sessionmaker[Session], scope: PlatformSessionScope) -> None:
        self._factory = factory
        self._scope = scope

    def run(self, operation: Callable[[], T]) -> T:
        with self._factory() as session:
            with session.begin():
                with self._scope.activate(session):
                    return operation()


class PlatformIdentityDatabase:
    def __init__(self, settings: Settings, *, scope: PlatformSessionScope | None = None, engine_factory: EngineFactory = create_engine) -> None:
        if not settings.database_url:
            raise PlatformIdentityDatabaseNotConfiguredError("Platform database is not configured")
        self.scope = scope or PlatformSessionScope()
        self.engine = engine_factory(normalize_database_url(settings.database_url), pool_pre_ping=True)
        self._factory = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        self.transaction = SqlAlchemyPlatformTransactionBoundary(self._factory, self.scope)

    def dispose(self) -> None:
        self.engine.dispose()
