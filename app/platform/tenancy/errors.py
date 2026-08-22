from __future__ import annotations


class TenancyError(RuntimeError):
    """Base error for tenant-bound platform operations."""


class TenantNotConfiguredError(TenancyError):
    pass


class TenantInactiveError(TenancyError):
    pass


class TenantDatabaseUnavailableError(TenancyError):
    pass


class TenantDatabaseIdentityError(TenancyError):
    pass


class TenantSessionScopeError(TenancyError):
    pass


class TenantRegistryConfigurationError(ValueError):
    pass
