"""Read-only browser for the repository's documentation and analysis reports."""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / 'docs'
PREFIX = '/docs'


def _inside(path: Path) -> Path:
    path = path.resolve()
    try:
        path.relative_to(DOCS_ROOT.resolve())
    except ValueError as exc:
        raise FileNotFoundError(path) from exc
    return path


def _target(value: str, current: Path) -> str:
    value = html.unescape(value).strip()
    if value.startswith(('#', 'http://', 'https://', 'mailto:')):
        return value
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return value
    raw_path, fragment = value.split('#', 1) if '#' in value else (value, '')
    target = _inside((current.parent / raw_path).resolve())
    relative = '/' + target.relative_to(ROOT).as_posix()
    if fragment:
        relative += '#' + quote(fragment, safe='-_.')
    return relative


def _inline(text: str, current: Path) -> str:
    value = html.escape(text, quote=False)
    links: list[str] = []

    def link(match: re.Match[str]) -> str:
        label, destination = match.group(1), match.group(2)
        href = html.escape(_target(destination, current), quote=True)
        token = f'\x00LINK{len(links)}\x00'
        links.append(f'<a href="{href}">{label}</a>')
        return token

    value = re.sub(r'\[([^]]+)\]\(([^)]+)\)', link, value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', value)
    for index, replacement in enumerate(links):
        value = value.replace(f'\x00LINK{index}\x00', replacement)
    return value


def render_markdown(text: str, source: Path) -> str:
    """Small dependency-free Markdown renderer for the project's report format."""
    lines = text.replace('\r\n', '\n').split('\n')
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_kind: str | None = None
    code: list[str] | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append('<p>' + _inline(' '.join(x.strip() for x in paragraph), source) + '</p>')
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if list_items:
            tag = list_kind or 'ul'
            blocks.append(f'<{tag}>' + ''.join(f'<li>{x}</li>' for x in list_items) + f'</{tag}>')
            list_items, list_kind = [], None

    def flush_code() -> None:
        nonlocal code
        if code is not None:
            blocks.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>')
            code = None

    index = 0
    while index < len(lines):
        line = lines[index]
        if code is not None:
            if line.strip().startswith('```'):
                flush_code()
            else:
                code.append(line)
            index += 1
            continue
        if line.strip().startswith('```'):
            flush_paragraph(); flush_list(); code = []
            index += 1
            continue
        if not line.strip():
            flush_paragraph(); flush_list(); index += 1; continue
        heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
        if heading:
            flush_paragraph(); flush_list()
            level = len(heading.group(1))
            blocks.append(f'<h{level}>' + _inline(heading.group(2), source) + f'</h{level}>')
            index += 1
            continue
        if re.match(r'^\s*([-*_])(?:\s*\1){2,}\s*$', line):
            flush_paragraph(); flush_list(); blocks.append('<hr>'); index += 1; continue
        item = re.match(r'^\s*[-*+]\s+(.+)$', line)
        ordered = re.match(r'^\s*\d+[.)]\s+(.+)$', line)
        if item or ordered:
            flush_paragraph()
            kind = 'ol' if ordered else 'ul'
            if list_kind and list_kind != kind: flush_list()
            list_kind = kind; list_items.append(_inline((ordered or item).group(1), source))
            index += 1; continue
        if line.lstrip().startswith('>'):
            flush_paragraph(); flush_list()
            blocks.append('<blockquote>' + _inline(line.lstrip()[1:].lstrip(), source) + '</blockquote>')
            index += 1; continue
        if index + 1 < len(lines) and '|' in line and re.match(r'^\s*\|?\s*:?-{3,}', lines[index + 1]):
            flush_paragraph(); flush_list()
            headers = [x.strip() for x in line.strip().strip('|').split('|')]
            index += 2
            rows = []
            while index < len(lines) and '|' in lines[index] and lines[index].strip():
                rows.append([x.strip() for x in lines[index].strip().strip('|').split('|')]); index += 1
            head = ''.join(f'<th>{_inline(x, source)}</th>' for x in headers)
            body = ''.join('<tr>' + ''.join(f'<td>{_inline(x, source)}</td>' for x in row) + '</tr>' for row in rows)
            blocks.append(f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')
            continue
        paragraph.append(line)
        index += 1
    flush_code(); flush_paragraph(); flush_list()
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    title = _inline(title_match.group(1), source) if title_match else 'Apartments documentation'
    return _HTML.replace('__TITLE__', title).replace('__BODY__', '\n'.join(blocks))


def _directory(path: Path, url_path: str) -> str:
    items = []
    if path != DOCS_ROOT:
        parent = '/'.join(url_path.rstrip('/').split('/')[:-1]) or PREFIX
        items.append(f'<li><a href="{html.escape(parent)}/">↩ Parent</a></li>')
    for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if child.name.startswith('.'):
            continue
        href = (url_path.rstrip('/') + '/' + quote(child.name))
        if child.is_dir(): href += '/'
        label = child.name + ('/' if child.is_dir() else '')
        items.append(f'<li><a href="{href}">{html.escape(label)}</a></li>')
    body = '<h1>NYC apartments documentation</h1><p>Read-only reports and project records.</p><ul>' + ''.join(items) + '</ul>'
    return _HTML.replace('__TITLE__', 'Documentation index').replace('__BODY__', body)


def create_app(root: Path = DOCS_ROOT):
    from flask import Flask, abort, make_response, send_file
    app = Flask('apartments-docs')
    docs_root = _inside(root)

    @app.get('/')
    def index():
        return _directory(docs_root, PREFIX + '/')

    @app.get('/docs/')
    @app.get('/docs/<path:requested>')
    def document(requested=''):
        try:
            path = _inside(docs_root / requested)
        except FileNotFoundError:
            abort(404)
        url_path = PREFIX + ('/' + requested if requested else '/')
        if path.is_dir():
            return _directory(path, url_path)
        if not path.is_file():
            abort(404)
        if path.suffix.lower() == '.md':
            response = make_response(render_markdown(path.read_text(), path))
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            return response
        if path.suffix.lower() == '.html':
            return send_file(path)
        abort(404)

    return app


def serve(*, host='127.0.0.1', port=8768, listen=None):
    from waitress import serve as waitress_serve
    app = create_app()
    waitress_serve(app, threads=2, **({'listen': listen} if listen else {'host': host, 'port': port}))


_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>body{max-width:1200px;margin:0 auto;padding:24px;font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:#17202a;background:#fbfcfe}h1{border-bottom:2px solid #d6dde8;padding-bottom:8px}h2{margin-top:2em}a{color:#1459a6}table{border-collapse:collapse;width:100%;margin:1em 0;background:white}th,td{border:1px solid #d6dde8;padding:6px 9px;text-align:left;vertical-align:top}th{background:#edf2f7}pre{overflow:auto;padding:12px;background:#17202a;color:#f8fafc;border-radius:5px}code{background:#edf2f7;padding:1px 4px;border-radius:3px}pre code{background:transparent;padding:0}blockquote{border-left:4px solid #9aaabd;padding-left:12px;color:#4b5563}li{margin:3px 0}hr{border:0;border-top:1px solid #d6dde8;margin:2em 0}</style></head><body>__BODY__</body></html>'''
''