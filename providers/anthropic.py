"""Anthropic Claude model provider for VibeShaper."""
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .base import BaseProvider, GenerateOptions, ModelInfo, Reply, SettingDef, ToolCall

_API = 'https://api.anthropic.com/v1'
_VERSION = '2023-06-01'
_UA = {'User-Agent': 'VibeShaper/0.9'}
_ENV_KEYS = ('ANTHROPIC_API_KEY',)
_FALLBACK_MODELS = (
    ('claude-opus-4-5', 'Claude Opus 4.5'),
    ('claude-sonnet-4-5', 'Claude Sonnet 4.5'),
    ('claude-haiku-4-5', 'Claude Haiku 4.5'),
    ('claude-3-7-sonnet-latest', 'Claude 3.7 Sonnet'),
    ('claude-3-5-sonnet-latest', 'Claude 3.5 Sonnet'),
)


def _api_error(e: urllib.error.HTTPError) -> str:
    body = e.read().decode('utf-8', errors='replace')
    try:
        err = json.loads(body).get('error', body)
        return err.get('message', str(err)) if isinstance(err, dict) else str(err)
    except Exception:
        return body


def _can_think(mid: str) -> bool:
    low = mid.lower()
    return any(x in low for x in ('claude-3-7', 'claude-4', 'claude-sonnet-4', 'claude-opus-4', 'claude-haiku-4'))


def _to_anthropic(messages):
    """VibeShaper's provider-neutral messages -> (system_str, anthropic_messages)."""
    system, out = '', []
    for m in messages:
        role = m.get('role')
        imgs = [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': i.get('mime_type') or 'image/png', 'data': i['data']}}
            for i in (m.get('images') or ()) if isinstance(i, dict) and i.get('data')
        ]
        if role == 'system':
            system = m.get('content', '')
        elif role == 'tool':
            content: Any = m.get('content', '')
            if imgs:
                content = ([{'type': 'text', 'text': content}] if content else []) + imgs
            block = {
                'type': 'tool_result',
                'tool_use_id': m.get('tool_call_id') or m.get('name') or 'toolu_1',
                'content': content,
            }
            if out and out[-1]['role'] == 'user' and isinstance(out[-1]['content'], list) and \
                    out[-1]['content'] and out[-1]['content'][-1].get('type') == 'tool_result':
                out[-1]['content'].append(block)
            else:
                out.append({'role': 'user', 'content': [block]})
        elif role == 'assistant':
            blocks = []
            for c in m.get('tool_calls') or []:
                ex = c.get('extra') or {}
                if ex.get('thinking'):
                    blocks.append({'type': 'thinking', 'thinking': ex['thinking'],
                                   **({'signature': ex['signature']} if ex.get('signature') else {})})
                blocks.append({
                    'type': 'tool_use',
                    'id': c.get('id') or 'toolu_1',
                    'name': c['name'],
                    'input': c.get('arguments') or {},
                })
            if m.get('content'):
                blocks.insert(0, {'type': 'text', 'text': m['content']})
            out.append({'role': 'assistant', 'content': blocks or [{'type': 'text', 'text': ''}]})
        else:
            if imgs:
                parts = ([{'type': 'text', 'text': m.get('content', '')}] if m.get('content') else []) + imgs
                out.append({'role': 'user', 'content': parts})
            else:
                out.append({'role': 'user', 'content': m.get('content', '')})
    return system, out


class AnthropicProvider(BaseProvider):
    id = 'anthropic'
    name = 'Anthropic Claude'
    short_name = 'Claude'
    order = 40

    def get_settings_schema(self) -> List[SettingDef]:
        return [
            SettingDef(
                key='api_key',
                label='Anthropic API key',
                type='secret',
                default='',
                tooltip='From console.anthropic.com. Leave empty to use the ANTHROPIC_API_KEY environment variable.',
                required=True,
                refreshes_models=True,
            ),
        ]

    def _key(self, values: Dict[str, Any]) -> str:
        key = str((values or {}).get('api_key') or '').strip()
        for env in _ENV_KEYS:
            key = key or os.environ.get(env, '').strip()
        return key

    def is_configured(self, values: Dict[str, Any]) -> bool:
        return bool(self._key(values))

    def _headers(self, key: str, json_body: bool = False) -> Dict[str, str]:
        h = dict(_UA, **{'x-api-key': key, 'anthropic-version': _VERSION})
        if json_body:
            h['Content-Type'] = 'application/json'
        return h

    def list_models(self, values: Dict[str, Any], timeout: float = 5.0) -> List[ModelInfo]:
        key = self._key(values)
        if not key:
            raise ValueError('Add an Anthropic API key first.')
        req = urllib.request.Request(f'{_API}/models?limit=100', headers=self._headers(key))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Anthropic: {_api_error(e)}')
        except urllib.error.URLError as e:
            raise RuntimeError(f'Anthropic network error: {e.reason}')
        items = data.get('data') or [{'id': mid, 'display_name': label} for mid, label in _FALLBACK_MODELS]
        out = []
        for m in items:
            mid = str(m.get('id') or '').strip()
            if not mid.startswith('claude'):
                continue
            out.append(ModelInfo(mid, label=m.get('display_name') or mid, images=True,
                                 thinking=_can_think(mid), tools=True))
        return sorted(out, key=lambda x: x.id)

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
    ):
        opts = options or GenerateOptions()
        key = self._key(values)
        if not key:
            raise ValueError('Anthropic API key is missing. Add it in Settings → Anthropic Claude.')

        system, ant_msgs = _to_anthropic(messages)
        think = bool(opts.think and _can_think(model))
        payload: Dict[str, Any] = {
            'model': model.strip(),
            'max_tokens': 16384 if think else 8192,
            'messages': ant_msgs,
            'stream': True,
        }
        if think:
            payload['thinking'] = {'type': 'enabled', 'budget_tokens': 4096}
        else:
            payload['temperature'] = 0.2
        if system:
            payload['system'] = system
        if opts.tools:
            payload['tools'] = [
                {
                    'name': t.name,
                    'description': t.description,
                    'input_schema': t.parameters or {'type': 'object', 'properties': {}},
                }
                for t in opts.tools
            ]

        def open_stream():
            req = urllib.request.Request(f'{_API}/messages', json.dumps(payload).encode('utf-8'),
                                         self._headers(key, json_body=True))
            return urllib.request.urlopen(req, timeout=300)

        try:
            try:
                resp = open_stream()
            except urllib.error.HTTPError as e:
                if stop_event and stop_event.is_set():
                    raise InterruptedError('Generation cancelled by user')
                msg = _api_error(e)
                if 'thinking' in payload and 'thinking' in msg.lower():
                    log(f'VibeShaper: {model} rejected thinking ({msg}); retrying without it')
                    payload.pop('thinking', None)
                    payload['max_tokens'] = 8192
                    payload['temperature'] = 0.2
                    resp = open_stream()
                else:
                    raise RuntimeError(f'Anthropic: {msg}')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Anthropic: {_api_error(e)}')
        except urllib.error.URLError as e:
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise RuntimeError(f'Anthropic network error: {e.reason}')

        out, thinking_chars = [], 0
        blocks: Dict[int, Dict[str, Any]] = {}
        try:
            with resp:
                if on_open:
                    on_open(resp)
                for line in resp:
                    if stop_event and stop_event.is_set():
                        try:
                            resp.close()
                        except Exception:
                            pass
                        raise InterruptedError('Generation cancelled by user')
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if not line_str.startswith('data:'):
                        continue
                    data_json = line_str[5:].strip()
                    if not data_json:
                        continue
                    ev = json.loads(data_json)
                    etype = ev.get('type')
                    if etype == 'error':
                        err = ev.get('error') or {}
                        raise RuntimeError(f"Anthropic: {err.get('message', err)}")
                    elif etype == 'content_block_start':
                        idx = int(ev.get('index', 0))
                        cb = ev.get('content_block') or {}
                        btype = cb.get('type')
                        if btype == 'tool_use':
                            blocks[idx] = {'type': 'tool_use', 'id': cb.get('id') or '', 'name': cb.get('name') or '', 'json': ''}
                        elif btype == 'thinking':
                            blocks[idx] = {'type': 'thinking', 'thinking': '', 'signature': ''}
                    elif etype == 'content_block_delta':
                        idx = int(ev.get('index', 0))
                        delta = ev.get('delta') or {}
                        dtype = delta.get('type')
                        if dtype == 'text_delta':
                            txt = delta.get('text') or ''
                            if txt:
                                out.append(txt)
                                if on_chunk:
                                    on_chunk('text', txt)
                        elif dtype == 'thinking_delta':
                            th = delta.get('thinking') or ''
                            if th:
                                thinking_chars += len(th)
                                if idx in blocks:
                                    blocks[idx]['thinking'] += th
                                if on_chunk:
                                    on_chunk('thought', th)
                        elif dtype == 'signature_delta':
                            if idx in blocks:
                                blocks[idx]['signature'] += delta.get('signature') or ''
                        elif dtype == 'input_json_delta':
                            if idx in blocks and 'json' in blocks[idx]:
                                blocks[idx]['json'] += delta.get('partial_json') or ''
        except (OSError, ValueError):
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise

        thought_block = next((b for b in blocks.values() if b.get('type') == 'thinking' and b.get('thinking')), None)
        calls = []
        for idx in sorted(blocks):
            b = blocks[idx]
            if b.get('type') != 'tool_use':
                continue
            try:
                args = json.loads(b['json']) if b['json'].strip() else {}
            except ValueError:
                args = {}
            extra = {}
            if not calls and thought_block:
                extra = {'thinking': thought_block['thinking'], 'signature': thought_block.get('signature', '')}
            calls.append(ToolCall(b['id'] or f'toolu_{len(calls) + 1}', b['name'], args, extra))

        res_text = ''.join(out)
        if calls:
            log(f'VibeShaper: Anthropic asked for {len(calls)} tool calls (thinking {thinking_chars} chars)')
            return Reply(res_text, calls)
        if not res_text:
            raise RuntimeError('Anthropic returned an empty response')
        log(f'VibeShaper: got {len(res_text)} chars from Anthropic (thinking {thinking_chars} chars)')
        return res_text
