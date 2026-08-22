class CompanyError(RuntimeError):
    """Base error for Company operations."""


class CompanyConflictError(CompanyError):
    pass


class CompanyNotFoundError(CompanyError):
    pass
