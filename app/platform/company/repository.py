from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.platform.company.model import Company


class CompanyRepository(Protocol):
    def add(self, company: Company) -> None:
        ...

    def get_by_id(self, company_id: UUID) -> Company | None:
        ...

    def list_all(self) -> Sequence[Company]:
        ...
