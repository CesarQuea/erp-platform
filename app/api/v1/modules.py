from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from app.api.contracts import CommandResponse, command_response
from app.api.security import current_principal, module_runtime, operational_principal
from app.platform.identity.model import AuthenticatedPrincipal
from app.platform.modules.errors import module_activation_not_available
from app.platform.modules.model import ChangeModuleActivation, CompanyModuleStatus
from app.platform.tenancy.context import TenantContext


router = APIRouter(prefix="/modules", tags=["modules"])
_MODULE_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class ModuleStatusResponse(BaseModel):
    module_id: str
    module_version: str
    description: str | None
    state: str
    version: int
    activation_present: bool
    effective_enabled: bool


class ChangeModuleActivationRequest(BaseModel):
    command_id: UUID
    expected_version: int = Field(ge=0)


def _status_response(status: CompanyModuleStatus) -> ModuleStatusResponse:
    return ModuleStatusResponse(
        module_id=status.definition.module_id,
        module_version=status.definition.module_version,
        description=status.definition.description,
        state=status.state.value,
        version=status.version,
        activation_present=status.activation_present,
        effective_enabled=status.effective_enabled,
    )


@router.get("", response_model=list[ModuleStatusResponse])
def list_modules(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(operational_principal)],
) -> list[ModuleStatusResponse]:
    runtime = module_runtime(request)
    if runtime.availability is None:
        raise module_activation_not_available()
    assert principal.tenant_id is not None
    assert principal.company_id is not None
    statuses = runtime.availability.list_company_modules(
        TenantContext(principal.tenant_id),
        principal.company_id,
    )
    return [_status_response(status) for status in statuses]


def _change_module(
    *,
    request: Request,
    principal: AuthenticatedPrincipal,
    module_id: str,
    payload: ChangeModuleActivationRequest,
    enable: bool,
) -> CommandResponse:
    runtime = module_runtime(request)
    if runtime.activations is None:
        raise module_activation_not_available()
    command = ChangeModuleActivation(
        command_id=payload.command_id,
        module_id=module_id,
        expected_version=payload.expected_version,
    )
    outcome = (
        runtime.activations.enable_module(command, principal=principal)
        if enable
        else runtime.activations.disable_module(command, principal=principal)
    )
    return command_response(outcome)


@router.post("/{module_id}/enable", response_model=CommandResponse)
def enable_module(
    module_id: Annotated[str, Path(pattern=_MODULE_ID_PATTERN)],
    payload: ChangeModuleActivationRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    return _change_module(
        request=request,
        principal=principal,
        module_id=module_id,
        payload=payload,
        enable=True,
    )


@router.post("/{module_id}/disable", response_model=CommandResponse)
def disable_module(
    module_id: Annotated[str, Path(pattern=_MODULE_ID_PATTERN)],
    payload: ChangeModuleActivationRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> CommandResponse:
    return _change_module(
        request=request,
        principal=principal,
        module_id=module_id,
        payload=payload,
        enable=False,
    )
