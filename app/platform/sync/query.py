from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from app.core.errors.models import PlatformError
from app.platform.identity.errors import access_denied
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.service import ModuleAvailabilityService
from app.platform.sync.errors import (
    sync_cursor_invalid,
    sync_protocol_unsupported,
    sync_stream_not_found,
)
from app.platform.sync.model import (
    SYNC_PROTOCOL_VERSION,
    BootstrapPage,
    SyncBatch,
    SyncProjection,
)
from app.platform.sync.provider import SyncProvider
from app.platform.sync.registry import SyncProviderRegistry, SyncStreamNotRegisteredError
from app.platform.sync.repository import SyncJournalRepository
from app.platform.sync.token import BootstrapContinuation, SyncTokenCodec
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.transactions import TenantTransactionBoundaryFactory

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SyncChangesPage:
    batches: tuple[SyncBatch, ...]
    next_cursor: str
    has_more: bool


@dataclass(frozen=True, slots=True)
class SyncBootstrapPage:
    items: tuple[SyncProjection, ...]
    bootstrap_start_cursor: str
    next_page_token: str | None
    has_more: bool


class _SyncQuerySignal(RuntimeError):
    def __init__(self, error: PlatformError) -> None:
        super().__init__(error.code)
        self.error = error


class SyncQueryService:
    def __init__(
        self,
        registry: SyncProviderRegistry,
        repository: SyncJournalRepository,
        transaction_factory: TenantTransactionBoundaryFactory,
        availability: ModuleAvailabilityService,
        token_codec: SyncTokenCodec,
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._transactions = transaction_factory
        self._availability = availability
        self._tokens = token_codec

    def changes(
        self,
        *,
        principal: AuthenticatedPrincipal,
        module_id: str,
        stream_id: str,
        cursor: str | None,
        limit: int,
        sync_protocol_version: str,
    ) -> SyncChangesPage:
        tenant_id, company_id = self._scope(principal)
        self._require_protocol(sync_protocol_version)
        provider = self._prepare_provider(
            principal=principal,
            module_id=module_id,
            stream_id=stream_id,
        )
        del provider  # Pull reads the immutable journal after authorization.

        after_position = (
            0
            if cursor is None
            else self._tokens.decode_cursor(
                cursor,
                tenant_id=tenant_id,
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
            )
        )

        def operation() -> tuple[tuple[SyncBatch, ...], bool]:
            current_position = self._repository.current_position(
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
            )
            if after_position > current_position:
                raise _SyncQuerySignal(sync_cursor_invalid())
            values = self._repository.list_batches(
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
                after_position=after_position,
                limit=limit + 1,
            )
            return values[:limit], len(values) > limit

        batches, has_more = self._run(TenantContext(tenant_id), operation)
        next_position = batches[-1].position if batches else after_position
        next_cursor = self._tokens.encode_cursor(
            tenant_id=tenant_id,
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
            position=next_position,
        )
        return SyncChangesPage(
            batches=batches,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def bootstrap(
        self,
        *,
        principal: AuthenticatedPrincipal,
        module_id: str,
        stream_id: str,
        page_token: str | None,
        limit: int,
        sync_protocol_version: str,
    ) -> SyncBootstrapPage:
        tenant_id, company_id = self._scope(principal)
        self._require_protocol(sync_protocol_version)
        provider = self._prepare_provider(
            principal=principal,
            module_id=module_id,
            stream_id=stream_id,
        )

        continuation: BootstrapContinuation | None = None
        if page_token is not None:
            continuation = self._tokens.decode_bootstrap_continuation(
                page_token,
                tenant_id=tenant_id,
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
            )

        def operation() -> tuple[int, BootstrapPage]:
            current_position = self._repository.current_position(
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
            )
            if continuation is None:
                start_position = current_position
                after_key = None
            else:
                start_position = continuation.start_position
                after_key = continuation.after_key
                if start_position > current_position:
                    raise _SyncQuerySignal(sync_cursor_invalid())

            page = provider.bootstrap_page(
                principal=principal,
                stream_id=stream_id,
                after_key=after_key,
                limit=limit,
            )
            return start_position, page

        start_position, page = self._run(TenantContext(tenant_id), operation)
        start_cursor = self._tokens.encode_cursor(
            tenant_id=tenant_id,
            company_id=company_id,
            module_id=module_id,
            stream_id=stream_id,
            position=start_position,
        )
        next_page_token = None
        if page.has_more:
            assert page.next_key is not None
            next_page_token = self._tokens.encode_bootstrap_continuation(
                tenant_id=tenant_id,
                company_id=company_id,
                module_id=module_id,
                stream_id=stream_id,
                start_position=start_position,
                after_key=page.next_key,
            )
        return SyncBootstrapPage(
            items=page.items,
            bootstrap_start_cursor=start_cursor,
            next_page_token=next_page_token,
            has_more=page.has_more,
        )

    def _prepare_provider(
        self,
        *,
        principal: AuthenticatedPrincipal,
        module_id: str,
        stream_id: str,
    ) -> SyncProvider:
        tenant_id, company_id = self._scope(principal)
        self._availability.require_enabled(
            TenantContext(tenant_id),
            company_id,
            module_id,
        )
        try:
            provider = self._registry.get(module_id, stream_id)
        except SyncStreamNotRegisteredError:
            raise sync_stream_not_found() from None
        provider.authorize(principal=principal, stream_id=stream_id)
        return provider

    @staticmethod
    def _scope(principal: AuthenticatedPrincipal):
        if not principal.has_operational_context:
            raise access_denied()
        assert principal.tenant_id is not None
        assert principal.company_id is not None
        return principal.tenant_id, principal.company_id

    @staticmethod
    def _require_protocol(value: str) -> None:
        if value != SYNC_PROTOCOL_VERSION:
            raise sync_protocol_unsupported()

    def _run(self, context: TenantContext, operation: Callable[[], T]) -> T:
        boundary = self._transactions.for_tenant(context)

        def guarded() -> T:
            try:
                return operation()
            except _SyncQuerySignal:
                raise
            except PlatformError as error:
                # Carry frozen PlatformError through generator-based transaction
                # contexts and re-raise after rollback/scope exit.
                raise _SyncQuerySignal(error) from None

        try:
            return boundary.run(guarded)
        except _SyncQuerySignal as signal:
            raise signal.error from None
