from enum import Enum


class OwnershipScope(str, Enum):
    PLATFORM = "PLATFORM"
    TENANT = "TENANT"
    COMPANY = "COMPANY"
    OPERATIONAL = "OPERATIONAL"
    RESOURCE_SPECIFIC = "RESOURCE_SPECIFIC"
