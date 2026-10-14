"""Skip scope enrolment for links the archive already holds as they would be written.

scope.expand passes every building root in scope to scope._enroll on every page, so each ad
page in Midtown West (Oct 2026) re-enrolled about 1,370 roots. Each one cost an INSERT OR IGNORE,
an upsert and two URL canonicalisations, about 0.18 s per ad on the crawler's main thread and
40% of its parse time. The crawl fetched 105 to 117 pages a minute against 128 allowed, and a
restart replayed captures at about 11 a second.

enroll_known_first reads, in one query, which links already have their scope row and a frontier
row with the kind and listing key store._enqueue would write. For those links _enroll changes
nothing: INSERT OR IGNORE leaves the scope row, and the upsert with no lastmod keeps the state,
sets the same kind and listing key and keeps the lastmod. It passes the other links and the new
building roots on to scope._enroll in their original order. A link stays on the full path when
canonicalisation changes it, or when another link in the batch canonicalises to it, so aliases
and their upserts happen as before.

scope.py and store.py are hashed by saved datasets, so the change lives here. cli applies it with
known_links() for crawl commands.
"""

import json
from contextlib import contextmanager

from . import scope
from .extract import canonical_url, is_gallery_url
from .listing_identity import listing_key

ORIGINAL_ENROLL = scope._enroll
_FORMS = {}
# About 40 MB of forms; a crawl of 200k links would otherwise hold about 85 MB.
FORMS_LIMIT = 100_000


def _form(url):
    """(kind, canonical form, listing key) for url; all three depend on url alone."""
    form = _FORMS.get(url)
    if form is None:
        if len(_FORMS) >= FORMS_LIMIT:
            _FORMS.clear()
        canonical = canonical_url(url) or url
        form = _FORMS[url] = (scope.kind_for(url), canonical, listing_key(canonical))
    return form


def _unchanged(store, generation, urls):
    """The links in urls for which _enroll would change no row."""
    plain, aliased = [], set()
    for url in urls:
        kind, canonical, key = _form(url)
        if not kind:
            continue
        if canonical != url or is_gallery_url(canonical):
            aliased.add(canonical)
        else:
            plain.append([url, kind, key])
    if not plain:
        return set()
    # CROSS JOIN keeps json_each as the outer loop. Left to itself, the planner walks the whole
    # generation's frontier and took 128 s per call on the Midtown West archive.
    rows = store.db.execute(
        """SELECT f.url FROM json_each(?) j
            CROSS JOIN frontier f ON f.generation=? AND f.url=json_extract(j.value,'$[0]')
            JOIN scope_urls s ON s.generation=f.generation AND s.url=f.url
            WHERE f.kind=json_extract(j.value,'$[1]')
            AND f.listing_key IS json_extract(j.value,'$[2]')""",
        (json.dumps(plain), generation),
    )
    return {r[0] for r in rows} - aliased


def enroll_known_first(store, generation, urls, roots=()):
    roots = list(roots)
    if roots:
        known = {
            r[0]
            for r in store.db.execute(
                "SELECT url FROM scope_buildings WHERE generation=?", (generation,)
            )
        }
        roots = [r for r in roots if r not in known]
    unchanged = _unchanged(store, generation, urls)
    ORIGINAL_ENROLL(
        store,
        generation,
        {u: reason for u, reason in urls.items() if u not in unchanged},
        roots,
    )


@contextmanager
def known_links():
    """Use enroll_known_first for scope._enroll inside the block."""
    previous = scope._enroll
    scope._enroll = enroll_known_first
    try:
        yield
    finally:
        scope._enroll = previous
