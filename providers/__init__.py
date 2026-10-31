"""Provider registry. Every module in this package that defines a BaseProvider subclass is a plugin;
none is special, and the registry knows nothing about any of them."""
import importlib
import inspect
import pathlib
import pkgutil
from typing import Dict, List, Optional

from .base import BaseProvider, GenerateOptions, ModelInfo, Reply, SettingDef, ToolCall, ToolDef, clean_values

_REGISTRY: Dict[str, BaseProvider] = {}
_discovered = False


def register_provider(provider: BaseProvider) -> None:
    if not provider.id:
        raise ValueError(f"Provider {provider} has no 'id' set.")
    _REGISTRY[provider.id.lower()] = provider


def unregister_provider(provider_id: str) -> None:
    _REGISTRY.pop(str(provider_id).lower(), None)


def get_provider(provider_id: str) -> Optional[BaseProvider]:
    _auto_discover()
    return _REGISTRY.get(str(provider_id).lower())


def get_all_providers() -> List[BaseProvider]:
    """All providers, ordered by their own `order`, then name."""
    _auto_discover()
    return sorted(_REGISTRY.values(), key=lambda p: (p.order, p.name))


def _auto_discover():
    global _discovered
    if _discovered:
        return
    _discovered = True
    pkg_dir = pathlib.Path(__file__).parent
    for _, module_name, is_pkg in pkgutil.iter_modules([str(pkg_dir)]):
        if is_pkg or module_name == 'base':
            continue
        try:
            mod = importlib.import_module(f'.{module_name}', package=__package__)
        except Exception:
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, BaseProvider) and cls is not BaseProvider and cls.__module__ == mod.__name__:
                try:
                    instance = cls()
                except Exception:
                    continue
                if instance.id and instance.id.lower() not in _REGISTRY:
                    register_provider(instance)


_auto_discover()

__all__ = ['BaseProvider', 'SettingDef', 'ModelInfo', 'GenerateOptions', 'ToolDef', 'ToolCall', 'Reply', 'clean_values',
           'register_provider', 'unregister_provider', 'get_provider', 'get_all_providers']
