"""OpenAI (and OpenAI-compatible API) model provider for VibeShaper."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .base import BaseProvider, GenerateOptions, ModelInfo, Reply, SettingDef, ToolCall

_DEFAULT_URL = 'https://api.openai.com/v1'
_UA = {'User-Agent': 'VibeShaper/0.9'}
_ENV_KEYS = ('OPENAI_API_KEY',)
_SKIP_PREFIXES = (
    'text-embedding', 'whisper', 'tts-', 'dall-e', 'omni-moderation',
    'text-moderation', 'babbage', 'davinci', 'canary-', 'sora',
)


def _api_error(e: urllib.error.HTTPError) -> str:
    body = e.read().decode('utf-8', errors='replace')
    try:
        err = json.loads(body).get('error', body)
        return err.get('message', str(err)) if isinstance(err, dict) else str(err)
    except Exception:
        return body


def _is_chat_model(mid: str) -> bool:
    low = mid.lower()
    if any(low.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if any(w in low for w in ('-realtime', '-audio', '-transcribe', '-tts', 'embedding', 'moderation')):
        return False
    return True


def _model_caps(mid: str):
    low = mid.lower()
    thinking = low.startswith(('o1', 'o3', 'o4', 'gpt-5')) or any(w in low for w in ('reasoner', 'r1', 'qwq', 'qwen3'))
    images = not any(w in low for w in ('gpt-3.5', 'o1-mini', 'o3-mini', 'deepseek-coder', 'codestral'))
    return images, thinking


def _to_openai(messages):
    """VibeShaper's provider-neutral messages -> OpenAI /v1/chat/completions messages."""
    out = []
    pending_imgs = []
    for idx, m in enumerate(messages):
        role = m.get('role')
        imgs = [
            {'type': 'image_url', 'image_url': {'url': f"data:{i.get('mime_type') or 'image/png'};base64,{i['data']}"}}
            for i in (m.get('images') or ()) if isinstance(i, dict) and i.get('data')
        ]
        if role == 'tool':
            out.append({
                'role': 'tool',
                'tool_call_id': m.get('tool_call_id') or m.get('name') or 'call_1',
                'content': m.get('content', ''),
            })
            if imgs:
                pending_imgs.extend(imgs)
            next_role = messages[idx + 1].get('role') if idx + 1 < len(messages) else None
            if pending_imgs and next_role != 'tool':
                out.append({
                    'role': 'user',
                    'content': [{'type': 'text', 'text': 'Viewport images from tool call:'}, *pending_imgs],
                })
                pending_imgs = []
        elif role == 'assistant':
            entry: Dict[str, Any] = {'role': 'assistant', 'content': m.get('content') or ''}
            tcs = m.get('tool_calls') or []
            if tcs:
                entry['tool_calls'] = [
                    {
                        'id': c.get('id') or f'call_{i + 1}',
                        'type': 'function',
                        'function': {
                            'name': c['name'],
                            'arguments': json.dumps(c.get('arguments') or {}),
                        },
                    }
                    for i, c in enumerate(tcs)
                ]
            out.append(entry)
        elif role == 'user' and imgs:
            parts = ([{'type': 'text', 'text': m.get('content', '')}] if m.get('content') else []) + imgs
            out.append({'role': 'user', 'content': parts})
        else:
            out.append({'role': role, 'content': m.get('content', '')})
    return out


class OpenAIProvider(BaseProvider):
    id = 'openai'
    name = 'OpenAI'
    short_name = 'OpenAI'
    order = 30
    multiple = True

    def get_settings_schema(self) -> List[SettingDef]:
        return [
            SettingDef(
                key='name',
                label='Name',
                type='string',
                default='',
                tooltip='Optional display name (defaults to OpenAI or the server hostname).',
                required=False,
                refreshes_models=False,
            ),
            SettingDef(
                key='base_url',
                label='Base URL',
                type='string',
                default=_DEFAULT_URL,
                tooltip='Default https://api.openai.com/v1, or any OpenAI-compatible endpoint (OpenRouter, DeepSeek, Groq, LM Studio, vLLM).',
                required=False,
                refreshes_models=True,
            ),
            SettingDef(
                key='api_key',
                label='API key',
                type='secret',
                default='',
                tooltip='OpenAI API key (or leave empty to use OPENAI_API_KEY, or when using a local server that needs no key).',
                required=False,
                refreshes_models=True,
            ),
        ]

    def instance_names(self, values: Dict[str, Any], index: int = 0):
        custom = str((values or {}).get('name') or '').strip()
        if custom:
            return custom, custom
        base = self._base_url(values)
        if base != _DEFAULT_URL:
            parsed = urllib.parse.urlparse(base)
            host = parsed.hostname or ''
            if host in ('localhost', '127.0.0.1', '::1') and parsed.netloc:
                return parsed.netloc, parsed.netloc
            if host:
                return host, host
        return super().instance_names(values, index)

    @staticmethod
    def _base_url(values: Dict[str, Any]) -> str:
        url = str((values or {}).get('base_url') or _DEFAULT_URL).strip().rstrip('/')
        if not url:
            return _DEFAULT_URL
        parsed = urllib.parse.urlparse(url)
        if not parsed.path or parsed.path == '/':
            return f'{url}/v1'
        return url

    def _key(self, values: Dict[str, Any]) -> str:
        key = str((values or {}).get('api_key') or '').strip()
        if not key and self._base_url(values) == _DEFAULT_URL:
            for env in _ENV_KEYS:
                key = key or os.environ.get(env, '').strip()
        return key

    def is_configured(self, values: Dict[str, Any]) -> bool:
        if self._base_url(values) != _DEFAULT_URL:
            return True
        return bool(self._key(values))

    def _headers(self, values: Dict[str, Any], json_body: bool = False) -> Dict[str, str]:
        h = dict(_UA)
        key = self._key(values)
        if key:
            h['Authorization'] = f'Bearer {key}'
        if json_body:
            h['Content-Type'] = 'application/json'
        return h

    def list_models(self, values: Dict[str, Any], timeout: float = 5.0) -> List[ModelInfo]:
        base = self._base_url(values)
        if not self.is_configured(values):
            raise ValueError('Add an OpenAI API key first.')
        req = urllib.request.Request(f'{base}/models', headers=self._headers(values))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'OpenAI: {_api_error(e)}')
        except urllib.error.URLError as e:
            raise RuntimeError(f'OpenAI network error: {e.reason}')
        out = []
        for m in data.get('data', []):
            mid = str(m.get('id') or '').strip()
            if not mid or not _is_chat_model(mid):
                continue
            images, thinking = _model_caps(mid)
            out.append(ModelInfo(mid, label=mid, images=images, thinking=thinking, tools=True))
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
        if not self.is_configured(values):
            raise ValueError('OpenAI API key is missing. Add it in Settings → OpenAI.')
        base = self._base_url(values)
        url = f'{base}/chat/completions'
        _, can_think = _model_caps(model)

        payload: Dict[str, Any] = {
            'model': model.strip(),
            'messages': _to_openai(messages),
            'stream': True,
        }
        if opts.think and can_think:
            payload['reasoning_effort'] = 'medium'
        elif not model.lower().startswith(('o1', 'o3', 'o4')):
            payload['temperature'] = 0.2

        if opts.tools:
            payload['tools'] = [
                {
                    'type': 'function',
                    'function': {
                        'name': t.name,
                        'description': t.description,
                        'parameters': t.parameters or {'type': 'object', 'properties': {}},
                    },
                }
                for t in opts.tools
            ]
        else:
            payload['response_format'] = {'type': 'json_object'}

        def open_stream():
            req = urllib.request.Request(url, json.dumps(payload).encode('utf-8'),
                                         self._headers(values, json_body=True))
            return urllib.request.urlopen(req, timeout=300)

        try:
            try:
                resp = open_stream()
            except urllib.error.HTTPError as e:
                if stop_event and stop_event.is_set():
                    raise InterruptedError('Generation cancelled by user')
                msg = _api_error(e)
                low = msg.lower()
                if 'reasoning_effort' in payload and ('reasoning_effort' in low or 'unrecognized' in low or 'unsupported' in low):
                    log(f'VibeShaper: {model} rejected reasoning_effort ({msg}); retrying without it')
                    payload.pop('reasoning_effort', None)
                    resp = open_stream()
                elif 'response_format' in payload and ('response_format' in low or 'json_object' in low):
                    log(f'VibeShaper: {model} rejected response_format ({msg}); retrying without it')
                    payload.pop('response_format', None)
                    resp = open_stream()
                elif 'temperature' in payload and 'temperature' in low:
                    payload.pop('temperature', None)
                    resp = open_stream()
                elif 'tools' in payload and 'does not support tools' in low:
                    log(f'VibeShaper: {model} does not support tools ({msg}); retrying without tools')
                    payload.pop('tools', None)
                    resp = open_stream()
                else:
                    raise RuntimeError(f'OpenAI: {msg}')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'OpenAI: {_api_error(e)}')
        except urllib.error.URLError as e:
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise RuntimeError(f'OpenAI network error: {e.reason}')

        out, thinking = [], 0
        tc_by_idx: Dict[int, Dict[str, str]] = {}
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
                    if not data_json or data_json == '[DONE]':
                        continue
                    chunk = json.loads(data_json)
                    if 'error' in chunk and chunk['error']:
                        err = chunk['error']
                        raise RuntimeError(f"OpenAI: {err.get('message', err) if isinstance(err, dict) else err}")
                    choices = chunk.get('choices') or []
                    if not choices:
                        continue
                    delta = choices[0].get('delta') or {}
                    th = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if th:
                        thinking += len(th)
                        if on_chunk:
                            on_chunk('thought', th)
                    txt = delta.get('content') or ''
                    if txt:
                        out.append(txt)
                        if on_chunk:
                            on_chunk('text', txt)
                    for tc in delta.get('tool_calls') or []:
                        idx = int(tc.get('index', 0))
                        slot = tc_by_idx.setdefault(idx, {'id': '', 'name': '', 'args': ''})
                        if tc.get('id'):
                            slot['id'] = tc['id']
                        fn = tc.get('function') or {}
                        if fn.get('name'):
                            slot['name'] += fn['name']
                        if fn.get('arguments'):
                            slot['args'] += fn['arguments']
        except (OSError, ValueError):
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise

        calls = []
        for idx in sorted(tc_by_idx):
            slot = tc_by_idx[idx]
            try:
                args = json.loads(slot['args']) if slot['args'].strip() else {}
            except ValueError:
                args = {}
            calls.append(ToolCall(slot['id'] or f'call_{len(calls) + 1}', slot['name'], args))

        res_text = ''.join(out)
        if calls:
            log(f'VibeShaper: OpenAI asked for {len(calls)} tool calls (thinking {thinking} chars)')
            return Reply(res_text, calls)
        if not res_text:
            raise RuntimeError('OpenAI returned an empty response')
        log(f'VibeShaper: got {len(res_text)} chars from OpenAI (thinking {thinking} chars)')
        return res_text
