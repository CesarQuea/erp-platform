from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.contracts import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    CommandResponse,
    command_response,
)
from app.api.security import current_principal, require_module_enabled
from app.bootstrap.milking_platform import MilkingPlatformRuntime
from app.modules.milking.admin_commands import (
    CreateMilkingConfiguration,
    CreateOutputProfile,
    CreateOutputProfileVersion,
    SetOutputProfileActive,
    UpdateMilkingConfiguration,
)
from app.modules.milking.commands import (
    CancelDraftMilkingSession,
    ConfirmMilkingSession,
    CreateMilkingSession,
    RequestMilkingAnnulment,
    SetMilkingGeneral,
    SetMilkingNotes,
    SetMilkingUseDiscard,
)
from app.modules.milking.configuration import MilkingConfiguration, MilkingOutputProfile
from app.modules.milking.domain import MilkingOutput, MilkingSession, MilkingSessionStatus
from app.modules.milking.errors import milking_unavailable, validation_failed
from app.platform.identity.model import AuthenticatedPrincipal


router = APIRouter(
    prefix="/milking",
    tags=["milking"],
    dependencies=[Depends(require_module_enabled("milking"))],
)


class CommandEnvelope(BaseModel):
    command_id: UUID
    client_occurred_at: datetime
    client_instance_id: str | None = Field(default=None, max_length=128)


class CreateSessionRequest(CommandEnvelope):
    farm_id: UUID
    milking_date: date
    shift_code: str = Field(min_length=1, max_length=64)
    operator_id: UUID | None = None


class SetGeneralRequest(CommandEnvelope):
    expected_version: int = Field(gt=0)
    general_gross_quantity: Decimal = Field(gt=0)
    animals_milked_count: int | None = Field(default=None, ge=0)


class SetUseDiscardRequest(CommandEnvelope):
    expected_version: int = Field(gt=0)
    used_on_farm_quantity: Decimal = Field(ge=0)
    discarded_quantity: Decimal = Field(ge=0)


class SetNotesRequest(CommandEnvelope):
    expected_version: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class VersionedCommandRequest(CommandEnvelope):
    expected_version: int = Field(gt=0)


class ReasonCommandRequest(VersionedCommandRequest):
    reason: str = Field(min_length=1, max_length=2000)


class CreateOutputProfileRequest(CommandEnvelope):
    product_id: UUID
    quantity_uom_id: UUID


class CreateOutputProfileVersionRequest(CommandEnvelope):
    product_id: UUID
    quantity_uom_id: UUID


class SetOutputProfileActiveRequest(VersionedCommandRequest):
    is_active: bool


class CreateConfigurationRequest(CommandEnvelope):
    farm_id: UUID
    shift_code: str = Field(min_length=1, max_length=64)
    output_profile_id: UUID
    output_profile_version: int = Field(gt=0)


class UpdateConfigurationRequest(VersionedCommandRequest):
    output_profile_id: UUID | None = None
    output_profile_version: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class SessionResponse(BaseModel):
    id: UUID
    company_id: UUID
    farm_id: UUID
    milking_date: date
    shift_code: str
    operator_id: UUID | None
    status: str
    animals_milked_count: int | None
    general_gross_quantity: Decimal | None
    quantity_uom_id: UUID
    authoritative_gross_quantity: Decimal | None
    authoritative_total_source: str | None
    used_on_farm_quantity: Decimal | None
    discarded_quantity: Decimal | None
    net_output_quantity: Decimal | None
    reconciliation_status: str
    output_profile_id: UUID
    output_profile_version: int
    product_id: UUID
    notes: str | None
    version: int
    created_at: datetime
    created_by: UUID
    updated_at: datetime | None
    updated_by: UUID | None
    confirmed_at: datetime | None
    confirmed_by: UUID | None
    cancelled_at: datetime | None
    cancelled_by: UUID | None
    cancel_reason: str | None


class OutputResponse(BaseModel):
    id: UUID
    company_id: UUID
    milking_session_id: UUID
    farm_id: UUID
    product_id: UUID
    quantity: Decimal
    uom_id: UUID
    production_date: date
    created_at: datetime
    created_by: UUID


class OutputProfileResponse(BaseModel):
    profile_id: UUID
    profile_version: int
    company_id: UUID
    product_id: UUID
    quantity_uom_id: UUID
    is_active: bool
    version: int
    created_at: datetime
    created_by: UUID


class ConfigurationResponse(BaseModel):
    id: UUID
    company_id: UUID
    farm_id: UUID
    shift_code: str
    output_profile_id: UUID
    output_profile_version: int
    is_active: bool
    version: int
    created_at: datetime
    created_by: UUID
    updated_at: datetime | None
    updated_by: UUID | None


def _milking_runtime(request: Request) -> MilkingPlatformRuntime:
    runtime = getattr(request.app.state, "milking_platform", None)
    if runtime is None:
        raise milking_unavailable()
    return runtime


def _session_response(value: MilkingSession) -> SessionResponse:
    return SessionResponse(
        id=value.id,
        company_id=value.company_id,
        farm_id=value.farm_id,
        milking_date=value.milking_date,
        shift_code=value.shift_code,
        operator_id=value.operator_id,
        status=value.status.value,
        animals_milked_count=value.animals_milked_count,
        general_gross_quantity=value.general_gross_quantity,
        quantity_uom_id=value.quantity_uom_id,
        authoritative_gross_quantity=value.authoritative_gross_quantity,
        authoritative_total_source=(
            value.authoritative_total_source.value
            if value.authoritative_total_source is not None
            else None
        ),
        used_on_farm_quantity=value.used_on_farm_quantity,
        discarded_quantity=value.discarded_quantity,
        net_output_quantity=value.net_output_quantity,
        reconciliation_status=value.reconciliation_status.value,
        output_profile_id=value.output_profile_id,
        output_profile_version=value.output_profile_version,
        product_id=value.product_id,
        notes=value.notes,
        version=value.version,
        created_at=value.created_at,
        created_by=value.created_by,
        updated_at=value.updated_at,
        updated_by=value.updated_by,
        confirmed_at=value.confirmed_at,
        confirmed_by=value.confirmed_by,
        cancelled_at=value.cancelled_at,
        cancelled_by=value.cancelled_by,
        cancel_reason=value.cancel_reason,
    )


def _output_response(value: MilkingOutput) -> OutputResponse:
    return OutputResponse(**{
        "id": value.id,
        "company_id": value.company_id,
        "milking_session_id": value.milking_session_id,
        "farm_id": value.farm_id,
        "product_id": value.product_id,
        "quantity": value.quantity,
        "uom_id": value.uom_id,
        "production_date": value.production_date,
        "created_at": value.created_at,
        "created_by": value.created_by,
    })


def _profile_response(value: MilkingOutputProfile) -> OutputProfileResponse:
    return OutputProfileResponse(
        profile_id=value.profile_id,
        profile_version=value.profile_version,
        company_id=value.company_id,
        product_id=value.product_id,
        quantity_uom_id=value.quantity_uom_id,
        is_active=value.is_active,
        version=value.row_version,
        created_at=value.created_at,
        created_by=value.created_by,
    )


def _configuration_response(value: MilkingConfiguration) -> ConfigurationResponse:
    return ConfigurationResponse(
        id=value.id,
        company_id=value.company_id,
        farm_id=value.farm_id,
        shift_code=value.shift_code,
        output_profile_id=value.output_profile_id,
        output_profile_version=value.output_profile_version,
        is_active=value.is_active,
        version=value.version,
        created_at=value.created_at,
        created_by=value.created_by,
        updated_at=value.updated_at,
        updated_by=value.updated_by,
    )


def _validated(factory, /, **kwargs):
    try:
        return factory(**kwargs)
    except (TypeError, ValueError) as exc:
        raise validation_failed(str(exc)) from None


@router.post("/sessions", response_model=CommandResponse)
def create_session(
    payload: CreateSessionRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        CreateMilkingSession,
        command_id=payload.command_id,
        farm_id=payload.farm_id,
        milking_date=payload.milking_date,
        shift_code=payload.shift_code,
        operator_id=payload.operator_id,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.create_session(command, principal=principal)
    )


@router.patch("/sessions/{session_id}/general", response_model=CommandResponse)
def set_general(
    session_id: UUID,
    payload: SetGeneralRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        SetMilkingGeneral,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        general_gross_quantity=payload.general_gross_quantity,
        animals_milked_count=payload.animals_milked_count,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.set_general(command, principal=principal)
    )


@router.patch("/sessions/{session_id}/notes", response_model=CommandResponse)
def set_notes(
    session_id: UUID,
    payload: SetNotesRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        SetMilkingNotes,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        notes=payload.notes,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.set_notes(command, principal=principal)
    )


@router.patch("/sessions/{session_id}/use-discard", response_model=CommandResponse)
def set_use_discard(
    session_id: UUID,
    payload: SetUseDiscardRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        SetMilkingUseDiscard,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        used_on_farm_quantity=payload.used_on_farm_quantity,
        discarded_quantity=payload.discarded_quantity,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.set_use_discard(command, principal=principal)
    )


@router.post("/sessions/{session_id}/confirm", response_model=CommandResponse)
def confirm_session(
    session_id: UUID,
    payload: VersionedCommandRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        ConfirmMilkingSession,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.confirm(command, principal=principal)
    )


@router.post("/sessions/{session_id}/cancel", response_model=CommandResponse)
def cancel_session(
    session_id: UUID,
    payload: ReasonCommandRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        CancelDraftMilkingSession,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        reason=payload.reason,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.cancel_draft(command, principal=principal)
    )


@router.post("/sessions/{session_id}/annulment-requests", response_model=CommandResponse)
def request_annulment(
    session_id: UUID,
    payload: ReasonCommandRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        RequestMilkingAnnulment,
        command_id=payload.command_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        reason=payload.reason,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).commands.request_annulment(command, principal=principal)
    )


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    farm_id: UUID | None = None,
    status: MilkingSessionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    shift_code: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[SessionResponse]:
    values = _milking_runtime(request).query.list_sessions(
        principal=principal,
        farm_id=farm_id,
        status=status.value if status is not None else None,
        date_from=date_from,
        date_to=date_to,
        shift_code=shift_code,
        limit=limit,
        offset=offset,
    )
    return [_session_response(value) for value in values]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: UUID,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> SessionResponse:
    return _session_response(
        _milking_runtime(request).query.get_session(
            principal=principal,
            session_id=session_id,
        )
    )


@router.get("/outputs", response_model=list[OutputResponse])
def list_outputs(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    farm_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[OutputResponse]:
    values = _milking_runtime(request).query.list_outputs(
        principal=principal,
        farm_id=farm_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [_output_response(value) for value in values]


@router.get("/outputs/{output_id}", response_model=OutputResponse)
def get_output(
    output_id: UUID,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> OutputResponse:
    return _output_response(
        _milking_runtime(request).query.get_output(
            principal=principal,
            output_id=output_id,
        )
    )


@router.get("/output-profiles", response_model=list[OutputProfileResponse])
def list_output_profiles(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    profile_id: UUID | None = None,
    active: bool | None = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[OutputProfileResponse]:
    values = _milking_runtime(request).admin.list_output_profiles(
        principal=principal,
        profile_id=profile_id,
        active=active,
        limit=limit,
        offset=offset,
    )
    return [_profile_response(value) for value in values]


@router.post("/output-profiles", response_model=CommandResponse)
def create_output_profile(
    payload: CreateOutputProfileRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        CreateOutputProfile,
        command_id=payload.command_id,
        product_id=payload.product_id,
        quantity_uom_id=payload.quantity_uom_id,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).admin.create_output_profile(command, principal=principal)
    )


@router.post("/output-profiles/{profile_id}/versions", response_model=CommandResponse)
def create_output_profile_version(
    profile_id: UUID,
    payload: CreateOutputProfileVersionRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        CreateOutputProfileVersion,
        command_id=payload.command_id,
        profile_id=profile_id,
        product_id=payload.product_id,
        quantity_uom_id=payload.quantity_uom_id,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).admin.create_output_profile_version(
            command,
            principal=principal,
        )
    )


@router.patch(
    "/output-profiles/{profile_id}/versions/{profile_version}",
    response_model=CommandResponse,
)
def set_output_profile_active(
    profile_id: UUID,
    profile_version: int,
    payload: SetOutputProfileActiveRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        SetOutputProfileActive,
        command_id=payload.command_id,
        profile_id=profile_id,
        profile_version=profile_version,
        expected_version=payload.expected_version,
        is_active=payload.is_active,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).admin.set_output_profile_active(
            command,
            principal=principal,
        )
    )


@router.get("/configurations", response_model=list[ConfigurationResponse])
def list_configurations(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
    farm_id: UUID | None = None,
    active: bool | None = None,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[ConfigurationResponse]:
    values = _milking_runtime(request).admin.list_configurations(
        principal=principal,
        farm_id=farm_id,
        active=active,
        limit=limit,
        offset=offset,
    )
    return [_configuration_response(value) for value in values]


@router.post("/configurations", response_model=CommandResponse)
def create_configuration(
    payload: CreateConfigurationRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        CreateMilkingConfiguration,
        command_id=payload.command_id,
        farm_id=payload.farm_id,
        shift_code=payload.shift_code,
        output_profile_id=payload.output_profile_id,
        output_profile_version=payload.output_profile_version,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).admin.create_configuration(command, principal=principal)
    )


@router.patch("/configurations/{configuration_id}", response_model=CommandResponse)
def update_configuration(
    configuration_id: UUID,
    payload: UpdateConfigurationRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    command = _validated(
        UpdateMilkingConfiguration,
        command_id=payload.command_id,
        configuration_id=configuration_id,
        expected_version=payload.expected_version,
        output_profile_id=payload.output_profile_id,
        output_profile_version=payload.output_profile_version,
        is_active=payload.is_active,
        client_occurred_at=payload.client_occurred_at,
        client_instance_id=payload.client_instance_id,
    )
    return command_response(
        _milking_runtime(request).admin.update_configuration(command, principal=principal)
    )
