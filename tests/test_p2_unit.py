from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, insert

from app.infrastructure.database.models import TenantMetadataRecord
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.tenant_datasource import SqlAlchemyTenantDataSourceResolver
from app.infrastructure.tenancy.environment_registry import EnvironmentTenantRegistry
from app.platform.company.model import Company
from app.platform.ownership import OwnershipScope
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.errors import TenantDatabaseIdentityError, TenantNotConfiguredError
from app.platform.tenancy.registry import TenantConnectionConfig


def test_tenant_context_requires_uuid():
    tenant_id = uuid4()
    assert TenantContext.from_value(str(tenant_id)).tenant_id == tenant_id
    with pytest.raises(ValueError):
        TenantContext.from_value("not-a-uuid")


def test_environment_registry_hides_database_url_and_fails_closed():
    tenant_id = uuid4()
    url = "postgresql://user:secret@db.example/tenant"
    registry = EnvironmentTenantRegistry.from_json(
        '{"%s":{"database_url":"%s","active":true}}' % (tenant_id, url)
    )
    config = registry.get(tenant_id)
    assert config.database_url == url
    assert "secret" not in repr(config)
    with pytest.raises(TenantNotConfiguredError):
        registry.get(uuid4())


def test_company_validates_human_fields_and_timezone():
    now = datetime.now(timezone.utc)
    company = Company(uuid4(), " ACME ", " Acme S.A. ", True, now, now)
    assert company.code == "ACME"
    assert company.legal_name == "Acme S.A."
    with pytest.raises(ValueError):
        Company(uuid4(), "", "Acme", True, now, now)


def test_ownership_scope_contains_expected_foundation():
    assert {scope.value for scope in OwnershipScope} == {
        "PLATFORM",
        "TENANT",
        "COMPANY",
        "OPERATIONAL",
        "RESOURCE_SPECIFIC",
    }


def _prepared_sqlite_engine(tenant_id: UUID):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TenantMetadataRecord.__table__.create(engine)
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


def test_resolver_validates_physical_tenant_identity_and_cache():
    tenant_id = uuid4()
    engine = _prepared_sqlite_engine(tenant_id)
    registry = EnvironmentTenantRegistry(
        {tenant_id: TenantConnectionConfig(tenant_id, "sqlite://tenant-a")}
    )
    resolver = SqlAlchemyTenantDataSourceResolver(
        registry,
        engine_factory=lambda *args, **kwargs: engine,
    )
    context = TenantContext(tenant_id)
    assert resolver.resolve(context).tenant_id == tenant_id
    assert resolver.resolve(context) is resolver.resolve(context)
    resolver.dispose()


def test_resolver_rejects_metadata_mismatch():
    requested = uuid4()
    actual = uuid4()
    engine = _prepared_sqlite_engine(actual)
    registry = EnvironmentTenantRegistry(
        {requested: TenantConnectionConfig(requested, "sqlite://wrong")}
    )
    resolver = SqlAlchemyTenantDataSourceResolver(
        registry,
        engine_factory=lambda *args, **kwargs: engine,
    )
    with pytest.raises(TenantDatabaseIdentityError):
        resolver.resolve(TenantContext(requested))


def test_session_scope_fails_closed_without_transaction():
    scope = TenantSessionScope()
    with pytest.raises(Exception):
        scope.current()


def test_settings_hide_tenant_registry_secrets():
    from app.core.config.settings import Settings

    settings = Settings(
        environment="test",
        tenant_databases_json=(
            '{"00000000-0000-0000-0000-000000000001":'
            '{"database_url":"postgresql://user:tenant-secret@db/t"}}'
        ),
    )
    assert "tenant-secret" not in repr(settings)
    assert "postgresql://" not in repr(settings)
