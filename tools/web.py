"""Zero-config web search and page reading tools for looking up real-world object dimensions and specs.

Uses Python's standard library only (urllib + html.parser):
- DuckDuckGo Lite HTML search with automatic fallback/supplement via the Wikipedia Search API.
- Plain-text & table extraction from web pages or Wikipedia articles.
"""
import html
import html.parser
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .base import BaseToolkit, ToolError

DEFAULT_RESULTS = 5
MAX_RESULTS = 10
DEFAULT_CHARS = 6000
MAX_CHARS = 20000
HTTP_TIMEOUT = 10.0
MAX_DOWNLOAD_BYTES = 512 * 1024

_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
_API_UA = 'VibeShaper/0.8 (https://github.com/slim-gears/vibeshaper)'

TOOL_SPECS = [
    {
        'name': 'web_search',
        'description': ('Search the web (and Wikipedia) for real-world object dimensions, datasheets, '
                        'standard part sizes, mounting hole spacings, or mechanical specifications.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Search query (e.g. "Raspberry Pi 5 mechanical dimensions mounting holes mm").',
                },
                'max_results': {
                    'type': 'integer',
                    'description': f'Maximum results to return (default {DEFAULT_RESULTS}, max {MAX_RESULTS}).',
                },
            },
            'required': ['query'],
        },
    },
    {
        'name': 'fetch_web_page',
        'description': ('Fetch and read the text and tables of a web page or Wikipedia article URL '
                        'returned by web_search to extract exact dimensions and specifications.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'url': {
                    'type': 'string',
                    'description': 'HTTP or HTTPS URL of the page to read.',
                },
                'max_chars': {
                    'type': 'integer',
                    'description': f'Maximum characters of text to return (default {DEFAULT_CHARS}, max {MAX_CHARS}).',
                },
            },
            'required': ['url'],
        },
    },
]
TOOL_NAMES = [t['name'] for t in TOOL_SPECS]


def _ws(text):
    return re.sub(r'[ \t\r\f\v]+', ' ', html.unescape(text or '')).strip()


def _strip_tags(raw):
    return _ws(re.sub(r'<[^>]+>', ' ', raw or ''))


def _unwrap_ddg_url(href):
    href = (href or '').strip()
    if href.startswith('//'):
        href = 'https:' + href
    parsed = urllib.parse.urlparse(href)
    if 'duckduckgo.com' in parsed.netloc and parsed.path.startswith('/l/'):
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get('uddg'):
            return qs['uddg'][0]
    return href


class _DDGLiteParser(html.parser.HTMLParser):
    """Extracts {title, url, snippet} items from DuckDuckGo Lite HTML."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._mode = None
        self._buf = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        cls = ad.get('class') or ''
        if tag == 'a' and 'result-link' in cls:
            url = _unwrap_ddg_url(ad.get('href', ''))
            if url and not url.startswith('https://duckduckgo.com/y.js'):
                self._cur = {'title': '', 'url': url, 'snippet': ''}
                self._mode = 'title'
                self._buf = []
        elif tag == 'td' and 'result-snippet' in cls and self._cur is not None:
            self._mode = 'snippet'
            self._buf = []

    def handle_endtag(self, tag):
        if self._mode == 'title' and tag == 'a' and self._cur is not None:
            self._cur['title'] = _ws(''.join(self._buf))
            self._mode = None
            self._buf = []
        elif self._mode == 'snippet' and tag == 'td' and self._cur is not None:
            self._cur['snippet'] = _ws(''.join(self._buf))
            self.results.append(self._cur)
            self._cur = None
            self._mode = None
            self._buf = []

    def handle_data(self, data):
        if self._mode:
            self._buf.append(data)


class _PageTextParser(html.parser.HTMLParser):
    """Converts HTML into compact readable text, preserving headings, lists, and table rows."""

    _SKIP = {'script', 'style', 'noscript', 'svg', 'nav', 'footer', 'form', 'iframe'}
    _BLOCK = {'p', 'div', 'section', 'article', 'main', 'header', 'blockquote',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'br', 'hr', 'pre'}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self.title = ''
        self._title_buf = []
        self._parts = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == 'title':
            self._in_title = True
            self._title_buf = []
        elif tag in self._BLOCK:
            self._parts.append('\n')
            if tag == 'li':
                self._parts.append('- ')
        elif tag in ('td', 'th'):
            if self._in_cell:
                self._parts.append(' | ')
            self._in_cell = True

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == 'title':
            self._in_title = False
            self.title = _ws(''.join(self._title_buf))
        elif tag == 'tr':
            self._in_cell = False
            self._parts.append('\n')
        elif tag in self._BLOCK:
            self._parts.append('\n')

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self._title_buf.append(data)
        else:
            txt = re.sub(r'[ \t\r\f\v]+', ' ', data)
            if txt.strip():
                self._parts.append(txt)

    def get_text(self):
        raw = html.unescape(''.join(self._parts))
        lines = [re.sub(r'[ \t]+', ' ', ln).strip(' |') for ln in raw.splitlines()]
        cleaned = []
        for ln in lines:
            if ln:
                cleaned.append(ln)
            elif cleaned and cleaned[-1] != '':
                cleaned.append('')
        return '\n'.join(cleaned).strip()


def _search_ddg(query, limit, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(
        'https://lite.duckduckgo.com/lite/',
        data=urllib.parse.urlencode({'q': query}).encode('utf-8'),
        headers={'User-Agent': _BROWSER_UA, 'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'text/html,application/xhtml+xml'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_DOWNLOAD_BYTES).decode('utf-8', errors='replace')
    parser = _DDGLiteParser()
    parser.feed(raw)
    if parser._cur and parser._cur.get('title'):
        parser.results.append(parser._cur)
    return [r for r in parser.results if r.get('title') and r.get('url')][:limit]


def _search_wikipedia(query, limit, timeout=HTTP_TIMEOUT):
    qs = urllib.parse.urlencode({
        'action': 'query', 'list': 'search', 'srsearch': query,
        'srlimit': max(1, min(limit, MAX_RESULTS)), 'format': 'json',
    })
    req = urllib.request.Request(f'https://en.wikipedia.org/w/api.php?{qs}', headers={'User-Agent': _API_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read(MAX_DOWNLOAD_BYTES).decode('utf-8', errors='replace'))
    out = []
    for item in data.get('query', {}).get('search', []):
        title = item.get('title', '').strip()
        if not title:
            continue
        slug = urllib.parse.quote(title.replace(' ', '_'))
        out.append({
            'title': f'{title} (Wikipedia)',
            'url': f'https://en.wikipedia.org/wiki/{slug}',
            'snippet': _strip_tags(item.get('snippet', '')),
        })
    return out[:limit]


def _fetch_wikipedia_article(title, max_chars, timeout=HTTP_TIMEOUT):
    qs = urllib.parse.urlencode({
        'action': 'query', 'prop': 'extracts', 'explaintext': 1,
        'redirects': 1, 'titles': title, 'format': 'json',
    })
    req = urllib.request.Request(f'https://en.wikipedia.org/w/api.php?{qs}', headers={'User-Agent': _API_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read(MAX_DOWNLOAD_BYTES).decode('utf-8', errors='replace'))
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        extract = (page.get('extract') or '').strip()
        if extract:
            return {
                'url': f'https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(" ", "_"))}',
                'title': page.get('title') or title,
                'content': extract[:max_chars],
                'truncated': len(extract) > max_chars,
            }
    return None


def web_search(args):
    query = str(args.get('query') or '').strip()
    if not query:
        raise ToolError('query is required.')
    try:
        limit = int(args.get('max_results') or DEFAULT_RESULTS)
    except (TypeError, ValueError):
        limit = DEFAULT_RESULTS
    limit = max(1, min(MAX_RESULTS, limit))

    results, errors = [], []
    seen_urls = set()

    try:
        for r in _search_ddg(query, limit):
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                results.append(r)
    except Exception as e:
        errors.append(f'DuckDuckGo: {e}')

    if len(results) < limit:
        try:
            for r in _search_wikipedia(query, limit - len(results)):
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    results.append(r)
        except Exception as e:
            errors.append(f'Wikipedia: {e}')

    if not results and errors:
        raise ToolError('Web search failed: ' + '; '.join(errors))
    return {'query': query, 'results': results[:limit], 'total': len(results[:limit])}


def fetch_web_page(args):
    url = str(args.get('url') or '').strip()
    if not url:
        raise ToolError('url is required.')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ToolError('url must be a valid http:// or https:// address.')
    try:
        max_chars = int(args.get('max_chars') or DEFAULT_CHARS)
    except (TypeError, ValueError):
        max_chars = DEFAULT_CHARS
    max_chars = max(500, min(MAX_CHARS, max_chars))

    # Wikipedia URLs: use the clean plain-text extracts API first, then fall back to HTML if needed
    if parsed.netloc.endswith('wikipedia.org') and parsed.path.startswith('/wiki/'):
        wiki_title = urllib.parse.unquote(parsed.path[len('/wiki/'):]).replace('_', ' ')
        if wiki_title:
            try:
                art = _fetch_wikipedia_article(wiki_title, max_chars)
                if art:
                    return art
            except Exception:
                pass

    req = urllib.request.Request(url, headers={
        'User-Agent': _BROWSER_UA,
        'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5',
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            ctype = (resp.headers.get('Content-Type') or '').lower()
            if 'application/pdf' in ctype or parsed.path.lower().endswith('.pdf'):
                raise ToolError('PDF files cannot be read directly; pick an HTML page or use the search snippet.')
            raw_bytes = resp.read(MAX_DOWNLOAD_BYTES)
    except ToolError:
        raise
    except urllib.error.HTTPError as e:
        raise ToolError(f'HTTP {e.code} {e.reason} fetching {url}')
    except urllib.error.URLError as e:
        raise ToolError(f'Could not connect to {url}: {getattr(e, "reason", e)}')

    raw = raw_bytes.decode('utf-8', errors='replace')
    if 'text/plain' in ctype or 'application/json' in ctype:
        text, title = raw.strip(), parsed.netloc
    else:
        parser = _PageTextParser()
        parser.feed(raw)
        text, title = parser.get_text(), parser.title or parsed.netloc

    return {
        'url': url,
        'title': title,
        'content': text[:max_chars],
        'truncated': len(text) > max_chars,
    }


_TOOLS = {'web_search': web_search, 'fetch_web_page': fetch_web_page}


def label(name, args, result):
    a = args or {}
    err = isinstance(result, dict) and result.get('error')
    if name == 'web_search':
        what = f'Searched the web for “{a.get("query", "")}”'
        if not err and isinstance(result, dict) and 'total' in result:
            what += f' · {result["total"]}'
    elif name == 'fetch_web_page':
        u = str(a.get('url') or '')
        host = urllib.parse.urlparse(u).netloc or u
        what = f'Read {host}'
        title = not err and isinstance(result, dict) and result.get('title')
        if title and title != host:
            what += f' · {title[:40]}'
    else:
        what = f'Called {name}'
    return f'{what} (failed: {err})' if err else what


PROMPT = """LOOKING UP REAL-WORLD DIMENSIONS ON THE WEB
- You have `web_search` and `fetch_web_page` to look up real-world objects, standard parts, electronics boards,
  batteries, mounts, or mechanical specifications on the web.
- Whenever the user's request names a real-world product or standard part whose exact dimensions are not already
  in your built-in shapes (e.g. "Raspberry Pi 5 case", "18650 battery holder", "GoPro mount", "Arduino Uno tray",
  "VESA 75/100 adapter"), search for its dimensions and mounting hole spacings first instead of guessing."""


class WebToolkit(BaseToolkit):
    """Zero-config web search and page text extraction for real-world object specs and dimensions."""
    id = 'web'
    name = 'Web search'
    order = 20
    main_thread = False
    prompt = PROMPT

    def tools(self):
        return [dict(t) for t in TOOL_SPECS]

    def run(self, name, args, ctx):
        fn = _TOOLS.get(name)
        if not fn:
            raise ToolError(f'Unknown tool "{name}".')
        return fn(args or {})

    def label(self, name, args, result):
        return label(name, args, result)
