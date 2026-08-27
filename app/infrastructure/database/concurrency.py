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
        return self.update_versioned_where(
            table,
            identity_values={identity_column: identity_value},
            version_column=version_column,
            expected_version=expected_version,
            values=values,
        )

    def update_versioned_where(
        self,
        table: Table,
        *,
        identity_values: Mapping[Any, object],
        version_column: Any,
        expected_version: int,
        values: Mapping[str, object],
    ) -> int:
        """CAS update supporting single or composite identities.

        The existing single-identity API delegates here so P-4 callers keep the
        exact same behavior while later modules can reuse the same concurrency
        primitive for composite primary keys.
        """
        if not identity_values:
            raise InvalidCommandContextSignal("identity_values cannot be empty")
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
        statement = update(table)
        for identity_column, identity_value in identity_values.items():
            statement = statement.where(identity_column == identity_value)
        statement = (
            statement.where(version_column == expected_version)
            .values(**updates)
            .returning(version_column)
        )
        new_version = session.execute(statement).scalar_one_or_none()
        if new_version is None:
            raise ConcurrencyConflictSignal()
        return int(new_version)
