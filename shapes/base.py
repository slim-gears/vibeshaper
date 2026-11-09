"""The shape plugin interface.

A shape is a ready-made part the model can ask for in one timeline step, such as a gear.
It adds its own step type ("op") and turns that step into ordinary DSL: extra parameters plus
plain steps (sketches, extrudes, patterns...). VibeShaper validates and builds those like any
other design, so a shape never calls Fusion itself and can be tested without it.
"""
from typing import Any, Dict, List, Tuple


class BaseShape:
    op = ''          # the step type this shape adds; unique
    name = ''        # for people (logs, docs)
    order = 100      # shapes from lower orders are listed first in the system prompt
    prompt = ''      # how to use it, for the system prompt (keys, defaults, an example)
    schema: Dict[str, Any] = {}  # JSON schema properties of the step's own keys

    def validate(self, step: Dict[str, Any], where: str) -> None:
        """Raise ValueError (mentioning `where`) when the step can't be expanded."""

    def expand(self, step: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Return (parameters, steps) that build the shape.

        Name new parameters and step ids after the step's own "id", so two shapes never clash.
        The step that finishes the part should carry the step's "id", so later steps
        (fillets, edge selectors, combines) can refer to the shape by that id.
        """
        raise NotImplementedError
