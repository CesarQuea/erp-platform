from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.errors.models import PlatformError
from app.platform.company.model import Company
from app.platform.modules.model import ModuleDefinition
from app.platform.modules.registry import ModuleRegistry
from app.platform.modules.service import ModuleAvailabilityService
from app.platform.tenancy.context import TenantContext


class MemoryActivationRepository:
    def get(self, *, company_id: UUID, module_id: str):
        return None

    def list_for_company(self, company_id: UUID):
        return ()


class MemoryCompanyRepository:
    def __init__(self, company: Company) -> None:
        self._company = company

    def get_by_id(self, company_id: UUID):
        return self._company if company_id == self._company.id else None


class GeneratorContextBoundary:
    @contextmanager
    def _scope(self):
        yield

    def run(self, operation):
        with self._scope():
            return operation()


class BoundaryFactory:
    def for_tenant(self, context: TenantContext):
        return GeneratorContextBoundary()


def _company(*, active: bool) -> Company:
    now = datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc)
    return Company(
        id=uuid4(),
        code="P6-CM",
        legal_name="P-6 Context Manager Company",
        is_active=active,
        created_at=now,
        updated_at=now,
    )


def _service(company: Company) -> ModuleAvailabilityService:
    registry = ModuleRegistry(
        [ModuleDefinition("milking", "1.0.0", "milking", "Milking")]
    )
    registry.freeze()
    return ModuleAvailabilityService(
        registry,
        MemoryActivationRepository(),
        MemoryCompanyRepository(company),
        BoundaryFactory(),
    )


def test_module_not_enabled_survives_generator_contextmanager_boundary():
    company = _company(active=True)
    service = _service(company)

    with pytest.raises(PlatformError) as exc:
        service.require_enabled(TenantContext(uuid4()), company.id, "milking")

    assert exc.value.code == "MODULE_NOT_ENABLED"
    assert exc.value.status_code == 409


def test_module_activation_not_available_survives_generator_contextmanager_boundary():
    company = _company(active=False)
    service = _service(company)

    with pytest.raises(PlatformError) as exc:
        service.list_company_modules(TenantContext(uuid4()), company.id)

    assert exc.value.code == "MODULE_ACTIVATION_NOT_AVAILABLE"
    assert exc.value.status_code == 409
