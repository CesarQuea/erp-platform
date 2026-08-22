from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.core.transactions.boundary import TransactionBoundary
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.platform.tenancy.context import TenantContext

T = TypeVar("T")


class SqlAlchemyTenantTransactionBoundary(TransactionBoundary):
    def __init__(
        self,
        context: TenantContext,
        resolver: SqlAlchemyTenantDataSourceResolver,
        session_scope: TenantSessionScope,
    ) -> None:
        self._context = context
        self._resolver = resolver
        self._session_scope = session_scope

    def run(self, operation: Callable[[], T]) -> T:
        datasource = self._resolver.resolve(self._context)
        factory = sessionmaker(
            bind=datasource.engine,
            class_=Session,
            expire_on_commit=False,
        )
        with factory() as session:
            with session.begin():
                with self._session_scope.activate(self._context.tenant_id, session):
                    return operation()


class SqlAlchemyTenantTransactionBoundaryFactory:
    def __init__(
        self,
        resolver: SqlAlchemyTenantDataSourceResolver,
        session_scope: TenantSessionScope,
    ) -> None:
        self._resolver = resolver
        self._session_scope = session_scope

    def for_tenant(self, context: TenantContext) -> TransactionBoundary:
        return SqlAlchemyTenantTransactionBoundary(
            context,
            self._resolver,
            self._session_scope,
        )
