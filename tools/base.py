"""The tool plugin interface.

A toolkit is a set of related tools the model can call. It describes them, runs them, says in
one line what each call did (for the panel), and may add a note to the system prompt and a text
summary for models that can't call tools. PromptCAD knows nothing about any particular toolkit.

Tools always run on Fusion's main thread, so they may use the Fusion API freely.
"""
from typing import Any, Dict, List, Sequence


class ToolError(Exception):
    """A problem the model should read and recover from (a bad id, a missing argument...)."""


class ToolContext:
    """What a tool works with.

    app:    the Fusion application
    design: the active Fusion design
    state:  this toolkit's own saved data for the document, a JSON-friendly dict it may change.
            PromptCAD keeps it with the document; how and where is not the toolkit's concern.
    """

    def __init__(self, app, design, state=None):
        self.app, self.design = app, design
        self.state = state if state is not None else {}


class BaseToolkit:
    id = ''          # unique, stable: also the key of its saved state
    name = ''        # for people (logs, docs)
    order = 100      # tools from lower orders are listed first
    needs: Sequence[str] = ()  # model capabilities required besides tool calling, e.g. ('images',)
    prompt = ''      # added to the system prompt when these tools are offered

    def tools(self) -> List[Dict[str, Any]]:
        """The tools, as {'name', 'description', 'parameters': JSON schema (object)}."""
        return []

    def run(self, name: str, args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """Run one of this toolkit's tools; return JSON-friendly data. Raise ToolError for problems
        the model should see; any other exception is reported to the model as a failure too."""
        raise ToolError(f'{name} is not implemented.')

    def label(self, name: str, args: Dict[str, Any], result: Dict[str, Any]) -> str:
        """A short line for the panel saying what the call did."""
        err = isinstance(result, dict) and result.get('error')
        return f'Called {name}' + (f' (failed: {err})' if err else '')

    def summary(self, ctx: ToolContext) -> str:
        """A text picture for models that can't call tools ('' when there is nothing to say)."""
        return ''
