"""The sketch entity plugin interface.

An entity plugin owns one sketch entity "type": its JSON schema keys, prompt line, structural
validation, and Fusion sketch drawing. Entity plugins never import each other; they use shared
helpers from features._helpers.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Set

from .. import _helpers as h


@dataclass
class EntityDrawContext:
    """Shared sketch context passed to entity plugins while drawing a sketch."""
    sk: Any
    ex: Callable
    cm: Callable
    pt: Callable
    ent_map: Optional[Dict[str, Any]] = None

    def place(self, points, coords, links=()) -> None:
        h.place_points(self.sk, points, coords, list(links), self.ex, self.cm, self.pt)

    def register(self, entity: Dict[str, Any], value: Any, *, index_curves: bool = False, **named: Any) -> None:
        if self.ent_map is None:
            return
        eid = entity.get('id')
        if not eid:
            return
        self.ent_map[eid] = value
        for k, v in named.items():
            self.ent_map[f'{eid}.{k}'] = v
        if index_curves:
            for idx, c in enumerate(value):
                self.ent_map[f'{eid}.{idx}'] = c


class BaseEntity:
    type = ''                    # unique entity "type" name
    name = ''                    # human-readable name
    order = 100                  # lower order comes first in prompts and schemas
    required: Sequence[str] = ()
    prompt = ''                  # one-line syntax for SKETCH ENTITIES in the system prompt
    schema: Dict[str, Any] = {}  # JSON schema properties contributed by this entity

    def get_schema(self) -> Dict[str, Any]:
        return dict(self.schema)

    def validate(self, entity: Dict[str, Any], where: str, ent_ids: Set[str]) -> None:
        """Raise ValueError (mentioning `where`) when the entity is invalid."""

    def draw(self, sk: Any, entity: Dict[str, Any], ctx: EntityDrawContext) -> None:
        """Draw the entity onto `sk` and constrain its points via `ctx`."""
        raise NotImplementedError
