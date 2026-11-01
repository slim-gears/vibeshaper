"""Ollama model provider for VibeShaper."""
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .base import BaseProvider, GenerateOptions, ModelInfo, Reply, SettingDef, ToolCall

_UA = {'User-Agent': 'VibeShaper/0.2'}


def _to_ollama(messages):
    """VibeShaper's provider-neutral messages -> Ollama /api/chat messages."""
    out = []
    for m in messages:
        if m.get('role') == 'tool':
            out.append({'role': 'tool', 'content': m.get('content', ''), 'tool_name': m.get('name', '')})
        elif m.get('tool_calls'):
            out.append({'role': 'assistant', 'content': m.get('content', ''),
                        'tool_calls': [{'function': {'name': c['name'], 'arguments': c.get('arguments') or {}}}
                                       for c in m['tool_calls']]})
        else:
            out.append({'role': m['role'], 'content': m.get('content', '')})
    return out


class OllamaProvider(BaseProvider):
    id = 'ollama'
    name = 'Ollama (Local)'
    short_name = 'Ollama'
    order = 10

    def get_settings_schema(self) -> List[SettingDef]:
        return [
            SettingDef(
                key='url',
                label='Ollama URL',
                type='string',
                default='http://localhost:11434',
                tooltip='Endpoint URL of your local or remote Ollama server',
                required=True,
                refreshes_models=True,
            ),
        ]

    @staticmethod
    def _url(values: Dict[str, Any]) -> str:
        return str(values.get('url') or 'http://localhost:11434').strip().rstrip('/')

    def _get_json(self, url: str, body: Optional[dict], timeout: float) -> dict:
        data = json.dumps(body).encode('utf-8') if body is not None else None
        req = urllib.request.Request(url, data, dict(_UA, **({'Content-Type': 'application/json'} if data else {})))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def list_models(self, values: Dict[str, Any], timeout: float = 5.0) -> List[ModelInfo]:
        base = self._url(values)
        try:
            tags = self._get_json(f'{base}/api/tags', None, timeout)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'Ollama at {base} answered {e.code} {e.reason}')
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise RuntimeError(f'Could not connect to Ollama at {base}: {getattr(e, "reason", e)}')
        names = [m.get('name', '') for m in tags.get('models', []) if m.get('name')]

        def caps(name):
            try:  # capabilities are reported per model
                return self._get_json(f'{base}/api/show', {'model': name}, timeout).get('capabilities')
            except Exception:
                return None  # unknown: assume plain text only

        with ThreadPoolExecutor(max_workers=8) as pool:
            all_caps = list(pool.map(caps, names))
        out = []
        for name, c in zip(names, all_caps):
            c = set(c or ['completion'])
            if 'completion' not in c:
                continue  # embedding-only models can't chat
            out.append(ModelInfo(name, images='vision' in c, thinking='thinking' in c, tools='tools' in c))
        return sorted(out, key=lambda m: m.id)

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
        think = bool(opts.think)
        body = {'model': model, 'messages': _to_ollama(messages), 'think': think, 'stream': True,
                'options': {'temperature': 0.2}}
        if opts.tools:
            body['tools'] = [{'type': 'function', 'function': {'name': t.name, 'description': t.description,
                                                               'parameters': t.parameters}} for t in opts.tools]
        elif opts.response_schema:
            body['format'] = opts.response_schema  # a reply format would block tool calls, so only without tools
        req = urllib.request.Request(f'{self._url(values)}/api/chat', json.dumps(body).encode('utf-8'),
                                     dict(_UA, **{'Content-Type': 'application/json'}))

        def retry_without_thinking():
            log(f"VibeShaper: model '{model}' does not support thinking, retrying without it")
            return self.generate(model, messages, values, GenerateOptions(False, opts.response_schema, opts.tools),
                                 on_chunk, stop_event, on_open, log)

        out, thinking, calls = [], 0, []
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            err_body = e.read().decode('utf-8', errors='replace')
            try:
                err_msg = json.loads(err_body).get('error', err_body)
            except Exception:
                err_msg = err_body
            if think and 'does not support thinking' in err_msg.lower():
                return retry_without_thinking()
            raise RuntimeError(f'Ollama: {err_msg}')
        except urllib.error.URLError as e:
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise RuntimeError(f'Ollama network error: {e.reason}')

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
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if 'error' in chunk:
                        err_msg = chunk['error']
                        if think and 'does not support thinking' in err_msg.lower():
                            return retry_without_thinking()
                        raise RuntimeError(f'Ollama: {err_msg}')
                    msg = chunk.get('message', {})
                    th = msg.get('thinking', '')
                    if th:
                        thinking += len(th)
                        if on_chunk:
                            on_chunk('thought', th)
                    txt = msg.get('content', '')
                    if txt:
                        out.append(txt)
                        if on_chunk:
                            on_chunk('text', txt)
                    for tc in msg.get('tool_calls') or []:
                        fn = tc.get('function') or {}
                        args = fn.get('arguments') or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except ValueError:
                                args = {}
                        calls.append(ToolCall(f'call_{len(calls) + 1}', fn.get('name', ''), args))
                    if chunk.get('done'):
                        break
        except (OSError, ValueError):
            if stop_event and stop_event.is_set():
                raise InterruptedError('Generation cancelled by user')
            raise

        res_text = ''.join(out)
        log(f'VibeShaper: got {len(res_text)} chars from Ollama (thinking {thinking} chars, {len(calls)} tool calls)')
        return Reply(res_text, calls) if calls else res_text
