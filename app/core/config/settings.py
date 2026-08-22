from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


_ALLOWED_ENVIRONMENTS = frozenset({"local", "test", "staging", "production"})
_ALLOWED_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid."""


def _read_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer") from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "ERP Platform API"
    environment: str = "local"
    database_url: str | None = field(default=None, repr=False)
    log_level: str = "INFO"
    tenant_databases_json: str | None = field(default=None, repr=False)
    tenant_engine_cache_size: int = 32
    jwt_signing_secret: str | None = field(default=None, repr=False)
    jwt_issuer: str = "erp-platform"
    jwt_audience: str = "erp-first-party"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    def __post_init__(self) -> None:
        environment = self.environment.strip().lower()
        log_level = self.log_level.strip().upper()

        if environment not in _ALLOWED_ENVIRONMENTS:
            raise ConfigurationError(
                f"Unsupported ERP_ENV '{self.environment}'. "
                f"Expected one of: {', '.join(sorted(_ALLOWED_ENVIRONMENTS))}."
            )
        if log_level not in _ALLOWED_LOG_LEVELS:
            raise ConfigurationError(
                f"Unsupported LOG_LEVEL '{self.log_level}'. "
                f"Expected one of: {', '.join(sorted(_ALLOWED_LOG_LEVELS))}."
            )
        if self.tenant_engine_cache_size <= 0:
            raise ConfigurationError("TENANT_ENGINE_CACHE_SIZE must be greater than zero")
        if self.access_token_ttl_minutes <= 0:
            raise ConfigurationError("ACCESS_TOKEN_TTL_MINUTES must be greater than zero")
        if self.refresh_token_ttl_days <= 0:
            raise ConfigurationError("REFRESH_TOKEN_TTL_DAYS must be greater than zero")

        database_url = self.database_url.strip() if self.database_url else None
        tenant_databases_json = (
            self.tenant_databases_json.strip() if self.tenant_databases_json else None
        )
        jwt_signing_secret = (
            self.jwt_signing_secret.strip() if self.jwt_signing_secret else None
        )
        jwt_issuer = self.jwt_issuer.strip()
        jwt_audience = self.jwt_audience.strip()

        if jwt_signing_secret and len(jwt_signing_secret.encode("utf-8")) < 32:
            raise ConfigurationError("JWT_SIGNING_SECRET must contain at least 256 bits")
        if not jwt_issuer:
            raise ConfigurationError("JWT_ISSUER must not be blank")
        if not jwt_audience:
            raise ConfigurationError("JWT_AUDIENCE must not be blank")

        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "log_level", log_level)
        object.__setattr__(self, "database_url", database_url or None)
        object.__setattr__(self, "tenant_databases_json", tenant_databases_json or None)
        object.__setattr__(self, "jwt_signing_secret", jwt_signing_secret or None)
        object.__setattr__(self, "jwt_issuer", jwt_issuer)
        object.__setattr__(self, "jwt_audience", jwt_audience)

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "ERP Platform API"),
            environment=os.getenv("ERP_ENV", "local"),
            database_url=os.getenv("DATABASE_URL"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            tenant_databases_json=os.getenv("TENANT_DATABASES_JSON"),
            tenant_engine_cache_size=_read_positive_int("TENANT_ENGINE_CACHE_SIZE", 32),
            jwt_signing_secret=os.getenv("JWT_SIGNING_SECRET"),
            jwt_issuer=os.getenv("JWT_ISSUER", "erp-platform"),
            jwt_audience=os.getenv("JWT_AUDIENCE", "erp-first-party"),
            access_token_ttl_minutes=_read_positive_int("ACCESS_TOKEN_TTL_MINUTES", 15),
            refresh_token_ttl_days=_read_positive_int("REFRESH_TOKEN_TTL_DAYS", 30),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
