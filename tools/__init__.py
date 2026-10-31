"""Tool registry. Every module in this package that defines a BaseToolkit subclass is a plugin;
none is special, and the registry knows nothing about any of them."""
import importlib
import inspect
import pathlib
import pkgutil
from typing import Dict, Iterable, List, Optional

from .base import BaseToolkit, ToolContext, ToolError

_REGISTRY: Dict[str, BaseToolkit] = {}
_discovered = False


def register_toolkit(toolkit: BaseToolkit) -> None:
    if not toolkit.id:
        raise ValueError(f"Toolkit {toolkit} has no 'id' set.")
    _REGISTRY[toolkit.id] = toolkit


def unregister_toolkit(toolkit_id: str) -> None:
    _REGISTRY.pop(toolkit_id, None)


def get_toolkit(toolkit_id: str) -> Optional[BaseToolkit]:
    _auto_discover()
    return _REGISTRY.get(toolkit_id)


def get_all_toolkits() -> List[BaseToolkit]:
    """All toolkits, ordered by their own `order`, then id."""
    _auto_discover()
    return sorted(_REGISTRY.values(), key=lambda t: (t.order, t.id))


def usable(capabilities: Iterable[str]) -> List[BaseToolkit]:
    """Toolkits whose needs the model meets (capabilities: names of what the model can do)."""
    caps = set(capabilities)
    return [t for t in get_all_toolkits() if set(t.needs) <= caps]


def _tools_of(toolkit):
    try:
        return [dict(s) for s in toolkit.tools() if s.get('name')]
    except Exception:
        return []


def specs(toolkits: Iterable[BaseToolkit]) -> List[dict]:
    """The tools of these toolkits. A name already taken by an earlier toolkit is left out."""
    out, seen = [], set()
    for t in toolkits:
        for s in _tools_of(t):
            if s['name'] not in seen:
                seen.add(s['name'])
                out.append(s)
    return out


def owner(name: str, toolkits: Iterable[BaseToolkit]) -> Optional[BaseToolkit]:
    """The toolkit that answers to a tool name (the first one, as in specs())."""
    for t in toolkits:
        if any(s['name'] == name for s in _tools_of(t)):
            return t
    return None


def prompt(toolkits: Iterable[BaseToolkit]) -> str:
    """The toolkits' notes for the system prompt."""
    return '\n'.join(t.prompt.strip('\n') for t in toolkits if t.prompt and t.prompt.strip())


def run(toolkit: BaseToolkit, name: str, args: dict, ctx: ToolContext) -> dict:
    """Run a tool. Problems come back as {'error': ...} for the model to read, never as exceptions."""
    try:
        result = toolkit.run(name, dict(args or {}), ctx)
        return result if isinstance(result, dict) else {'result': result}
    except ToolError as e:
        return {'error': str(e)}
    except Exception as e:  # a Fusion API surprise: tell the model rather than failing the turn
        return {'error': f'{name} failed: {type(e).__name__}: {e}'}


def label(toolkit: BaseToolkit, name: str, args: dict, result: dict) -> str:
    try:
        return str(toolkit.label(name, args or {}, result)) or f'Called {name}'
    except Exception:
        return f'Called {name}'


def summary(toolkit: BaseToolkit, ctx: ToolContext) -> str:
    """The toolkit's text picture ('' if it has none or it fails)."""
    try:
        return (toolkit.summary(ctx) or '').strip()
    except Exception:
        return ''


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
            if issubclass(cls, BaseToolkit) and cls is not BaseToolkit and cls.__module__ == mod.__name__:
                try:
                    instance = cls()
                except Exception:
                    continue
                if instance.id and instance.id not in _REGISTRY:
                    register_toolkit(instance)


_auto_discover()

__all__ = ['BaseToolkit', 'ToolContext', 'ToolError', 'register_toolkit', 'unregister_toolkit', 'get_toolkit',
           'get_all_toolkits', 'usable', 'specs', 'owner', 'prompt', 'run', 'label', 'summary']
