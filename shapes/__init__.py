"""Shape registry. Every .py BaseShape subclass and .json shape macro in this package is a plugin;
none is special, and the registry knows nothing about any of them."""
import importlib
import inspect
import pathlib
import pkgutil
from typing import Callable, Dict, List, Optional

from ._json import JsonShape, load_json_shape
from .base import BaseShape

_REGISTRY: Dict[str, BaseShape] = {}
_discovered = False
_listeners: List[Callable[[], None]] = []


def on_change(fn: Callable[[], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def notify_change() -> None:
    for fn in list(_listeners):
        fn()


def register_shape(shape: BaseShape) -> None:
    if not shape.op:
        raise ValueError(f"Shape {shape} has no 'op' set.")
    _REGISTRY[shape.op] = shape
    notify_change()


def unregister_shape(op: str) -> None:
    _REGISTRY.pop(op, None)
    notify_change()


def get_shape(op: str) -> Optional[BaseShape]:
    _auto_discover()
    return _REGISTRY.get(op)


def get_all_shapes() -> List[BaseShape]:
    """All shapes, ordered by their own `order`, then op."""
    _auto_discover()
    return sorted(_REGISTRY.values(), key=lambda s: (s.order, s.op))


def prompt() -> str:
    """The shapes' notes for the system prompt ('' when there are none)."""
    return '\n'.join(s.prompt.strip('\n') for s in get_all_shapes() if s.prompt and s.prompt.strip())


def _auto_discover():
    global _discovered
    if _discovered:
        return
    _discovered = True
    pkg_dir = pathlib.Path(__file__).parent
    added = False
    for _, module_name, is_pkg in pkgutil.iter_modules([str(pkg_dir)]):
        if is_pkg or module_name == 'base' or module_name.startswith('_'):
            continue
        try:
            mod = importlib.import_module(f'.{module_name}', package=__package__)
        except Exception:
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, BaseShape) and cls is not BaseShape and cls.__module__ == mod.__name__:
                try:
                    instance = cls()
                except Exception:
                    continue
                if instance.op and instance.op not in _REGISTRY:
                    _REGISTRY[instance.op] = instance
                    added = True
    for json_path in sorted(pkg_dir.glob('*.json')):
        if json_path.name.startswith('_'):
            continue
        try:
            instance = load_json_shape(json_path)
        except Exception:
            continue
        if instance.op and instance.op not in _REGISTRY:
            _REGISTRY[instance.op] = instance
            added = True
    if added:
        notify_change()


_auto_discover()
