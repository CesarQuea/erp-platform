from __future__ import annotations

from typing import Protocol

from app.core.transactions.boundary import TransactionBoundary
from app.platform.tenancy.context import TenantContext


class TenantTransactionBoundaryFactory(Protocol):
    def for_tenant(self, context: TenantContext) -> TransactionBoundary:
        ...
