"""The provider plugin interface.

A provider describes its own settings (fields), lists its models with what each can do, and
generates text. It only ever sees its own values as a plain dict: where and how they are
stored is VibeShaper's business, not the provider's.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

FIELD_TYPES = ('string', 'secret', 'boolean', 'number', 'select')


@dataclass
class SettingDef:
    """One field on the provider's Settings page."""
    key: str
    label: str
    type: str = 'string'             # one of FIELD_TYPES
    default: Any = ''
    tooltip: str = ''
    required: bool = False           # must be filled in before the provider can be used
    refreshes_models: bool = False   # the model list depends on this value
    options: Sequence[Tuple[str, str]] = ()  # 'select': (value, label) pairs
    minimum: Optional[float] = None  # 'number' bounds
    maximum: Optional[float] = None

    def to_view(self) -> Dict[str, Any]:
        v = {'key': self.key, 'label': self.label, 'type': self.type, 'tooltip': self.tooltip,
             'required': self.required, 'refreshes_models': self.refreshes_models}
        if self.type == 'select':
            v['options'] = [{'value': val, 'label': lab} for val, lab in self.options]
        if self.type == 'number':
            v['minimum'], v['maximum'] = self.minimum, self.maximum
        return v


@dataclass
class ModelInfo:
    """A model and what it can do."""
    id: str
    label: str = ''
    images: bool = False    # accepts images in messages
    thinking: bool = False  # can reason before answering, and it can be switched on/off
    tools: bool = False     # supports tool / function calling

    def to_view(self) -> Dict[str, Any]:
        return {'id': self.id, 'label': self.label or self.id, 'images': self.images,
                'thinking': self.thinking, 'tools': self.tools}


@dataclass
class ToolDef:
    """A function the model may call. `parameters` is a JSON schema (object)."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=lambda: {'type': 'object', 'properties': {}})


@dataclass
class ToolCall:
    """A call the model made. `extra` is for the provider's own data that must be sent back with
    the call in later requests (e.g. signatures); VibeShaper stores it and never reads it."""
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> Dict[str, Any]:
        return {'id': self.id, 'name': self.name, 'arguments': self.arguments, 'extra': self.extra}


@dataclass
class Reply:
    """What generate() returns when the model may call tools: its text, and the calls it made."""
    text: str = ''
    tool_calls: List[ToolCall] = field(default_factory=list)


@dataclass
class GenerateOptions:
    """Choices VibeShaper makes for a request. Providers ignore what they can't do."""
    think: bool = False
    response_schema: Optional[Dict[str, Any]] = None  # JSON schema the reply must follow, if supported
    tools: Optional[List[ToolDef]] = None  # functions the model may call (only for models listed with tools=True)


# Messages are provider-neutral dicts; each provider converts them to its API's format:
#   {'role': 'system' | 'user' | 'assistant', 'content': str}
#   {'role': 'assistant', 'content': str, 'tool_calls': [ToolCall.to_message(), ...]}
#   {'role': 'tool', 'tool_call_id': str, 'name': str, 'content': str (JSON)}


def clean_values(schema: List[SettingDef], values: Dict[str, Any]) -> Dict[str, Any]:
    """The provider's declared fields only, each coerced to its type; anything invalid falls back to the default."""
    out = {}
    for f in schema:
        v = values.get(f.key, f.default) if isinstance(values, dict) else f.default
        out[f.key] = _coerce(f, v)
    return out


def _coerce(f: SettingDef, v: Any) -> Any:
    if f.type == 'boolean':
        return bool(v)
    if f.type == 'number':
        try:
            n = float(v)
        except (TypeError, ValueError):
            return f.default
        if f.minimum is not None:
            n = max(f.minimum, n)
        if f.maximum is not None:
            n = min(f.maximum, n)
        return int(n) if n == int(n) and isinstance(f.default, int) else n
    if f.type == 'select':
        return v if v in {val for val, _ in f.options} else f.default
    return '' if v is None else str(v).strip()


class BaseProvider:
    id: str = ''
    name: str = ''
    short_name: str = ''  # shown on the model chip; defaults to `name`
    order: int = 100      # position in lists (lower first), then by name

    def __init__(self):
        if not self.short_name:
            self.short_name = self.name

    def get_settings_schema(self) -> List[SettingDef]:
        """The fields this provider needs."""
        return []

    def is_configured(self, values: Dict[str, Any]) -> bool:
        """Whether the provider can be used with these values. By default: every required field is filled in."""
        return all(str(values.get(f.key) if values.get(f.key) is not None else '').strip()
                   for f in self.get_settings_schema() if f.required)

    def list_models(self, values: Dict[str, Any], timeout: float = 5.0) -> List[ModelInfo]:
        """The models available with these values. Raise with a readable message if it can't connect."""
        return []

    def generate(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        values: Dict[str, Any],
        options: Optional[GenerateOptions] = None,
        on_chunk: Optional[Callable[[str, str], None]] = None,
        stop_event: Optional[Any] = None,
        on_open: Optional[Callable[[Any], None]] = None,
        log: Callable[[str], None] = print,
    ) -> 'str | Reply':
        """Stream a reply to `messages`. Return its full text, or a Reply when the model called tools.

        on_chunk(kind, text) with kind 'thought' or 'text'; stop when stop_event is set
        (raise InterruptedError); on_open(response) lets VibeShaper close the stream early.
        With options.tools, offer them to the model; VibeShaper runs the calls and asks again."""
        raise NotImplementedError
