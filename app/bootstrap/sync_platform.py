from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.bootstrap.module_platform import ModulePlatformRuntime
from app.bootstrap.tenant_platform import TenantPlatformRuntime
from app.core.config.settings import Settings
from app.infrastructure.database.session_scope import TenantSessionScope
from app.infrastructure.database.sync_repository import SqlAlchemySyncJournalRepository
from app.infrastructure.database.tenant_transactions import (
    SqlAlchemyTenantTransactionBoundaryFactory,
)
from app.platform.sync.provider import SyncProvider
from app.platform.sync.query import SyncQueryService
from app.platform.sync.registry import SyncProviderRegistry
from app.platform.sync.service import SyncPublisher
from app.platform.sync.token import SyncTokenCodec

DEFAULT_SYNC_BATCH_MAX_BYTES = 256 * 1024
SyncProviderFactory = Callable[[TenantSessionScope], SyncProvider]


@dataclass(slots=True)
class SyncPlatformRuntime:
    registry: SyncProviderRegistry
    query: SyncQueryService

    def dispose(self) -> None:
        # Tenant engines are owned by TenantPlatformRuntime.
        pass


def build_sync_publisher(
    session_scope: TenantSessionScope,
    *,
    max_batch_bytes: int = DEFAULT_SYNC_BATCH_MAX_BYTES,
) -> SyncPublisher:
    """Build a publisher for a bounded context's existing Tenant session scope."""

    return SyncPublisher(
        SqlAlchemySyncJournalRepository(session_scope),
        max_batch_bytes=max_batch_bytes,
    )


def _token_secret(settings: Settings) -> bytes | None:
    if not settings.jwt_signing_secret:
        return None
    # Domain-separate Sync token HMAC from the JWT key while keeping one
    # deployment secret source. This does not couple token formats or semantics.
    return hashlib.sha256(
        b"erp-platform-sync-token-v1\0" + settings.jwt_signing_secret.encode("utf-8")
    ).digest()


def build_sync_platform(
    settings: Settings,
    tenant_platform: TenantPlatformRuntime,
    module_platform: ModulePlatformRuntime,
    *,
    providers: Iterable[SyncProvider] = (),
    provider_factories: Iterable[SyncProviderFactory] = (),
) -> SyncPlatformRuntime | None:
    resolver = getattr(tenant_platform, "resolver", None)
    availability = getattr(module_platform, "availability", None)
    secret = _token_secret(settings)
    if resolver is None or availability is None or secret is None:
        return None

    session_scope = TenantSessionScope()
    resolved_providers = [*providers]
    resolved_providers.extend(factory(session_scope) for factory in provider_factories)
    registry = SyncProviderRegistry(module_platform.registry, resolved_providers)
    registry.freeze()

    transactions = SqlAlchemyTenantTransactionBoundaryFactory(resolver, session_scope)
    repository = SqlAlchemySyncJournalRepository(session_scope)
    return SyncPlatformRuntime(
        registry=registry,
        query=SyncQueryService(
            registry,
            repository,
            transactions,
            availability,
            SyncTokenCodec(secret),
        ),
    )
