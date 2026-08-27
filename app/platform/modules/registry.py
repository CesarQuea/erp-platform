from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.platform.modules.model import ModuleDefinition


class ModuleRegistryError(ValueError):
    pass


class ModuleRegistryFrozenError(ModuleRegistryError):
    pass


class ModuleNotRegisteredError(ModuleRegistryError):
    pass


class ModuleRegistry:
    def __init__(self, definitions: Iterable[ModuleDefinition] = ()) -> None:
        self._definitions: dict[str, ModuleDefinition] = {}
        self._frozen = False
        for definition in definitions:
            self.register(definition)

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def register(self, definition: ModuleDefinition) -> None:
        if self._frozen:
            raise ModuleRegistryFrozenError("module registry is frozen")
        if not isinstance(definition, ModuleDefinition):
            raise TypeError("definition must be a ModuleDefinition")
        if definition.module_id in self._definitions:
            raise ModuleRegistryError(
                f"duplicate module_id registration: {definition.module_id}"
            )
        self._definitions[definition.module_id] = definition

    def freeze(self) -> None:
        self._frozen = True

    def get(self, module_id: str) -> ModuleDefinition:
        try:
            return self._definitions[module_id]
        except KeyError:
            raise ModuleNotRegisteredError(
                f"module is not registered: {module_id}"
            ) from None

    def contains(self, module_id: str) -> bool:
        return module_id in self._definitions

    def list(self) -> Sequence[ModuleDefinition]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))
