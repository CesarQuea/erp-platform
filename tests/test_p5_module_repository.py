from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.infrastructure.database.models import CompanyRecord
from app.infrastructure.database.module_models import ModuleActivationRecord
from app.infrastructure.database.module_repository import SqlAlchemyModuleActivationRepository
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.commands.errors import ConcurrencyConflictSignal
from app.platform.modules.model import CompanyModuleActivation, ModuleActivationState


def _company(engine, company_id, code: str):
    now = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(CompanyRecord).values(
                id=company_id,
                code=code,
                legal_name=f"Company {code}",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )


def _activation(company_id, actor_id, *, module_id="milking", version=1):
    return CompanyModuleActivation(
        company_id=company_id,
        module_id=module_id,
        state=ModuleActivationState.ENABLED,
        version=version,
        created_at=datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
        created_by=actor_id,
    )


def _runtime():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CompanyRecord.__table__.create(engine)
    ModuleActivationRecord.__table__.create(engine)
    return engine, TenantSessionScope()


def test_repository_insert_get_list_and_company_isolation():
    engine, scope = _runtime()
    tenant_id = uuid4()
    company_a, company_b, actor = uuid4(), uuid4(), uuid4()
    _company(engine, company_a, "A")
    _company(engine, company_b, "B")
    repository = SqlAlchemyModuleActivationRepository(scope)

    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                repository.insert(_activation(company_a, actor))
                repository.insert(_activation(company_b, actor))
        with session.begin():
            with scope.activate(tenant_id, session):
                found = repository.get(company_id=company_a, module_id="milking")
                assert found is not None
                assert found.company_id == company_a
                assert found.version == 1
                assert [item.company_id for item in repository.list_for_company(company_a)] == [
                    company_a
                ]
    engine.dispose()


def test_repository_duplicate_first_activation_is_concurrency_conflict():
    engine, scope = _runtime()
    tenant_id, company_id, actor = uuid4(), uuid4(), uuid4()
    _company(engine, company_id, "A")
    repository = SqlAlchemyModuleActivationRepository(scope)
    activation = _activation(company_id, actor)

    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                repository.insert(activation)
        with pytest.raises(ConcurrencyConflictSignal):
            with session.begin():
                with scope.activate(tenant_id, session):
                    repository.insert(activation)
    engine.dispose()


def test_repository_composite_cas_updates_once_and_rejects_stale_writer():
    engine, scope = _runtime()
    tenant_id, company_id, actor = uuid4(), uuid4(), uuid4()
    _company(engine, company_id, "A")
    repository = SqlAlchemyModuleActivationRepository(scope)
    activation = _activation(company_id, actor)
    updated_at = activation.created_at + timedelta(minutes=1)

    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                repository.insert(activation)
        with session.begin():
            with scope.activate(tenant_id, session):
                updated = repository.update_state(
                    company_id=company_id,
                    module_id="milking",
                    expected_version=1,
                    state=ModuleActivationState.DISABLED,
                    updated_at=updated_at,
                    updated_by=actor,
                )
                assert updated.state is ModuleActivationState.DISABLED
                assert updated.version == 2
                assert updated.updated_at == updated_at
        with pytest.raises(ConcurrencyConflictSignal):
            with session.begin():
                with scope.activate(tenant_id, session):
                    repository.update_state(
                        company_id=company_id,
                        module_id="milking",
                        expected_version=1,
                        state=ModuleActivationState.ENABLED,
                        updated_at=updated_at,
                        updated_by=actor,
                    )
    engine.dispose()


@pytest.mark.parametrize(
    "overrides",
    [
        {"module_id": ""},
        {"state": "UNKNOWN"},
        {"version": 0},
    ],
)
def test_database_constraints_reject_invalid_activation_rows(overrides):
    engine, _ = _runtime()
    company_id, actor = uuid4(), uuid4()
    _company(engine, company_id, "A")
    values = {
        "company_id": company_id,
        "module_id": "milking",
        "state": "ENABLED",
        "version": 1,
        "created_at": datetime.now(timezone.utc),
        "created_by": actor,
        "updated_at": None,
        "updated_by": None,
    }
    values.update(overrides)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(ModuleActivationRecord).values(**values))
    engine.dispose()
