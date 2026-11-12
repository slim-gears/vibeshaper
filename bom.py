"""Bill of materials: everything to buy and make for a design, with quantities.

Items come from three places:
- shape steps (their plugin's bom(): a motor, a rail cut to length, the screws for some holes),
- a component's own "bom" list, and the design's top-level "bom" (wires, a power supply...).
A component's items count once per instance; a shape's items also once per copy a later
pattern step makes of it. A component that no item marks as "whole" is a part to make, and is
listed as one.

Runs without Fusion:  python bom.py design.json [out.csv]
"""
import ast
import csv
import io
import json
import math
import operator
import re
import sys

try:
    from . import dsl, shapes
except ImportError:  # run as a plain script (tests, the command line)
    import dsl
    import shapes

_UNITS = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'in': 25.4, 'deg': math.pi / 180, 'rad': 1.0}
_NUM_UNIT = re.compile(r'(?<![\w.])(\d+\.?\d*|\.\d+)\s*(mm|cm|m|in|deg|rad)\b')
_PLAIN = re.compile(r'^\s*-?(\d+\.?\d*|\.\d+)\s*$')
_FUNCS = {'sqrt': math.sqrt, 'abs': abs, 'floor': math.floor, 'ceil': math.ceil, 'round': round,
          'min': min, 'max': max, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
          'asin': math.asin, 'acos': math.acos, 'atan': math.atan}
_CONSTS = {'pi': math.pi, 'PI': math.pi}
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow, ast.Mod: operator.mod}
COLUMNS = ('Category', 'Item', 'Qty', 'Unit', 'Note', 'Link')
MADE = 'Made'


class Evaluator:
    """Evaluates DSL expressions in plain Python: lengths in mm, angles in radians."""

    def __init__(self, params):
        self.params = dict(params or {})
        self.values = {}
        self._busy = set()

    def __call__(self, expr):
        if isinstance(expr, (int, float)) and not isinstance(expr, bool):
            return float(expr)
        text = _NUM_UNIT.sub(lambda m: f'({float(m.group(1)) * _UNITS[m.group(2)]!r})', str(expr))
        try:
            tree = ast.parse(text.replace('^', '**'), mode='eval')
        except SyntaxError:
            raise ValueError(f'cannot read the expression {expr!r}')
        return float(self._node(tree.body, expr))

    def _name(self, name, expr):
        if name in _CONSTS:
            return _CONSTS[name]
        if name not in self.params:
            raise ValueError(f'{expr!r} uses {name!r}, which is not a parameter')
        if name not in self.values:
            if name in self._busy:
                raise ValueError(f'parameter {name!r} depends on itself')
            self._busy.add(name)
            try:
                self.values[name] = self(self.params[name])
            finally:
                self._busy.discard(name)
        return self.values[name]

    def _node(self, n, expr):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            return self._name(n.id, expr)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = self._node(n.operand, expr)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](self._node(n.left, expr), self._node(n.right, expr))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*(self._node(a, expr) for a in n.args))
        raise ValueError(f'cannot evaluate {expr!r}')


def _pattern_copies(timeline, fid, ev):
    """How many copies later pattern steps make of feature fid (1 when none)."""
    copies = 1
    if not fid:
        return copies
    for s in timeline:
        if isinstance(s, dict) and s.get('op') in ('circular_pattern', 'linear_pattern') and s.get('feature') == fid:
            n = round(ev(s.get('quantity', 1)))
            if s.get('op') == 'linear_pattern' and 'quantity2' in s:
                n *= round(ev(s['quantity2']))
            copies *= max(n, 1)
    return copies


def _fmt_len(mm):
    return f'{mm:g} mm' if mm < 1000 else f'{mm / 1000:g} m'


def _fmt_qty(q):
    return str(int(round(q))) if abs(q - round(q)) < 1e-9 else f'{q:.2f}'.rstrip('0').rstrip('.')


def _line(it, times, ev, where):
    """One item as (key, qty, round step)."""
    name = it['item']
    if 'length' in it:
        length = abs(ev(it['length']))
        stock = sorted(it.get('stock') or [])
        if stock:
            fits = [s for s in stock if s >= length - 1e-6]
            if not fits:
                raise ValueError(f'{where}: {name!r} needs {length:g} mm, longer than any stock length')
            length = fits[0]
        length = round(length, 2)
        name = name.replace('{length_mm}', f'{length:g}').replace('{length}', _fmt_len(length))
    unit = it.get('unit', 'pcs')
    qty = it.get('qty', 1)
    if unit in dsl.BOM_UNITS_LENGTH and not _PLAIN.match(str(qty)):  # an expression with lengths: mm
        q = ev(qty) / dsl.BOM_UNITS_LENGTH[unit]
    else:
        q = ev(qty)
    if q < 0:
        raise ValueError(f'{where}: {name!r} has a negative quantity')
    key = (it['category'], name, unit, it.get('note', ''), it.get('link', ''))
    return key, q * times, it.get('round')


def collect(d):
    """The design's bill of materials: a list of rows {Category, Item, Qty, Unit, Note, Link}."""
    dsl.validate(d)
    ev = Evaluator((dsl.expand_shapes(d).get('parameters') or {}))
    totals, rounding, order = {}, {}, []

    def add(items, times, where):
        dsl.check_bom(items, where)
        whole = False
        for k, it in enumerate(items):
            key, q, step = _line(it, times, ev, f'{where}[{k}]')
            if key not in totals:
                totals[key] = 0.0
                order.append(key)
            totals[key] += q
            if step:
                rounding[key] = max(rounding.get(key, 0), step)
            whole = whole or it.get('whole', False)
        return whole

    def timeline(tl, times, label):
        whole = False
        for i, s in enumerate(tl or []):
            shape = shapes.get_shape(s.get('op')) if isinstance(s, dict) else None
            if shape:
                copies = _pattern_copies(tl[i + 1:], s.get('id'), ev)
                whole = add(shape.bom(s) or [], times * copies, f'{label}[{i}] ({s["op"]}) bom') or whole
        return whole

    def made(name, material, times):
        add([dict({'category': MADE, 'item': name}, **({'note': material} if material else {}))],
            times, 'made parts')

    if d.get('timeline') and not timeline(d['timeline'], 1, 'timeline'):
        made(d.get('name') or 'Main part', None, 1)
    placed = {}
    for inst in d.get('instances') or []:
        placed[inst['component']] = placed.get(inst['component'], 0) + 1
    for k, c in enumerate(d.get('components') or []):
        times = placed.get(c['id'], 1)
        whole = timeline(c['timeline'], times, f'components[{k}].timeline')
        whole = add(c.get('bom', []), times, f'components[{k}].bom') or whole
        if not whole:
            made(c.get('name') or c['id'], c.get('material'), times)
    add(d.get('bom', []), 1, 'bom')

    rows = []
    for key in order:
        category, item, unit, note, link = key
        q = totals[key]
        if rounding.get(key):
            q = math.ceil(q / rounding[key] - 1e-9) * rounding[key]
        rows.append({'Category': category, 'Item': item, 'Qty': q, 'Unit': unit, 'Note': note, 'Link': link})
    rows.sort(key=lambda r: (r['Category'] == MADE, r['Category'].lower(), r['Item'].lower()))
    return rows


def to_csv(rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow(dict(r, Qty=_fmt_qty(r['Qty'])))
    return out.getvalue()


def main(argv):
    if len(argv) not in (2, 3):
        print('usage: python bom.py design.json [out.csv]', file=sys.stderr)
        return 2
    with open(argv[1], encoding='utf-8') as f:
        text = to_csv(collect(json.load(f)))
    if len(argv) == 3:
        with open(argv[2], 'w', encoding='utf-8-sig', newline='') as f:  # Excel reads the BOM mark as UTF-8
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
