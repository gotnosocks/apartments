"""Parse each captured listing page once per crawl step.

The crawler calls collection_policy.annotate twice for every listing page: once before it records
the capture, to put the policy verdict into the stored data, and once after, to write exclusions
and memberships. Each call runs apartments.granular_parse.parse_listing on the same body, about
0.035 s per ad page on the crawler's main thread in Midtown West (Oct 2026).

parse_listing_once keeps the last body, URL and result. When the next call passes the same URL and
the same body, it returns copies of the stored row and events without parsing again. Any other
call parses and replaces the stored result. A call that raises stores nothing, so a repeat raises
again as before. annotate reads the row and events without changing them, and the copies keep it
that way for any other caller.

granular_parse.py is hashed by saved datasets, so the change lives here. annotate imports
parse_listing when it runs, and cli applies the memo with parse_once() for crawl commands.
"""

from contextlib import contextmanager

from apartments import granular_parse

ORIGINAL_PARSE = granular_parse.parse_listing
_last = None


def parse_listing_once(body, url):
    global _last
    if _last is not None:
        last_body, last_url, row, events = _last
        if url == last_url and (body is last_body or body == last_body):
            return dict(row), [dict(e) for e in events]
    row, events = ORIGINAL_PARSE(body, url)
    _last = (body, url, row, events)
    return dict(row), [dict(e) for e in events]


@contextmanager
def parse_once():
    """Use parse_listing_once for granular_parse.parse_listing inside the block."""
    global _last
    previous = granular_parse.parse_listing
    granular_parse.parse_listing = parse_listing_once
    try:
        yield
    finally:
        granular_parse.parse_listing = previous
        _last = None
