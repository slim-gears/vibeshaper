"""The timeline feature plugin interface.

A feature plugin owns one timeline step type ("op"): its JSON schema properties, prompt docs,
structural validation, and Fusion 360 execution. Feature plugins never import each other; they
communicate indirectly through the shared ValidationContext and BuildContext.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set

PLANES = ('xy', 'xz', 'yz')
AXES = ('x', 'y', 'z')
MODES = ('new_body', 'join', 'cut', 'intersect')

JS_LEN = {'type': ['string', 'number']}
JS_POINT = {'type': 'array', 'items': JS_LEN, 'minItems': 2, 'maxItems': 2}
JS_CENTER = {'type': 'array', 'items': JS_LEN, 'minItems': 2, 'maxItems': 3}
JS_AXIS = {'enum': list(AXES)}
JS_PLANE = {'enum': list(PLANES)}
JS_MODE = {'enum': list(MODES)}


@dataclass
class ValidationContext:
    """State accumulated while validating one timeline."""
    params: Dict[str, Any] = field(default_factory=dict)
    sketches: Set[str] = field(default_factory=set)
    features: Set[str] = field(default_factory=set)


@dataclass
class BuildContext:
    """Shared state and unit/expression helpers for executing one timeline in Fusion."""
    root: Any
    index: int
    params: Dict[str, Any]
    um: Any
    sketches: Dict[str, Any]
    features: Dict[str, Any]
    last_feature: Any
    base_planes: Dict[str, Any]
    axes_map: Dict[str, Any]
    ops: Dict[str, Any]
    world: Dict[str, Callable]
    ex: Callable
    cm: Callable
    angle_ex: Callable
    eval_count: Callable

    def add_feature(self, step: Dict[str, Any], feat: Any, default_id: Optional[str] = None) -> None:
        fid = step.get('id', default_id or f'_{step["op"]}_{self.index}')
        self.features[fid] = feat
        self.last_feature = feat


class BaseFeature:
    op = ''                      # unique timeline step "op" name
    name = ''                    # human-readable name (logs, docs)
    order = 100                  # lower order comes first in prompts and schemas
    target_key: Optional[str] = 'feature'  # fallback key for progress labels when "id" is omitted
    prompt = ''                  # syntax & usage line for the system prompt
    rules = ''                   # optional lines for RULES & BEST PRACTICES
    schema: Dict[str, Any] = {}  # JSON schema properties contributed by this op

    def get_schema(self) -> Dict[str, Any]:
        return dict(self.schema)

    def get_prompt(self) -> str:
        return self.prompt

    def extra_prompt(self) -> str:
        return ''

    def label(self, step: Dict[str, Any]) -> str:
        what = step.get('id') or (step.get(self.target_key) if self.target_key else '') or ''
        return f'{self.op} {what}'.strip() if what else self.op

    def validate(self, step: Dict[str, Any], where: str, ctx: ValidationContext) -> None:
        """Raise ValueError (mentioning `where`) when the step is invalid."""

    def execute(self, step: Dict[str, Any], ctx: BuildContext) -> None:
        """Build the feature in Fusion using `ctx`."""
        raise NotImplementedError

    def pattern_copies(self, step: Dict[str, Any], fid: str, ev: Callable[[Any], float]) -> int:
        """How many copies this step makes of feature `fid` for BOM counting (1 when none)."""
        return 1
