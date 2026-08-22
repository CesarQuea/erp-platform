from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import jwt

from app.platform.identity.security import AccessTokenClaims


class AccessTokenValidationError(ValueError):
    pass


class Hs256AccessTokenCodec:
    def __init__(self, *, secret: str, issuer: str, audience: str) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT signing secret must contain at least 256 bits")
        if not issuer.strip() or not audience.strip():
            raise ValueError("JWT issuer and audience are required")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def encode(self, claims: AccessTokenClaims) -> str:
        payload: dict[str, object] = {
            "iss": claims.issuer,
            "aud": claims.audience,
            "sub": str(claims.user_id),
            "sid": str(claims.session_id),
            "jti": str(claims.token_id),
            "iat": claims.issued_at,
            "exp": claims.expires_at,
        }
        if claims.tenant_id is not None:
            payload["tenant_id"] = str(claims.tenant_id)
        if claims.company_id is not None:
            payload["company_id"] = str(claims.company_id)
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "sid", "jti"]},
            )
            issued_at = datetime.fromtimestamp(float(payload["iat"]), tz=UTC)
            expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
            return AccessTokenClaims(
                issuer=str(payload["iss"]),
                audience=str(payload["aud"]),
                user_id=UUID(str(payload["sub"])),
                session_id=UUID(str(payload["sid"])),
                token_id=UUID(str(payload["jti"])),
                issued_at=issued_at,
                expires_at=expires_at,
                tenant_id=UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None,
                company_id=UUID(str(payload["company_id"])) if payload.get("company_id") else None,
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AccessTokenValidationError("access token is invalid") from exc
