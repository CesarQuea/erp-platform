from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.platform.modules.model import CompanyModuleActivation, ModuleActivationState


class ModuleActivationRepository(Protocol):
    def get(
        self,
        *,
        company_id: UUID,
        module_id: str,
    ) -> CompanyModuleActivation | None: ...

    def list_for_company(self, company_id: UUID) -> Sequence[CompanyModuleActivation]: ...

    def insert(self, activation: CompanyModuleActivation) -> None: ...

    def update_state(
        self,
        *,
        company_id: UUID,
        module_id: str,
        expected_version: int,
        state: ModuleActivationState,
        updated_at: datetime,
        updated_by: UUID,
    ) -> CompanyModuleActivation: ...
