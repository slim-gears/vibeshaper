"""Chat sessions for PromptCAD: conversation history, design versions, and persistence.

Pure stdlib so it can be tested outside Fusion. A design document holds a ChatStore;
each Chat owns one timeline group (its current version) and the model conversation.
"""
import copy
import json
import time
import uuid

STORE_VERSION = 1
TITLE_LEN = 48


def _new_id():
    return uuid.uuid4().hex[:8]


def looks_like_json(text):
    return text.lstrip().startswith('{')


def make_title(text):
    t = ' '.join(str(text).split())
    if looks_like_json(t):
        try:
            name = json.loads(text).get('name')
            if name:
                t = str(name).replace('_', ' ')
            else:
                t = 'Imported design'
        except Exception:
            t = 'Imported design'
    return t if len(t) <= TITLE_LEN else t[:TITLE_LEN - 1].rstrip() + '…'


def manual_change_note(d):
    return ('I changed the design manually. The current design is:\n'
            + json.dumps(d) + '\n\nApply my next request on top of this design.')


class Chat:
    """One conversation about one part.

    messages: model history without the system prompt (added at send time).
    turns:    what the panel shows (user and assistant cards).
    versions: every design built; `current` is the version now in the timeline.
    pending_manual: a design changed by hand (JSON edit, restore, parameter edit)
                    that the model has not been told about yet.
    """

    def __init__(self, chat_id=None, title='New chat'):
        self.id = chat_id or _new_id()
        self.title = title
        self.created = time.time()
        self.messages = []
        self.turns = []
        self.versions = []
        self.current = None
        self.pending_manual = None
        # Where builds go. mode: 'component' | 'new_body' | None (= default from Settings).
        # occ: entity token of the chat's own component.
        self.target = {'mode': None, 'occ': None}

    # ----- versions -----------------------------------------------------
    def version(self, n):
        for v in self.versions:
            if v['n'] == n:
                return v
        return None

    def current_version(self):
        return self.version(self.current) if self.current is not None else None

    def current_dsl(self):
        v = self.current_version()
        return copy.deepcopy(v['dsl']) if v else None

    def group_name(self, n):
        return f'PromptCAD · {self.title} · v{n} [{self.id}]'

    def add_version(self, d, source, group_name=None, param_map=None, feature_count=0, placement=None):
        n = (self.versions[-1]['n'] + 1) if self.versions else 1
        v = {
            'n': n,
            'dsl': copy.deepcopy(d),
            'source': source,  # 'model' | 'json' | 'restore'
            'group_name': group_name,
            'param_map': dict(param_map or {}),
            'feature_count': feature_count,
            'placement': placement,  # {'mode', 'label'}: where it was built
            'created': time.time(),
        }
        self.versions.append(v)
        self.current = n
        return v

    # ----- turns --------------------------------------------------------
    def _turn(self, **fields):
        t = {'id': _new_id(), 'ts': time.time()}
        t.update(fields)
        self.turns.append(t)
        return t

    def turn(self, turn_id):
        for t in self.turns:
            if t['id'] == turn_id:
                return t
        return None

    def add_user_turn(self, text):
        if not self.turns and self.title == 'New chat':
            self.title = make_title(text)
        return self._turn(role='user', text=text, is_json=looks_like_json(text))

    def add_assistant_turn(self, kind, **fields):
        """kind: 'model' (asked the model), 'json' (built pasted/edited JSON), 'restore'."""
        base = dict(role='assistant', kind=kind, status='thinking' if kind == 'model' else 'building',
                    thought='', version=None, replaced=None, attempts=[], error=None)
        base.update(fields)
        return self._turn(**base)

    # ----- model conversation -------------------------------------------
    def begin_model_request(self, text, turn):
        """Append the user's message (with any pending manual change folded in).

        Records where this request starts so failed attempts can be trimmed later.
        """
        content = text
        if self.pending_manual is not None:
            content = manual_change_note(self.pending_manual) + '\n\n' + text
        turn['_mark'] = len(self.messages)
        turn['_pending_before'] = self.pending_manual
        turn['request'] = text
        self.messages.append({'role': 'user', 'content': content})
        self.pending_manual = None

    def model_messages(self, system):
        return [{'role': 'system', 'content': system}] + self.messages

    def commit_model_success(self, turn, d):
        """Keep only the request and the final good design in the model history."""
        mark = turn.get('_mark', len(self.messages) - 1)
        del self.messages[mark + 1:]
        self.messages.append({'role': 'assistant', 'content': json.dumps(d)})
        turn.pop('_mark', None)
        turn.pop('_pending_before', None)

    def rollback_model_request(self, turn):
        """Undo the request entirely (failed or stopped), so the user can retry or rephrase."""
        mark = turn.get('_mark')
        if mark is not None:
            del self.messages[mark:]
            self.pending_manual = turn.get('_pending_before')
        turn.pop('_mark', None)
        turn.pop('_pending_before', None)

    # ----- manual changes -----------------------------------------------
    def note_manual_design(self, d):
        self.pending_manual = copy.deepcopy(d)

    def set_param_in_current(self, name, expr):
        """Record a parameter edit made directly in Fusion. Returns the updated design."""
        v = self.current_version()
        if not v:
            raise ValueError('no design to edit yet')
        if name not in v['dsl'].get('parameters', {}):
            raise ValueError(f'unknown parameter {name!r}')
        v['dsl']['parameters'][name] = expr
        self.note_manual_design(v['dsl'])
        return v['dsl']

    # ----- persistence --------------------------------------------------
    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'created': self.created,
            'messages': self.messages, 'turns': self.turns, 'versions': self.versions,
            'current': self.current, 'pending_manual': self.pending_manual,
            'target': dict(self.target),
        }

    def to_view(self):
        """What the panel needs (no model history)."""
        d = self.to_dict()
        d.pop('messages')
        d['turns'] = [{k: val for k, val in t.items() if not k.startswith('_')} for t in d['turns']]
        return d

    @classmethod
    def from_dict(cls, data):
        c = cls(data.get('id'), data.get('title', 'New chat'))
        c.created = data.get('created', time.time())
        c.messages = list(data.get('messages', []))
        c.turns = list(data.get('turns', []))
        c.versions = list(data.get('versions', []))
        c.current = data.get('current')
        c.pending_manual = data.get('pending_manual')
        if isinstance(data.get('target'), dict):
            c.target.update({k: data['target'].get(k) for k in c.target})
        elif c.versions:
            c.target['mode'] = 'new_body'  # saved before build modes existed: built in the root
        # A turn that was mid-flight when the document was saved can't resume.
        for t in c.turns:
            if t.get('role') == 'assistant' and t.get('status') not in ('done', 'error', 'stopped'):
                t['status'] = 'stopped'
                c.rollback_model_request(t)
        return c


class ChatStore:
    """All chats of one design document."""

    def __init__(self):
        self.chats = []
        self.active_id = None
        self.tool_state = {}  # toolkit id -> that toolkit's own saved data for the document

    def active(self):
        for c in self.chats:
            if c.id == self.active_id:
                return c
        return None

    def get(self, chat_id):
        for c in self.chats:
            if c.id == chat_id:
                return c
        return None

    def new_chat(self):
        """Start a chat, reusing the active one if it is still empty."""
        cur = self.active()
        if cur and not cur.turns:
            return cur
        c = Chat()
        self.chats.append(c)
        self.active_id = c.id
        return c

    def ensure_active(self):
        return self.active() or self.new_chat()

    def switch(self, chat_id):
        if not self.get(chat_id):
            raise ValueError(f'unknown chat {chat_id!r}')
        self.active_id = chat_id
        return self.get(chat_id)

    def summaries(self):
        return [{'id': c.id, 'title': c.title, 'versions': len(c.versions), 'created': c.created}
                for c in self.chats if c.turns]

    def to_json(self):
        return json.dumps({'v': STORE_VERSION, 'active': self.active_id, 'tool_state': self.tool_state,
                           'chats': [c.to_dict() for c in self.chats if c.turns]})

    @classmethod
    def from_json(cls, text):
        s = cls()
        if not text:
            return s
        try:
            data = json.loads(text)
        except ValueError:
            return s
        s.chats = [Chat.from_dict(c) for c in data.get('chats', [])]
        s.active_id = data.get('active')
        ts = data.get('tool_state')
        s.tool_state = {k: v for k, v in ts.items() if isinstance(v, dict)} if isinstance(ts, dict) else {}
        if not s.active() and s.chats:
            s.active_id = s.chats[-1].id
        return s
