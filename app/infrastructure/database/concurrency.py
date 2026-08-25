from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import update
from sqlalchemy.sql.schema import Table

from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.errors import (
    ConcurrencyConflictSignal,
    InvalidCommandContextSignal,
)


class SqlAlchemyCompareAndSet:
    """SQLAlchemy optimistic concurrency helper for module repositories."""

    def __init__(self, session_scope: TenantSessionScope) -> None:
        self._session_scope = session_scope

    def update_versioned(
        self,
        table: Table,
        *,
        identity_column: Any,
        identity_value: object,
        version_column: Any,
        expected_version: int,
        values: Mapping[str, object],
    ) -> int:
        if not isinstance(expected_version, int) or isinstance(expected_version, bool):
            raise InvalidCommandContextSignal("expected_version must be an integer")
        if expected_version < 0:
            raise InvalidCommandContextSignal("expected_version cannot be negative")
        if version_column.key in values:
            raise InvalidCommandContextSignal(
                "version is managed by the compare-and-set primitive"
            )

        session = self._session_scope.current()
        updates = dict(values)
        updates[version_column.key] = version_column + 1
        statement = (
            update(table)
            .where(identity_column == identity_value)
            .where(version_column == expected_version)
            .values(**updates)
            .returning(version_column)
        )
        new_version = session.execute(statement).scalar_one_or_none()
        if new_version is None:
            raise ConcurrencyConflictSignal()
        return int(new_version)
