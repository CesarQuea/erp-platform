from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel

from app.api.contracts import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.api.security import current_principal
from app.bootstrap.sync_platform import SyncPlatformRuntime
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.sync.model import SYNC_PROTOCOL_VERSION, SyncBatch, SyncChange, SyncProjection

router = APIRouter(prefix="/sync", tags=["sync"])
_MODULE_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_STREAM_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class SyncChangeResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    change_kind: str
    schema_version: str
    entity_version: int | None
    payload: dict[str, object] | None


class SyncBatchResponse(BaseModel):
    batch_id: UUID
    position: int
    recorded_at: datetime
    source_command_id: UUID | None
    changes: list[SyncChangeResponse]


class SyncChangesResponse(BaseModel):
    sync_protocol_version: str
    module_id: str
    stream_id: str
    batches: list[SyncBatchResponse]
    next_cursor: str
    has_more: bool


class SyncProjectionResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    schema_version: str
    entity_version: int | None
    payload: dict[str, object]


class SyncBootstrapResponse(BaseModel):
    sync_protocol_version: str
    module_id: str
    stream_id: str
    items: list[SyncProjectionResponse]
    bootstrap_start_cursor: str
    next_page_token: str | None
    has_more: bool


def _runtime(request: Request) -> SyncPlatformRuntime:
    runtime = getattr(request.app.state, "sync_platform", None)
    if runtime is None:
        # With a valid principal this indicates a server bootstrap/configuration
        # defect, not a client-correctable Sync protocol condition.
        raise RuntimeError("Sync platform runtime is unavailable")
    return runtime


def _change_response(value: SyncChange) -> SyncChangeResponse:
    return SyncChangeResponse(
        entity_type=value.entity_type,
        entity_id=value.entity_id,
        change_kind=value.change_kind.value,
        schema_version=value.schema_version,
        entity_version=value.entity_version,
        payload=(dict(value.payload) if value.payload is not None else None),
    )


def _batch_response(value: SyncBatch) -> SyncBatchResponse:
    return SyncBatchResponse(
        batch_id=value.batch_id,
        position=value.position,
        recorded_at=value.recorded_at,
        source_command_id=value.source_command_id,
        changes=[_change_response(change) for change in value.changes],
    )


def _projection_response(value: SyncProjection) -> SyncProjectionResponse:
    return SyncProjectionResponse(
        entity_type=value.entity_type,
        entity_id=value.entity_id,
        schema_version=value.schema_version,
        entity_version=value.entity_version,
        payload=dict(value.payload),
    )


@router.get("/{module_id}/changes", response_model=SyncChangesResponse)
def get_changes(
    module_id: Annotated[str, Path(pattern=_MODULE_ID_PATTERN)],
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    stream_id: Annotated[str, Query(pattern=_STREAM_ID_PATTERN)] = "default",
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    sync_protocol_version: Annotated[str, Query(min_length=1, max_length=32)] = SYNC_PROTOCOL_VERSION,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
) -> SyncChangesResponse:
    page = _runtime(request).query.changes(
        principal=principal,
        module_id=module_id,
        stream_id=stream_id,
        cursor=cursor,
        limit=limit,
        sync_protocol_version=sync_protocol_version,
    )
    return SyncChangesResponse(
        sync_protocol_version=SYNC_PROTOCOL_VERSION,
        module_id=module_id,
        stream_id=stream_id,
        batches=[_batch_response(batch) for batch in page.batches],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{module_id}/bootstrap", response_model=SyncBootstrapResponse)
def get_bootstrap(
    module_id: Annotated[str, Path(pattern=_MODULE_ID_PATTERN)],
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    stream_id: Annotated[str, Query(pattern=_STREAM_ID_PATTERN)] = "default",
    page_token: Annotated[str | None, Query(max_length=4096)] = None,
    sync_protocol_version: Annotated[str, Query(min_length=1, max_length=32)] = SYNC_PROTOCOL_VERSION,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
) -> SyncBootstrapResponse:
    page = _runtime(request).query.bootstrap(
        principal=principal,
        module_id=module_id,
        stream_id=stream_id,
        page_token=page_token,
        limit=limit,
        sync_protocol_version=sync_protocol_version,
    )
    return SyncBootstrapResponse(
        sync_protocol_version=SYNC_PROTOCOL_VERSION,
        module_id=module_id,
        stream_id=stream_id,
        items=[_projection_response(item) for item in page.items],
        bootstrap_start_cursor=page.bootstrap_start_cursor,
        next_page_token=page.next_page_token,
        has_more=page.has_more,
    )
