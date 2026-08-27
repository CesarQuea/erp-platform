from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from app.infrastructure.database.models import CompanyRecord
from app.infrastructure.database.module_models import ModuleActivationRecord
from app.infrastructure.database.module_repository import SqlAlchemyModuleActivationRepository
from app.infrastructure.database.session_scope import TenantSessionScope
from app.platform.modules.model import CompanyModuleActivation, ModuleActivationState


def test_update_state_refreshes_preloaded_activation_after_composite_cas() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CompanyRecord.__table__.create(engine)
    ModuleActivationRecord.__table__.create(engine)

    tenant_id = uuid4()
    company_id = uuid4()
    actor_id = uuid4()
    created_at = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    updated_at = created_at + timedelta(minutes=1)

    with engine.begin() as connection:
        connection.execute(
            insert(CompanyRecord).values(
                id=company_id,
                code="REFRESH",
                legal_name="Refresh Test Company",
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    scope = TenantSessionScope()
    repository = SqlAlchemyModuleActivationRepository(scope)

    with Session(engine) as session:
        with session.begin():
            with scope.activate(tenant_id, session):
                repository.insert(
                    CompanyModuleActivation(
                        company_id=company_id,
                        module_id="milking",
                        state=ModuleActivationState.ENABLED,
                        version=1,
                        created_at=created_at,
                        created_by=actor_id,
                    )
                )

        with session.begin():
            with scope.activate(tenant_id, session):
                preloaded = repository.get(company_id=company_id, module_id="milking")
                assert preloaded is not None
                assert preloaded.version == 1
                assert preloaded.state is ModuleActivationState.ENABLED

                changed = repository.update_state(
                    company_id=company_id,
                    module_id="milking",
                    expected_version=1,
                    state=ModuleActivationState.DISABLED,
                    updated_at=updated_at,
                    updated_by=actor_id,
                )

                assert changed.version == 2
                assert changed.state is ModuleActivationState.DISABLED
                assert changed.updated_at == updated_at
                assert changed.updated_by == actor_id

    engine.dispose()
