from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


_ALLOWED_ENVIRONMENTS = frozenset({"local", "test", "staging", "production"})
_ALLOWED_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "ERP Platform API"
    environment: str = "local"
    database_url: str | None = field(default=None, repr=False)
    log_level: str = "INFO"

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

        database_url = self.database_url.strip() if self.database_url else None

        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "log_level", log_level)
        object.__setattr__(self, "database_url", database_url or None)

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "ERP Platform API"),
            environment=os.getenv("ERP_ENV", "local"),
            database_url=os.getenv("DATABASE_URL"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
