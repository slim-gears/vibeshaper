"""VibeShaper LLM orchestration: prompt -> validated DSL dict.
Generation goes through whichever provider plugin (providers/) the caller names; nothing here
knows any particular provider.
"""
import datetime
import json
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional

try:
    from . import dsl, providers, userdata
except ImportError:  # run as a plain script
    import dsl, providers, userdata

LOG_FILE = userdata.path('vibeshaper.log')
LAST_RESPONSE_FILE = userdata.path('last_response.txt')

SYSTEM = """You are a CAD engineer. Convert the user's request into a parametric design written in this JSON DSL.
Output ONLY the JSON object.

FORMAT
{"parameters": {name: expression, ...}, "timeline": [step, ...]}

PARAMETERS
- snake_case names; values like "60 mm" or expressions over earlier parameters ("width - 2 * wall").
- Put every meaningful dimension in a parameter and reference it everywhere (sketches, offsets, distances),
  so the user can edit the design later. Lengths are mm. Expressions may use + - * / and parentheses.
- Prefix parameter names with the part or component name where helpful (e.g. "elbow_od", "flange_dia", "boss_len")
  rather than generic names ("dia", "length"), so multiple parts can coexist cleanly in one document.

COORDINATES (world, Z is up)
- plane "xy": the ground. Sketch point [a, b] = world (X=a, Y=b). Positive extrude distance goes up (+Z).
- plane "xz": front. Sketch point [a, b] = world (X=a, Z=b). Positive extrude distance goes toward +Y.
- plane "yz": side.  Sketch point [a, b] = world (Y=a, Z=b). Positive extrude distance goes toward +X.
- "offset" moves the sketch plane along its normal: plane "xy" with offset "h" sketches at Z = h.

OPERATIONS (Each timeline step must contain ONLY its required keys!):
1. Sketch:
   {"op": "sketch", "id": unique_name, "plane": "xy"|"xz"|"yz", "offset": length (optional), "entities": [entity, ...], "constraints": [{"type": "perpendicular"|"parallel"|"concentric"|"tangent"|"equal", "entities": [id1, id2]}, ...] (optional)}
2. Extrude:
   {"op": "extrude", "id": optional_name, "sketch": sketch_id, "distance": length, "mode": "new_body"|"join"|"cut"|"intersect"}
3. Revolve:
   {"op": "revolve", "id": optional_name, "sketch": sketch_id, "axis": "x"|"y"|"z", "angle": "360 deg" (optional), "mode": "new_body"|"join"|"cut"}
4. Fillet (ONLY uses radius and edges! NEVER put thickness or remove_faces here!):
   {"op": "fillet", "radius": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"}
5. Chamfer (ONLY uses distance and edges!):
   {"op": "chamfer", "distance": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"}
6. Shell (ONLY uses thickness and remove_faces! NEVER put radius or edges here!):
   {"op": "shell", "thickness": length, "remove_faces": "top"|"bottom"|"none"}
7. Circular Pattern:
   {"op": "circular_pattern", "feature": feature_id (optional), "axis": "z", "quantity": count, "angle": "360 deg"}
8. Linear Pattern:
   {"op": "linear_pattern", "feature": feature_id (optional), "direction": "x"|"y"|"z", "distance": spacing, "quantity": count}
9. Thread:
   {"op": "thread", "feature": feature_id (optional), "target": "internal"|"external"|"all" (optional), "modeled": true|false (optional, default true), "designation": "M6x1" (optional)}
10. Mirror:
   {"op": "mirror", "feature": feature_id (optional), "plane": "xy"|"xz"|"yz"|"top"|"bottom", "combine": true|false (optional, default true)}
11. Combine (Boolean):
   {"op": "combine", "target": body_or_feature_id (optional), "tools": [tool_id, ...], "mode": "cut"|"join"|"intersect", "keep_tools": false}
12. Sweep:
   {"op": "sweep", "sketch": profile_sketch_id, "path": path_sketch_id, "mode": "new_body"|"join"|"cut"}
13. Coil (Spring / Helix):
   {"op": "coil", "diameter": coil_dia, "pitch": pitch, "revolutions": count, "section_size": wire_dia, "axis": "z"|"x"|"y" (optional, default "z"), "mode": "new_body"|"join"|"cut" (optional, default "new_body")}

SKETCH ENTITIES (entities can have optional "id": "name" to be referenced by constraints)
{"type": "center_rectangle", "center": [a, b], "width": along a, "height": along b}
{"type": "circle", "center": [a, b], "diameter": d}
{"type": "polygon", "points": [[a, b], ...], "closed": true}   at least 3 points
{"type": "line", "start": [a, b], "end": [c, d]}
{"type": "polyline", "points": [[a, b], ...], "closed": false}  open spine/path for sweeps or wires

RULES & BEST PRACTICES
- NEVER combine two operations into one step! Each operation (`extrude`, `fillet`, `shell`, `chamfer`, etc.) MUST be its own separate entry in the `timeline` array.
- For hollow boxes or open containers, prefer `shell` with `remove_faces: "top"` over manual pocket cuts!
- When making an open box with rounded corners: FIRST `extrude`, NEXT `fillet` the vertical corners, THEN `shell` the top face (or shell first, then fillet). They are two distinct steps!
- For rounded corners or chamfered rims, use `fillet` or `chamfer` with edge selectors (`"vertical"`, `"top"`, `"circular"`).
- For radial arrays (e.g. 6 bolt holes on a flange), draw ONE hole and use `circular_pattern`!
- For symmetric designs, model ONE half and use `mirror` across "xz" or "yz" with `combine: true` to complete the full symmetric body!
- To carve or combine separate bodies, use `combine` with `mode: "cut"` / `"join"` and list tool body IDs in `tools`.
- For bent pipes, tubing, wire routing, or rails, draw a cross-section `sketch` and a spine/route `path` sketch, then use `sweep`.
- For hollow pipes or conduit: to ensure fluid can pass through, FIRST sweep the outer pipe body (`mode: "new_body"`), THEN sweep an inner bore circle with a smaller diameter along the path (`mode: "cut"`) so the pipe is hollow and has a through-bore from end to end.
- When modeling a gusset rib against a round pipe or cylinder: rib sketch points MUST extend into the body centerline (e.g. at [0, 0] or into the wall), NOT stop on the outer radius. Because round cylinders curve away from the offset sketch plane, stopping at the outer radius causes floating gaps!
- To thread a hole, bore, or bolt, add a `thread` step specifying the cut feature: `{"op": "thread", "feature": "bore_cut", "target": "internal", "designation": "M20x2.5"}`. Physical 3D threads are modeled by default (`modeled: true`).
- For springs, coils, or screw helices, use `coil` with `diameter` (major coil diameter), `section_size` (wire diameter), and `pitch` / `revolutions` (or `height`).
- The first 3D operation must be "new_body". "cut"/"join" must overlap existing material.
- An extrude or revolve uses EVERY closed region of its sketch. Never draw a shape inside another shape in the same sketch.
- A sketch must be defined before the operation that uses it.
- Prefer centering features at [0, 0].

EXAMPLE 1 (hollow enclosure with rounded corners)
""" + json.dumps({
    'parameters': {'box_width': '80 mm', 'box_length': '120 mm', 'box_height': '40 mm',
                   'wall_thick': '3 mm', 'corner_r': '6 mm'},
    'timeline': [
        {'op': 'sketch', 'id': 'base', 'plane': 'xy', 'entities': [
            {'type': 'center_rectangle', 'center': [0, 0], 'width': 'box_width', 'height': 'box_length'}]},
        {'op': 'extrude', 'id': 'outer_body', 'sketch': 'base', 'distance': 'box_height', 'mode': 'new_body'},
        {'op': 'fillet', 'edges': 'vertical', 'radius': 'corner_r'},
        {'op': 'shell', 'remove_faces': 'top', 'thickness': 'wall_thick'},
    ]}) + """

EXAMPLE 2 (flanged hub with bolt pattern)
""" + json.dumps({
    'parameters': {'flange_dia': '80 mm', 'flange_thick': '8 mm', 'boss_dia': '40 mm', 'boss_h': '30 mm',
                   'bore_dia': '20 mm', 'bolt_dia': '6 mm', 'bolt_r': '30 mm', 'bolt_qty': '6'},
    'timeline': [
        {'op': 'sketch', 'id': 'flange_sk', 'plane': 'xy', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'flange_dia'}]},
        {'op': 'extrude', 'sketch': 'flange_sk', 'distance': 'flange_thick', 'mode': 'new_body'},
        {'op': 'sketch', 'id': 'boss_sk', 'plane': 'xy', 'offset': 'flange_thick', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'boss_dia'}]},
        {'op': 'extrude', 'sketch': 'boss_sk', 'distance': 'boss_h', 'mode': 'join'},
        {'op': 'sketch', 'id': 'bore_sk', 'plane': 'xy', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'bore_dia'}]},
        {'op': 'extrude', 'sketch': 'bore_sk', 'distance': 'flange_thick + boss_h', 'mode': 'cut'},
        {'op': 'sketch', 'id': 'one_bolt', 'plane': 'xy', 'entities': [
            {'type': 'circle', 'center': ['bolt_r', 0], 'diameter': 'bolt_dia'}]},
        {'op': 'extrude', 'id': 'bolt_cut', 'sketch': 'one_bolt', 'distance': 'flange_thick', 'mode': 'cut'},
        {'op': 'circular_pattern', 'feature': 'bolt_cut', 'axis': 'z', 'quantity': 'bolt_qty'},
        {'op': 'chamfer', 'edges': 'circular', 'distance': '1 mm'}
    ]}) + """

EXAMPLE 3 (swept pipe elbow with through-bore, threaded outlet, and mirrored ribs)
""" + json.dumps({
    'parameters': {
        'pipe_od': '30 mm', 'pipe_id': '16 mm', 'pipe_len': '80 mm',
        'flange_dia': '80 mm', 'flange_thick': '10 mm',
        'boss_dia': '40 mm', 'boss_len': '25 mm', 'bore_dia': '20 mm',
        'gusset_thick': '4 mm'
    },
    'timeline': [
        {'op': 'sketch', 'id': 'path_sk', 'plane': 'xz', 'entities': [
            {'type': 'polyline', 'points': [[0, 'pipe_len'], [0, 0], ['pipe_len', 0]], 'closed': False}]},
        {'op': 'sketch', 'id': 'outer_sk', 'plane': 'xy', 'offset': 'pipe_len', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'pipe_od'}]},
        {'op': 'sweep', 'id': 'pipe_body', 'sketch': 'outer_sk', 'path': 'path_sk', 'mode': 'new_body'},
        {'op': 'sketch', 'id': 'flange_sk', 'plane': 'xy', 'offset': 'pipe_len - flange_thick', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'flange_dia'}]},
        {'op': 'extrude', 'sketch': 'flange_sk', 'distance': 'flange_thick', 'mode': 'join'},
        {'op': 'sketch', 'id': 'boss_sk', 'plane': 'yz', 'offset': 'pipe_len', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'boss_dia'}]},
        {'op': 'extrude', 'sketch': 'boss_sk', 'distance': 'boss_len', 'mode': 'join'},
        {'op': 'sketch', 'id': 'inner_sk', 'plane': 'xy', 'offset': 'pipe_len', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'pipe_id'}]},
        {'op': 'sketch', 'id': 'cut_path_sk', 'plane': 'xz', 'entities': [
            {'type': 'polyline', 'points': [[0, 'pipe_len + 2 mm'], [0, 0], ['pipe_len + boss_len + 2 mm', 0]], 'closed': False}]},
        {'op': 'sweep', 'id': 'bore_sweep', 'sketch': 'inner_sk', 'path': 'cut_path_sk', 'mode': 'cut'},
        {'op': 'sketch', 'id': 'port_sk', 'plane': 'yz', 'offset': 'pipe_len + boss_len', 'entities': [
            {'type': 'circle', 'center': [0, 0], 'diameter': 'bore_dia'}]},
        {'op': 'extrude', 'id': 'port_cut', 'sketch': 'port_sk', 'distance': '-boss_len', 'mode': 'cut'},
        {'op': 'thread', 'feature': 'port_cut', 'target': 'internal', 'designation': 'M20x2.5', 'modeled': True},
        {'op': 'sketch', 'id': 'gusset_sk', 'plane': 'xz', 'offset': 'pipe_od / 4', 'entities': [
            {'type': 'polygon', 'points': [[0, 'pipe_len - flange_thick - 5 mm'], [0, 0], ['pipe_len - 5 mm', 0]], 'closed': True}]},
        {'op': 'extrude', 'id': 'gusset', 'sketch': 'gusset_sk', 'distance': 'gusset_thick', 'mode': 'join'},
        {'op': 'mirror', 'feature': 'gusset', 'plane': 'xz', 'combine': True}
    ]})

TOOLS_NOTE = """

TOOLS
- You can call tools before answering. Use them when they help; when you have what you need, reply with
  ONLY the JSON design.
"""

CONTEXT_NOTE = """

THE USER'S CURRENT DESIGN (for reference; your design is built as new geometry next to it)
"""

MAX_TOOL_CALLS = 25


def system_prompt(tools=False, notes=''):
    """The system prompt; with tools, a general note plus what the offered toolkits say about theirs."""
    if not tools:
        return SYSTEM
    return SYSTEM + TOOLS_NOTE + (f'\n{notes.strip()}' if notes and notes.strip() else '')


def with_design_context(content, summary):
    """A user message with a picture of the current design, for models that can't call tools."""
    return f'{content}{CONTEXT_NOTE}{summary}' if summary else content


def clean_json(text):
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    if text and not text.startswith('{') and '{' in text and '}' in text:
        text = text[text.index('{'):text.rindex('}') + 1]  # prose around the JSON
    return text


def get_provider(provider_id):
    prov = providers.get_provider(provider_id)
    if not prov:
        raise ValueError(f'Unknown model provider: {provider_id!r}')
    return prov


def log_transcript(provider, model, prompt_or_msg, response_text, thinking_text='', error=None, attempt=1):
    """Append a full record of the LLM call to vibeshaper.log and overwrite last_response.txt."""
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sep = '=' * 80
    prompt_str = prompt_or_msg if isinstance(prompt_or_msg, str) else json.dumps(prompt_or_msg, indent=2)
    entry = [
        sep,
        f'[{now}] Provider: {provider} | Model: {model} | Attempt: {attempt}',
        '--- USER / PROMPT ---',
        prompt_str.strip(),
    ]
    if thinking_text and thinking_text.strip():
        entry.extend([
            '--- THINKING ---',
            thinking_text.strip(),
        ])
    if response_text:
        entry.extend([
            '--- RAW RESPONSE ---',
            response_text.strip(),
        ])
    entry.extend([
        '--- STATUS ---',
        f'ERROR: {error}' if error else 'SUCCESS: Validated successfully',
        sep,
        ''
    ])
    block = '\n'.join(entry) + '\n'

    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 5 * 1024 * 1024:
            old = LOG_FILE.with_suffix('.log.old')
            if old.exists():
                old.unlink()
            LOG_FILE.rename(old)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(block)
    except Exception as e:
        sys.stderr.write(f"VibeShaper: failed to write log: {e}\n")

    if response_text:
        try:
            with open(LAST_RESPONSE_FILE, 'w', encoding='utf-8') as f:
                f.write(response_text)
        except Exception:
            pass


def generate(provider_id, values, model, messages, think=False, tries=3, on_chunk=None, stop_event=None,
             on_open=None, log=print, tools=None, run_tool=None, max_tool_calls=MAX_TOOL_CALLS):
    """Ask until the reply parses and validates; errors are fed back to the model. Mutates `messages`.

    `values` are the provider's own settings; the reply is constrained to the DSL schema where the
    provider supports that. With `tools` (specs: name, description, parameters) and `run_tool(name, args)`,
    the model may call tools first; their results go back to it and don't count as attempts."""
    prov = get_provider(provider_id)
    tool_defs = [providers.ToolDef(t['name'], t['description'], t['parameters']) for t in tools] \
        if tools and run_tool else None
    used = 0
    request = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
    err = None
    attempt = 0

    def stopped():
        return stop_event is not None and stop_event.is_set()

    while attempt < tries:
        if stopped():
            raise InterruptedError('Generation cancelled by user')
        thoughts = []

        def intercept_chunk(kind, chunk):
            if kind == 'thought':
                thoughts.append(chunk)
            if on_chunk:
                on_chunk(kind, chunk)

        offer = tool_defs if tool_defs and used < max_tool_calls else None
        options = providers.GenerateOptions(think=bool(think), response_schema=dsl.JSON_SCHEMA, tools=offer)
        try:
            reply = prov.generate(model, messages, dict(values or {}), options, on_chunk=intercept_chunk,
                                  stop_event=stop_event, on_open=on_open, log=log)
        except InterruptedError:
            raise
        except Exception as e:
            if stopped():
                raise InterruptedError('Generation cancelled by user')
            log_transcript(provider_id, model, request, '', ''.join(thoughts), error=f"Network/API Error: {e}", attempt=attempt + 1)
            raise

        if stopped():
            raise InterruptedError('Generation cancelled by user')

        text, calls = (reply.text or '', list(reply.tool_calls)) if isinstance(reply, providers.Reply) else (reply, [])
        if calls and offer:
            messages.append({'role': 'assistant', 'content': text, 'tool_calls': [c.to_message() for c in calls]})
            for c in calls:
                if stopped():
                    raise InterruptedError('Generation cancelled by user')
                used += 1
                if used > max_tool_calls:
                    result = {'error': 'No more tool calls for this request. Reply with the JSON design now.'}
                else:
                    result = run_tool(c.name, c.arguments)
                messages.append({'role': 'tool', 'tool_call_id': c.id, 'name': c.name,
                                 'content': json.dumps(result, default=str)})
            log(f'VibeShaper: model called {", ".join(c.name for c in calls)} ({used} tool calls so far)')
            continue

        attempt += 1
        messages.append({'role': 'assistant', 'content': text})
        th_str = ''.join(thoughts)
        try:
            d = json.loads(clean_json(text))
            dsl.validate(d)
            log_transcript(provider_id, model, request, text, th_str, error=None, attempt=attempt)
            return d
        except ValueError as e:  # JSONDecodeError is a ValueError
            err = str(e)
            log(f'VibeShaper: invalid DSL ({err}):\n{text}')
            log_transcript(provider_id, model, request, text, th_str, error=err, attempt=attempt)
            messages.append({'role': 'user', 'content': fix_request(err)})
    raise ValueError(f'model gave invalid DSL {tries} times; last error: {err}')


def fix_request(err):
    return (
        f'Your JSON failed validation: {err}\n'
        'Remember: each 3D operation (extrude, fillet, shell, etc.) must be its OWN SEPARATE step in the timeline.\n'
        'Fillet takes ONLY "radius" and "edges". Shell takes ONLY "thickness" and "remove_faces".\n'
        'Output the complete corrected JSON.'
    )


def new_conversation(prompt):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]


def _main(argv):
    """python llm.py --provider ID --model NAME [--set key=value ...] [--think] prompt words"""
    import argparse
    ap = argparse.ArgumentParser(description='Generate a VibeShaper design from the command line.')
    ap.add_argument('--provider', required=True, choices=[p.id for p in providers.get_all_providers()])
    ap.add_argument('--model', required=True)
    ap.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help="a provider setting")
    ap.add_argument('--think', action='store_true')
    ap.add_argument('prompt', nargs='*')
    a = ap.parse_args(argv)
    prov = get_provider(a.provider)
    raw = dict(kv.split('=', 1) for kv in a.set if '=' in kv)
    values = providers.clean_values(prov.get_settings_schema(), raw)
    prompt = ' '.join(a.prompt) or 'a 40 mm cube with a 10 mm hole through the middle'
    print(json.dumps(generate(a.provider, values, a.model, new_conversation(prompt), think=a.think), indent=1))


if __name__ == '__main__':
    _main(sys.argv[1:])
