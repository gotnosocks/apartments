"""Source-declared unit page extraction shared by transforms and archive backfills."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

def unit_page(url, base='https://streeteasy.com/'):
    try:
        parsed = urlsplit(urljoin(base, url or ''))
    except ValueError:
        return None
    if (parsed.scheme not in {'http', 'https'} or parsed.netloc.lower() not in {'streeteasy.com', 'www.streeteasy.com'}
        or parsed.query or parsed.fragment):
        return None
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 3 or parts[0] != 'building' or not all(parts):
        return None
    return 'https://streeteasy.com/' + '/'.join(parts)


class Head(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        attrs = dict(attrs)
        if tag == 'link' and 'canonical' in (attrs.get('rel') or '').lower().split():
            self.links.append(attrs.get('href') or '')
        if tag == 'body':
            self.done = True

    def handle_endtag(self, tag):
        if tag == 'head':
            self.done = True


def head_fields(parser, url):
    links = set(parser.links)
    error = None
    href = next(iter(links)) if len(links)==1 else None
    if not parser.done:
        error = 'Incomplete HTML head'
    elif len(links) != 1:
        error = 'Missing or conflicting canonical links'
    normalized = unit_page(href, url) if href and not error else None
    if not error and not normalized:
        error = 'Canonical link is not a unit page'
    return {'canonical_href':href, 'canonical_unit_url':normalized, 'canonical_unit_error':error}


def canonical_fields(body, url):
    parser = Head()
    text = body.decode('utf-8', errors='replace') if isinstance(body,bytes) else body
    # Same bounded head parser as the existing-dataset backfill.
    for start in range(0,min(len(text),1048576),8192):
        parser.feed(text[start:start+8192])
        if parser.done:
            break
    return head_fields(parser,url)
