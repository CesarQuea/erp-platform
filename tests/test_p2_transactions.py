from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, insert

from app.infrastructure.database.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.models import CompanyRecord, TenantMetadataRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.company.errors import CompanyConflictError, CompanyNotFoundError
from app.platform.company.service import CompanyService
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.registry import TenantConnectionConfig


class FixedClock:
    def now(self):
        return datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def _engine_for_file(path: Path, tenant_id: UUID):
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    TenantMetadataRecord.__table__.create(engine)
    CompanyRecord.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(TenantMetadataRecord).values(
                singleton_key=1,
                tenant_id=tenant_id,
                schema_version="test",
                created_at=datetime.now(timezone.utc),
            )
        )
    return engine


def _service_for_tenants(mapping: dict[UUID, tuple[str, object]]):
    registry = EnvironmentTenantRegistry(
        {
            tenant_id: TenantConnectionConfig(tenant_id, url)
            for tenant_id, (url, _) in mapping.items()
        }
    )
    by_url = {url: engine for url, engine in mapping.values()}
    resolver = SqlAlchemyTenantDataSourceResolver(
        registry,
        engine_factory=lambda url, **kwargs: by_url[url],
    )
    scope = TenantSessionScope()
    service = CompanyService(
        SqlAlchemyCompanyRepository(scope),
        SqlAlchemyTenantTransactionBoundaryFactory(resolver, scope),
        clock=FixedClock(),
        id_factory=uuid4,
    )
    return service, resolver


def test_company_service_isolates_two_tenant_databases(tmp_path):
    tenant_a, tenant_b = uuid4(), uuid4()
    engine_a = _engine_for_file(tmp_path / "a.db", tenant_a)
    engine_b = _engine_for_file(tmp_path / "b.db", tenant_b)
    service, resolver = _service_for_tenants(
        {
            tenant_a: ("sqlite://a", engine_a),
            tenant_b: ("sqlite://b", engine_b),
        }
    )

    company_a = service.register_company(
        TenantContext(tenant_a), code="A", legal_name="Company A"
    )
    company_b = service.register_company(
        TenantContext(tenant_b), code="B", legal_name="Company B"
    )

    assert [c.code for c in service.list_companies(TenantContext(tenant_a))] == ["A"]
    assert [c.code for c in service.list_companies(TenantContext(tenant_b))] == ["B"]
    with pytest.raises(CompanyNotFoundError):
        service.get_company(TenantContext(tenant_a), company_b.id)
    assert service.get_company(TenantContext(tenant_b), company_b.id).id == company_b.id
    assert service.get_company(TenantContext(tenant_a), company_a.id).id == company_a.id
    resolver.dispose()


def test_multiple_companies_can_exist_inside_one_tenant(tmp_path):
    tenant_id = uuid4()
    engine = _engine_for_file(tmp_path / "multi-company.db", tenant_id)
    service, resolver = _service_for_tenants(
        {tenant_id: ("sqlite://multi-company", engine)}
    )
    context = TenantContext(tenant_id)
    service.register_company(context, code="A", legal_name="Company A")
    service.register_company(context, code="B", legal_name="Company B")
    assert [company.code for company in service.list_companies(context)] == ["A", "B"]
    with pytest.raises(CompanyNotFoundError):
        service.get_company(context, uuid4())
    resolver.dispose()


def test_unique_company_conflict_rolls_back(tmp_path):
    tenant_id = uuid4()
    engine = _engine_for_file(tmp_path / "tenant.db", tenant_id)
    service, resolver = _service_for_tenants(
        {tenant_id: ("sqlite://tenant", engine)}
    )
    context = TenantContext(tenant_id)
    service.register_company(context, code="DUP", legal_name="First")
    with pytest.raises(CompanyConflictError):
        service.register_company(context, code="DUP", legal_name="Second")
    assert [c.legal_name for c in service.list_companies(context)] == ["First"]
    resolver.dispose()
