from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infrastructure.database.command_models import CommandExecutionRecordModel
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.model import CommandExecutionRecord, CommandScope


class SqlAlchemyCommandExecutionRepository:
    def __init__(self, session_scope: TenantSessionScope) -> None:
        self._session_scope = session_scope

    def claim(self, record: CommandExecutionRecord) -> bool:
        session = self._session_scope.current()
        values = {
            "command_id": record.command_id,
            "command_name": record.command_name,
            "command_schema_version": record.command_schema_version,
            "scope": record.scope.value,
            "company_id": record.company_id,
            "actor_user_id": record.actor_user_id,
            "fingerprint": record.fingerprint,
            "result_code": None,
            "result_json": None,
            "committed_at": None,
        }
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(CommandExecutionRecordModel).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[CommandExecutionRecordModel.command_id]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(CommandExecutionRecordModel).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=[CommandExecutionRecordModel.command_id]
            )
        else:
            raise RuntimeError(
                f"P-4 command idempotency does not support database dialect {dialect!r}"
            )
        statement = statement.returning(CommandExecutionRecordModel.command_id)
        claimed_id = session.execute(statement).scalar_one_or_none()
        return claimed_id is not None

    def get(self, command_id: UUID) -> CommandExecutionRecord | None:
        session = self._session_scope.current()
        row = session.get(CommandExecutionRecordModel, command_id)
        if row is None:
            return None
        return CommandExecutionRecord(
            command_id=row.command_id,
            command_name=row.command_name,
            command_schema_version=row.command_schema_version,
            scope=CommandScope(row.scope),
            company_id=row.company_id,
            actor_user_id=row.actor_user_id,
            fingerprint=row.fingerprint,
            result_code=row.result_code,
            result_json=row.result_json,
            committed_at=row.committed_at,
        )

    def complete(
        self,
        command_id: UUID,
        *,
        result_code: str,
        result_json: Mapping[str, object],
        committed_at: datetime,
    ) -> None:
        session = self._session_scope.current()
        result = session.execute(
            update(CommandExecutionRecordModel)
            .where(CommandExecutionRecordModel.command_id == command_id)
            .values(
                result_code=result_code,
                result_json=dict(result_json),
                committed_at=committed_at,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("command execution claim disappeared before completion")
