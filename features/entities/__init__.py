"""Sketch entity registry. Every module in this package that defines a BaseEntity subclass
is a plugin; none is special, and the registry knows nothing about any of them."""
import importlib
import inspect
import pathlib
import pkgutil
from typing import Callable, Dict, List, Optional, Set

from .. import _helpers as h
from .base import BaseEntity, EntityDrawContext

_REGISTRY: Dict[str, BaseEntity] = {}
_discovered = False
_listeners: List[Callable[[], None]] = []


def on_change(fn: Callable[[], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def notify_change() -> None:
    for fn in list(_listeners):
        fn()


def register_entity(entity: BaseEntity) -> None:
    if not entity.type:
        raise ValueError(f"Entity {entity} has no 'type' set.")
    _REGISTRY[entity.type] = entity
    notify_change()


def unregister_entity(entity_type: str) -> None:
    _REGISTRY.pop(entity_type, None)
    notify_change()


def get_entity(entity_type: str) -> Optional[BaseEntity]:
    _auto_discover()
    return _REGISTRY.get(entity_type)


def get_all_entities() -> List[BaseEntity]:
    """All sketch entities, ordered by their own `order`, then type."""
    _auto_discover()
    return sorted(_REGISTRY.values(), key=lambda e: (e.order, e.type))


def schema() -> Dict:
    """JSON schema for a sketch's `entities` array, built from all registered entity plugins."""
    ents = get_all_entities()
    props: Dict = {
        'type': {'enum': [e.type for e in ents]},
        'id': {'type': 'string'},
    }
    for ent in ents:
        for key, spec in ent.get_schema().items():
            props.setdefault(key, spec)
    return {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': props,
            'required': ['type'],
        },
    }


def prompt() -> str:
    """The sketch entities' lines for the system prompt."""
    return '\n'.join(e.prompt.strip('\n') for e in get_all_entities() if e.prompt and e.prompt.strip())


def validate_entity(e: Dict, where: str, ent_ids: Set[str]) -> None:
    h.need(e, where, 'type')
    ent = get_entity(e['type'])
    if not ent:
        known = tuple(x.type for x in get_all_entities())
        raise ValueError(f'{where}: type must be one of {known}')
    h.need(e, where, *ent.required)
    ent.validate(e, where, ent_ids)
    if 'id' in e:
        if not isinstance(e['id'], str) or not e['id']:
            raise ValueError(f'{where}: id must be a non-empty string')
        ent_ids.add(e['id'])


def draw(sk, e, ex, cm, pt, ent_map=None) -> None:
    """Draw one sketch entity onto `sk`; pt(a, b) maps DSL plane coords (cm) -> sketch Point3D."""
    ent = get_entity(e['type'])
    if not ent:
        raise ValueError(f'unknown entity type {e["type"]!r}')
    ent.draw(sk, e, EntityDrawContext(sk, ex, cm, pt, ent_map))


def _auto_discover() -> None:
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
            if issubclass(cls, BaseEntity) and cls is not BaseEntity and cls.__module__ == mod.__name__:
                try:
                    instance = cls()
                except Exception:
                    continue
                if instance.type and instance.type not in _REGISTRY:
                    _REGISTRY[instance.type] = instance
                    added = True
    if added:
        notify_change()


_auto_discover()

__all__ = ['BaseEntity', 'EntityDrawContext', 'on_change', 'notify_change', 'register_entity',
           'unregister_entity', 'get_entity', 'get_all_entities', 'schema', 'prompt',
           'validate_entity', 'draw']
