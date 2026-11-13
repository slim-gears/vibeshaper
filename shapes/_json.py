"""Declarative JSON shape macros: load a single-part design JSON as a parametric shape plugin."""
import json
import pathlib
import re

from . import _parts as p
from .base import BaseShape

_ENUM_STR_KEYS = frozenset({
    'op', 'type', 'mode', 'plane', 'direction', 'direction2', 'faces', 'face',
    'at', 'section', 'edges', 'remove_faces', 'note', 'head', 'nut', 'collet',
    'model', 'series', 'block',
})
_METRIC_THREAD = re.compile(r'^M\d')


def _is_bare_number(v):
    if isinstance(v, bool):
        return False
    try:
        float(str(v).strip())
        return True
    except ValueError:
        return False


def _remap_ident(text, mapping):
    if not mapping or not text:
        return text
    keys = sorted((re.escape(k) for k in mapping), key=len, reverse=True)
    return re.sub(r'\b(' + '|'.join(keys) + r')\b', lambda m: mapping[m.group(0)], text)


def _schema_for_input(spec):
    if 'choices' in spec:
        ch = list(spec['choices'])
        if ch and all(isinstance(c, str) and c.isdigit() for c in ch):
            return {'type': ['string', 'number']}
        return {'enum': ch}
    t = spec.get('type', 'length')
    if t == 'boolean':
        return {'type': 'boolean'}
    if t == 'string':
        return {'type': 'string'}
    return {'type': ['string', 'number']}


class JsonShape(BaseShape):
    """A shape plugin loaded from a declarative JSON macro (or plain single-part design JSON)."""

    def __init__(self, data):
        if not isinstance(data, dict):
            raise ValueError('JSON shape must be an object')
        op = data.get('op')
        if not isinstance(op, str) or not p._NAME.match(op):
            raise ValueError(f'JSON shape: bad or missing op {op!r}')
        tl = data.get('timeline')
        if not isinstance(tl, list) or not tl or not all(isinstance(s, dict) for s in tl):
            raise ValueError(f'JSON shape {op!r}: timeline must be a non-empty list of step objects')

        self.op = op
        self.name = str(data.get('name') or op)
        self.order = int(data.get('order', 100))
        raw_prompt = data.get('prompt', '')
        self.prompt = '\n'.join(raw_prompt) if isinstance(raw_prompt, list) else str(raw_prompt)
        self._inputs = dict(data.get('inputs') or {})
        self._presets = data.get('presets')
        self._parameters = dict(data.get('parameters') or {})
        self._bom = list(data.get('bom') or [])
        self._timeline = tl

        schema = dict(p.PLAIN_KEYS)
        if self._inputs:
            for k, spec in self._inputs.items():
                schema[k] = _schema_for_input(spec)
        else:
            for k in self._parameters:
                schema[k] = {'type': ['string', 'number']}
        self.schema = schema

    def _active_preset(self, step):
        if not self._presets:
            return {}
        sel_key = self._presets['key']
        sel_default = self._inputs.get(sel_key, {}).get('default', '')
        sel_val = str(step.get(sel_key, sel_default))
        return dict(self._presets['values'].get(sel_val, {}))

    def validate(self, step, where):
        required = tuple(k for k, spec in self._inputs.items() if spec.get('required'))
        choices = {}
        for k, spec in self._inputs.items():
            if 'choices' in spec:
                ch = list(spec['choices'])
                if ch and all(isinstance(c, str) and c.isdigit() for c in ch):
                    ch = ch + [int(c) for c in ch]
                choices[k] = ch
                if k in step and isinstance(step[k], bool):
                    raise ValueError(f'{where}: {k} must be one of {tuple(ch)}')
        p.check(step, where, required, choices)
        for k, spec in self._inputs.items():
            if k not in step or 'choices' in spec:
                continue
            t = spec.get('type', 'length')
            val = step[k]
            if t == 'boolean':
                if not isinstance(val, bool):
                    raise ValueError(f'{where}: {k} must be true or false')
            elif t == 'string':
                if not isinstance(val, str):
                    raise ValueError(f'{where}: {k} must be a string')
            elif t == 'number':
                if isinstance(val, bool) or p.num(val) is None or p.num(val) <= 0:
                    raise ValueError(f'{where}: {k} must be a number of mm, more than 0')
            else:
                if isinstance(val, bool) or (p.num(val) is not None and p.num(val) <= 0):
                    raise ValueError(f'{where}: {k} must be more than 0')
        preset_vals = self._active_preset(step)
        for k in list(preset_vals) + list(self._parameters):
            if k in step and k not in self._inputs:
                val = step[k]
                if isinstance(val, bool):
                    raise ValueError(f'{where}: {k} must be a number or expression')
                is_positive = k in preset_vals or (p.num(self._parameters[k]) or 0) > 0
                if is_positive and p.num(val) is not None and p.num(val) <= 0:
                    raise ValueError(f'{where}: {k} must be more than 0')

    def expand(self, step):
        gid = step['id']
        preset_vals = self._active_preset(step)
        param_keys = []
        seen = set()
        for k in list(preset_vals) + list(self._parameters):
            if k not in seen:
                seen.add(k)
                param_keys.append(k)
        for k, spec in self._inputs.items():
            is_param = spec.get('param', 'choices' not in spec and spec.get('type', 'length') not in ('boolean', 'string'))
            if is_param and k not in seen:
                seen.add(k)
                param_keys.append(k)

        step_ids = [s['id'] for s in self._timeline[:-1] if 'id' in s]
        ident_map = {k: f'{gid}_{k}' for k in param_keys + step_ids}

        def is_unitless(k):
            if self._inputs.get(k, {}).get('type') == 'count':
                return True
            return k in self._parameters and k not in self._inputs and k not in preset_vals and _is_bare_number(self._parameters[k])

        out_params = {}
        for k in param_keys:
            pk = f'{gid}_{k}'
            if k in step:
                v = step[k]
                if is_unitless(k):
                    out_params[pk] = v if _is_bare_number(v) else f'({v})'
                else:
                    out_params[pk] = p.length(v)
            elif k in preset_vals:
                pv = preset_vals[k]
                out_params[pk] = p.length(pv) if isinstance(pv, (int, float)) else _remap_ident(str(pv), ident_map)
            elif k in self._parameters:
                rv = self._parameters[k]
                out_params[pk] = rv if isinstance(rv, (int, float)) else _remap_ident(str(rv), ident_map)
            elif k in self._inputs and 'default' in self._inputs[k]:
                dv = self._inputs[k]['default']
                if isinstance(dv, (int, float)):
                    out_params[pk] = dv if is_unitless(k) else p.length(dv)
                else:
                    out_params[pk] = _remap_ident(str(dv), ident_map)

        def xform(val, key=None, in_entity=False):
            if isinstance(val, str):
                if in_entity and key in ('id', 'type', 'of'):
                    return val
                if key in _ENUM_STR_KEYS:
                    return val
                if key == 'axis' and val in ('x', 'y', 'z'):
                    return val
                if key == 'size' and _METRIC_THREAD.match(val):
                    return val
                return _remap_ident(val, ident_map)
            if isinstance(val, list):
                if in_entity and key in ('entities', 'of'):
                    return list(val)
                if not in_entity and key == 'entities':
                    return [xform(item, None, True) for item in val]
                return [xform(item, key, in_entity) for item in val]
            if isinstance(val, dict):
                return {dk: xform(dv, dk, in_entity) for dk, dv in val.items()}
            return val

        out_steps = []
        last = len(self._timeline) - 1
        for idx, s in enumerate(self._timeline):
            ns = {dk: xform(dv, dk, False) for dk, dv in s.items() if dk != 'id'}
            if idx == last:
                ns['id'] = gid
            elif 'id' in s:
                ns['id'] = f'{gid}_{s["id"]}'
            out_steps.append(ns)
        return out_params, out_steps

    def bom(self, step):
        if not self._bom:
            return []
        ctx = {k: spec['default'] for k, spec in self._inputs.items() if 'default' in spec}
        ctx.update(self._active_preset(step))
        for k, v in self._parameters.items():
            ctx.setdefault(k, v)
        for k, v in step.items():
            if k != 'id':
                ctx[k] = v

        def fmt(v):
            n = None if isinstance(v, bool) else p.num(v)
            return f'{n:g}' if n is not None else str(v)

        items = []
        for tpl in self._bom:
            it = dict(tpl)
            keep = {'length', 'length_mm'} if 'length' in it else set()
            it['item'] = re.sub(
                r'\{([A-Za-z_][A-Za-z0-9_]*)\}',
                lambda m: m.group(0) if m.group(1) in keep or m.group(1) not in ctx else fmt(ctx[m.group(1)]),
                it['item'],
            )
            for ekey in ('length', 'qty'):
                if ekey in it and isinstance(it[ekey], str) and it[ekey] in ctx:
                    ref = it[ekey]
                    if ref in step:
                        it[ekey] = step[ref]
                    elif p.num(ctx[ref]) is not None:
                        it[ekey] = p.num(ctx[ref])
                    elif 'id' in step:
                        it[ekey] = f'{step["id"]}_{ref}'
            if step.get('note') and 'note' not in it:
                it['note'] = step['note']
            items.append(it)
        return items


def load_json_shape(path):
    """Load and return a JsonShape from a .json file path."""
    data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    return JsonShape(data)
