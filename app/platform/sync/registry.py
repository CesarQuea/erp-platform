from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.platform.modules.registry import ModuleRegistry
from app.platform.sync.model import validate_stream_id
from app.platform.sync.provider import SyncProvider


class SyncProviderRegistryError(ValueError):
    pass


class SyncProviderRegistryFrozenError(SyncProviderRegistryError):
    pass


class SyncStreamNotRegisteredError(SyncProviderRegistryError):
    pass


class SyncProviderRegistry:
    """Explicit Sync capability registry layered on top of P-5 ModuleRegistry."""

    def __init__(
        self,
        module_registry: ModuleRegistry,
        providers: Iterable[SyncProvider] = (),
    ) -> None:
        if not isinstance(module_registry, ModuleRegistry):
            raise TypeError("module_registry must be a ModuleRegistry")
        self._module_registry = module_registry
        self._providers: dict[str, SyncProvider] = {}
        self._stream_ids: dict[str, tuple[str, ...]] = {}
        self._frozen = False
        for provider in providers:
            self.register(provider)

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def register(self, provider: SyncProvider) -> None:
        if self._frozen:
            raise SyncProviderRegistryFrozenError("sync provider registry is frozen")
        module_id = getattr(provider, "module_id", None)
        if not isinstance(module_id, str):
            raise TypeError("provider.module_id must be a string")

        # A Sync provider extends a P-5 registered module. It never creates a
        # second independent catalogue of modules.
        self._module_registry.get(module_id)

        raw_stream_ids = getattr(provider, "stream_ids", None)
        if not isinstance(raw_stream_ids, tuple):
            raise TypeError("provider.stream_ids must be a tuple")
        if not raw_stream_ids:
            raise SyncProviderRegistryError("sync provider must declare at least one stream")

        seen: set[str] = set()
        for stream_id in raw_stream_ids:
            validate_stream_id(stream_id)
            if stream_id in seen:
                raise SyncProviderRegistryError(
                    f"duplicate stream_id for module {module_id}: {stream_id}"
                )
            seen.add(stream_id)

        if module_id in self._providers:
            raise SyncProviderRegistryError(
                f"duplicate sync provider registration: {module_id}"
            )

        self._providers[module_id] = provider
        self._stream_ids[module_id] = tuple(raw_stream_ids)

    def freeze(self) -> None:
        self._frozen = True

    def get(self, module_id: str, stream_id: str) -> SyncProvider:
        # Preserve the P-5 distinction between an unknown module and a known
        # module that does not expose the requested Sync stream.
        self._module_registry.get(module_id)
        validate_stream_id(stream_id)
        provider = self._providers.get(module_id)
        if provider is None or stream_id not in self._stream_ids[module_id]:
            raise SyncStreamNotRegisteredError(
                f"sync stream is not registered: {module_id}/{stream_id}"
            )
        return provider

    def list_streams(self, module_id: str) -> Sequence[str]:
        self._module_registry.get(module_id)
        return self._stream_ids.get(module_id, ())
