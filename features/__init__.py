"""Feature registry. Every module in this package that defines a BaseFeature subclass
is a plugin; none is special, and the registry knows nothing about any of them."""
import importlib
import inspect
import pathlib
import pkgutil
from typing import Callable, Dict, List, Optional

from .base import AXES, MODES, PLANES, BaseFeature, BuildContext, ValidationContext

_REGISTRY: Dict[str, BaseFeature] = {}
_discovered = False
_listeners: List[Callable[[], None]] = []


def on_change(fn: Callable[[], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def notify_change() -> None:
    for fn in list(_listeners):
        fn()


def register_feature(feature: BaseFeature) -> None:
    if not feature.op:
        raise ValueError(f"Feature {feature} has no 'op' set.")
    _REGISTRY[feature.op] = feature
    notify_change()


def unregister_feature(op: str) -> None:
    _REGISTRY.pop(op, None)
    notify_change()


def get_feature(op: str) -> Optional[BaseFeature]:
    _auto_discover()
    return _REGISTRY.get(op)


def get_all_features() -> List[BaseFeature]:
    """All features, ordered by their own `order`, then op."""
    _auto_discover()
    return sorted(_REGISTRY.values(), key=lambda f: (f.order, f.op))


def prompt() -> str:
    """Numbered operations documentation plus any extra sections (e.g. sub-item syntax)."""
    feats = get_all_features()
    lines = []
    idx = 0
    for feat in feats:
        p = feat.get_prompt()
        if p and p.strip():
            idx += 1
            lines.append(f'{idx}. {p.strip()}')
    out = '\n'.join(lines)
    extras = [feat.extra_prompt().strip('\n') for feat in feats if feat.extra_prompt() and feat.extra_prompt().strip()]
    if extras:
        out = (out + '\n\n' if out else '') + '\n\n'.join(extras)
    return out


def rules_prompt() -> str:
    """Feature-specific CAD best-practice rules for the system prompt."""
    return '\n'.join(f.rules.strip('\n') for f in get_all_features() if f.rules and f.rules.strip())


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
            if issubclass(cls, BaseFeature) and cls is not BaseFeature and cls.__module__ == mod.__name__:
                try:
                    instance = cls()
                except Exception:
                    continue
                if instance.op and instance.op not in _REGISTRY:
                    _REGISTRY[instance.op] = instance
                    added = True
    if added:
        notify_change()


_auto_discover()
