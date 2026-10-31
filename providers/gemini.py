"""Google Gemini model provider for PromptCAD."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .base import BaseProvider, GenerateOptions, ModelInfo, Reply, SettingDef, ToolCall

_API = 'https://generativelanguage.googleapis.com/v1beta'
_UA = {'User-Agent': 'PromptCAD/0.2'}
_ENV_KEYS = ('GEMINI_API_KEY', 'GOOGLE_API_KEY')


def _api_error(e: urllib.error.HTTPError) -> str:
    body = e.read().decode('utf-8', errors='replace')
    try:
        return json.loads(body).get('error', {}).get('message', body)
    except Exception:
        return body


def _to_gemini(messages):
    """PromptCAD's provider-neutral messages -> (systemInstruction, contents)."""
    system, contents = None, []
    for m in messages:
        role = m.get('role')
        if role == 'system':
            system = {'parts': [{'text': m.get('content', '')}]}
        elif role == 'tool':
            try:
                result = json.loads(m.get('content') or 'null')
            except ValueError:
                result = m.get('content')
            part = {'functionResponse': {'name': m.get('name', ''), 'response': {'result': result}}}
            # all results of one round go back together, in one user turn
            if contents and contents[-1]['role'] == 'user' and contents[-1]['parts'] and \
                    'functionResponse' in contents[-1]['parts'][-1]:
                contents[-1]['parts'].append(part)
            else:
                contents.append({'role': 'user', 'parts': [part]})
        elif role == 'assistant':
            parts = [{'text': m['content']}] if m.get('content') else []
            for c in m.get('tool_calls') or []:
                parts.append({'functionCall': {'name': c['name'], 'args': c.get('arguments') or {}},
                              **(c.get('extra') or {})})
            contents.append({'role': 'model', 'parts': parts or [{'text': ''}]})
        else:
            contents.append({'role': 'user', 'parts': [{'text': m.get('content', '')}]})
    return system, contents


class GeminiProvider(BaseProvider):
    id = 'gemini'
    name = 'Google Gemini'
    short_name = 'Gemini'
    order = 20

    def get_settings_schema(self) -> List[SettingDef]:
        return [
            SettingDef(
                key='api_key',
                label='Gemini API key',
                type='secret',
                default='',
                tooltip='From Google AI Studio. Leave empty to use the GEMINI_API_KEY environment variable.',
                required=True,
                refreshes_models=True,
            ),
        ]

    def _key(self, values: Dict[str, Any]) -> str:
        key = str(values.get('api_key') or '').strip()
        for env in _ENV_KEYS:
            key = key or os.environ.get(env, '').strip()
        return key

    def is_configured(self, values: Dict[str, Any]) -> bool:
        return bool(self._key(values))

    def list_models(self, values: Dict[str, Any], timeout: float = 5.0) -> List[ModelInfo]:
        key = self._key(values)
        if not key:
            raise ValueError('Add a Gemini API key first.')
        req = urllib.request.Request(f'{_API}/models?pageSize=1000&key={urllib.parse.quote(key)}', headers=_UA)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Gemini: {_api_error(e)}')
        except urllib.error.URLError as e:
            raise RuntimeError(f'Gemini network error: {e.reason}')
        out = []
        for m in data.get('models', []):
            mid = str(m.get('name', '')).removeprefix('models/')
            if 'generateContent' not in m.get('supportedGenerationMethods', []) or not mid.startswith('gemini'):
                continue
            # Gemini chat models all take images and tools; thinking is reported per model.
            out.append(ModelInfo(mid, label=m.get('displayName') or mid, images=True,
                                 thinking=bool(m.get('thinking')), tools=True))
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
            raise ValueError('Gemini API key is missing. Add it in Settings → Gemini.')

        model_name = model.strip().removeprefix('models/')
        url = f'{_API}/models/{model_name}:streamGenerateContent?alt=sse&key={urllib.parse.quote(key)}'

        sys_instruction, contents = _to_gemini(messages)

        # Think on: show the model's reasoning. Off: ask for no thinking budget (some models
        # always think and reject that; the request is then retried without the setting).
        thinking_cfg = {'includeThoughts': True} if opts.think else {'thinkingBudget': 0}
        payload = {'contents': contents,
                   'generationConfig': {'temperature': 0.2, 'thinkingConfig': thinking_cfg}}
        if opts.tools:  # a JSON-only reply can't be combined with function calling
            payload['tools'] = [{'functionDeclarations': [
                {'name': t.name, 'description': t.description,
                 **({'parameters': t.parameters} if (t.parameters or {}).get('properties') else {})}  # Gemini rejects empty objects
                for t in opts.tools]}]
        else:
            payload['generationConfig']['responseMimeType'] = 'application/json'
        if sys_instruction:
            payload['systemInstruction'] = sys_instruction

        def open_stream():
            req = urllib.request.Request(url, json.dumps(payload).encode('utf-8'),
                                         dict(_UA, **{'Content-Type': 'application/json'}))
            return urllib.request.urlopen(req, timeout=300)

        try:
            try:
                resp = open_stream()
            except urllib.error.HTTPError as e:
                if stop_event and stop_event.is_set():
                    raise InterruptedError('Generation cancelled by user')
                msg = _api_error(e)
                if 'think' not in msg.lower():
                    raise RuntimeError(f'Gemini: {msg}')
                log(f'PromptCAD: {model_name} rejected the thinking setting ({msg}); retrying without it')
                payload['generationConfig'].pop('thinkingConfig')
                resp = open_stream()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Gemini: {_api_error(e)}')
        except urllib.error.URLError as e:
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise RuntimeError(f'Gemini network error: {e.reason}')

        out, thinking, calls = [], 0, []
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
                    chunk = json.loads(data_json)
                    if 'error' in chunk:
                        raise RuntimeError(f'Gemini: {chunk["error"].get("message", chunk["error"])}')
                    cand = chunk.get('candidates', [{}])[0]
                    for p in cand.get('content', {}).get('parts', []):
                        if p.get('thought'):
                            th = p.get('text', '')
                            thinking += len(th)
                            if on_chunk:
                                on_chunk('thought', th)
                        elif 'functionCall' in p:
                            fc = p['functionCall']
                            # signatures must go back with the call in the next request
                            extra = {k: v for k, v in p.items() if k != 'functionCall'}
                            calls.append(ToolCall(fc.get('id') or f'call_{len(calls) + 1}', fc.get('name', ''),
                                                  fc.get('args') or {}, extra))
                        elif 'text' in p:
                            txt = p.get('text', '')
                            out.append(txt)
                            if on_chunk:
                                on_chunk('text', txt)
        except (OSError, ValueError):
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise

        res_text = ''.join(out)
        if calls:
            log(f'PromptCAD: Gemini asked for {len(calls)} tool calls (thinking {thinking} chars)')
            return Reply(res_text, calls)
        if not res_text:
            raise RuntimeError('Gemini returned an empty response')
        log(f'PromptCAD: got {len(res_text)} chars from Gemini (thinking {thinking} chars)')
        return res_text
