from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.security import access_token, current_principal, identity_runtime
from app.platform.identity.model import AuthenticatedPrincipal

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    client_label: str | None = Field(default=None, max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class ContextRequest(BaseModel):
    tenant_id: UUID
    company_id: UUID


class TokenPairResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    refresh_token: str
    session_id: UUID
    access_expires_at: datetime
    refresh_expires_at: datetime


class ContextTokenResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    expires_at: datetime


class MeResponse(BaseModel):
    user_id: UUID
    login: str
    display_name: str
    email: str | None
    status: str
    tenant_id: UUID | None
    company_id: UUID | None


class ContextResponse(BaseModel):
    tenant_id: UUID
    company_id: UUID
    company_code: str
    company_name: str


@router.post("/login", response_model=TokenPairResponse)
def login(payload: LoginRequest, request: Request) -> TokenPairResponse:
    pair = identity_runtime(request).authentication.login(
        login=payload.login,
        password=payload.password,
        client_label=payload.client_label,
    )
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        session_id=pair.session_id,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest, request: Request) -> TokenPairResponse:
    pair = identity_runtime(request).authentication.refresh(payload.refresh_token)
    return TokenPairResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        session_id=pair.session_id,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/logout")
def logout(
    request: Request,
    token: Annotated[str, Depends(access_token)],
) -> dict[str, str]:
    identity_runtime(request).authentication.logout(token)
    return {"status": "logged_out"}


@router.get("/me", response_model=MeResponse)
def me(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> MeResponse:
    user = identity_runtime(request).authentication.get_user(principal)
    return MeResponse(
        user_id=user.id,
        login=user.login,
        display_name=user.display_name,
        email=user.email,
        status=user.status.value,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
    )


@router.get("/contexts", response_model=list[ContextResponse])
def contexts(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> list[ContextResponse]:
    return [
        ContextResponse(
            tenant_id=item.tenant_id,
            company_id=item.company_id,
            company_code=item.company_code,
            company_name=item.company_name,
        )
        for item in identity_runtime(request).authentication.list_contexts(principal)
    ]


@router.post("/context", response_model=ContextTokenResponse)
def select_context(
    payload: ContextRequest,
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(current_principal)],
) -> ContextTokenResponse:
    token = identity_runtime(request).authentication.select_context(
        principal,
        tenant_id=payload.tenant_id,
        company_id=payload.company_id,
    )
    return ContextTokenResponse(
        access_token=token.access_token,
        expires_at=token.expires_at,
    )
