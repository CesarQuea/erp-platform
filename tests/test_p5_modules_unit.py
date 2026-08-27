from __future__ import annotations

from uuid import uuid4

import pytest

from app.bootstrap.module_platform import build_module_registry
from app.platform.modules.model import (
    ChangeModuleActivation,
    ModuleActivationState,
    ModuleDefinition,
)
from app.platform.modules.registry import (
    ModuleNotRegisteredError,
    ModuleRegistry,
    ModuleRegistryError,
    ModuleRegistryFrozenError,
)


def definition(module_id: str = "inventory", version: str = "1.0.0") -> ModuleDefinition:
    return ModuleDefinition(
        module_id=module_id,
        module_version=version,
        configuration_namespace=module_id,
    )


def test_module_definition_accepts_semver_and_stable_identifiers():
    item = ModuleDefinition(
        module_id="inventory_core",
        module_version="1.2.3-rc.1+build.7",
        configuration_namespace="inventory.core",
        description="Inventory bounded context",
    )
    assert item.module_id == "inventory_core"
    assert item.module_version == "1.2.3-rc.1+build.7"


@pytest.mark.parametrize(
    "module_id",
    ["", "Milking", "milk-ing", "1inventory", " inventory"],
)
def test_module_definition_rejects_invalid_module_id(module_id: str):
    with pytest.raises(ValueError):
        definition(module_id)


@pytest.mark.parametrize("version", ["1", "1.0", "01.0.0", "1.01.0", "v1.0.0"])
def test_module_definition_rejects_non_semver_versions(version: str):
    with pytest.raises(ValueError):
        definition(version=version)


def test_registry_is_explicit_deterministic_and_frozen_after_bootstrap():
    registry = ModuleRegistry()
    registry.register(definition("sales"))
    registry.register(definition("inventory"))
    assert [item.module_id for item in registry.list()] == ["inventory", "sales"]
    assert registry.contains("inventory")
    assert registry.get("sales").module_version == "1.0.0"

    registry.freeze()
    assert registry.is_frozen
    with pytest.raises(ModuleRegistryFrozenError):
        registry.register(definition("manufacturing"))


def test_registry_rejects_duplicates_and_unknown_modules():
    registry = ModuleRegistry([definition("inventory")])
    with pytest.raises(ModuleRegistryError):
        registry.register(definition("inventory", "2.0.0"))
    with pytest.raises(ModuleNotRegisteredError):
        registry.get("sales")


def test_production_registry_registers_only_current_milking_module_and_is_frozen():
    registry = build_module_registry()
    modules = registry.list()
    assert registry.is_frozen
    assert len(modules) == 1
    assert modules[0].module_id == "milking"
    assert modules[0].module_version == "1.0.0"
    assert modules[0].configuration_namespace == "milking"


def test_activation_command_requires_uuid_valid_module_and_non_negative_version():
    command = ChangeModuleActivation(uuid4(), "milking", 0)
    assert command.expected_version == 0
    with pytest.raises(ValueError):
        ChangeModuleActivation(uuid4(), "Milking", 0)
    with pytest.raises(ValueError):
        ChangeModuleActivation(uuid4(), "milking", -1)


def test_activation_state_is_limited_to_enabled_and_disabled():
    assert {state.value for state in ModuleActivationState} == {"ENABLED", "DISABLED"}
