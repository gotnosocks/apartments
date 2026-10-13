"""Claim building-directory and building pages before units and advertisements.

ArchiveStore.claim takes advertisements first, then unit inventories, then building and
directory pages. In a neighbourhood crawl each building page adds dozens of units and
advertisements that jump ahead of the directory, so the building census finishes last and
the crawl's size stays unknown until near the end (East Village, Oct 2026). Ben, Oct 9
2026: "pull all the buildings first and then traverse the apartments and listings".

claim_structure_first is ArchiveStore.claim with one leading sort key: directory pages,
then building pages, then everything else in the original order. It is the default for
backfill, update and resume (Ben, Oct 9 2026: "make that the default for future crawls");
`--claim-order original` keeps store.py's order. cli.run_crawler applies it with
claim_order() for the crawl's duration only.
The candidate filter, policy exclusions and capture reuse are unchanged. Two claim-time
exclusions are judged on what has been discovered so far, and are permanent: an ad with no
unit membership yet (missing_canonical_unit_association), and a unit whose route was first
enrolled as an inventory probe from a pre-cutoff ad (probe_source_before_min_listing_id;
scope_urls keeps the first reason, apart from GraphQL unit paths moving to a newer ad). Claiming buildings first enrolls units from their
building pages before those rules run, so some ads and re-let units that the original
order excluded early are fetched: the same rules, more coverage, somewhat more requests.
store.py is hashed by saved datasets, so the change lives here.
"""

import time
from contextlib import contextmanager

from .store import ArchiveStore

ORDERS = ("structure-first", "original")
STRUCTURE_RANK = "CASE f.kind WHEN 'directory' THEN 0 WHEN 'building' THEN 1 ELSE 2 END"


FILTER = """f.generation=? AND f.state='pending' AND f.next_attempt<=?
                AND (f.listing_key IS NULL OR NOT EXISTS(SELECT 1 FROM frontier busy
                    WHERE busy.generation=f.generation AND busy.listing_key=f.listing_key AND busy.state='inflight'))
                AND (g.cooldown IS NULL OR g.cooldown<=?)
                AND (?=0 OR EXISTS(SELECT 1 FROM scope_urls scope WHERE scope.generation=f.generation AND scope.url=f.url))
                AND (? IS NULL OR f.url=? OR substr(f.url,1,length(?)+1)=? || '/' OR substr(f.url,1,length(?)+1)=? || '?')"""

# store.py's priority column, by kind; any other kind is 2.
PRIORITY = {"listing": 0, "sitemap": 1, "search": 3}
KINDS = ("directory", "building", "inventory", "listing", "sitemap", "search")


def _filter_args(generation, now, scoped, url_prefix):
    return (generation, now, now, int(scoped), *(url_prefix,) * 6)


def _sorted_candidate(
    self, generation, now, url_prefix, scoped, prefer_inventory, prefer_units
):
    """The next candidate by one sort over the whole pending queue."""
    return self.db.execute(
        """SELECT f.* FROM frontier f JOIN generations g ON g.id=f.generation
                WHERE f.generation=? AND f.state='pending' AND f.next_attempt<=?
                AND (f.listing_key IS NULL OR NOT EXISTS(SELECT 1 FROM frontier busy
                    WHERE busy.generation=f.generation AND busy.listing_key=f.listing_key AND busy.state='inflight'))
                AND (g.cooldown IS NULL OR g.cooldown<=?)
                AND (?=0 OR EXISTS(SELECT 1 FROM scope_urls scope WHERE scope.generation=f.generation AND scope.url=f.url))
                AND (? IS NULL OR f.url=? OR substr(f.url,1,length(?)+1)=? || '/' OR substr(f.url,1,length(?)+1)=? || '?')
                ORDER BY """
        + STRUCTURE_RANK
        + """,
                         CASE WHEN ? THEN CASE WHEN f.kind='inventory' THEN 0 ELSE f.priority + 1 END
                           ELSE f.priority END,
                         CASE WHEN ? AND f.kind='listing' AND f.listing_key IS NULL THEN 0 ELSE 1 END,
                         f.rowid LIMIT 1""",
        (
            *_filter_args(generation, now, scoped, url_prefix),
            int(prefer_inventory),
            int(prefer_units),
        ),
    ).fetchone()


def _buckets(prefer_inventory, prefer_units):
    """(kind, listing_key IS NULL or None for either) in the order _sorted_candidate ranks them."""

    def rank(kind):
        structure = {"directory": 0, "building": 1}.get(kind, 2)
        priority = PRIORITY.get(kind, 2)
        if prefer_inventory:
            priority = 0 if kind == "inventory" else priority + 1
        return structure, priority

    for kind in sorted(KINDS, key=rank):
        if kind == "listing" and prefer_units:
            yield kind, 1
            yield kind, 0
        else:
            yield kind, None


def _claim_indexes(self):
    """Create the kind indexes the claim reads.

    IF NOT EXISTS runs on every claim, since a rolled-back claim transaction also drops an
    index it created.
    """
    self.db.execute(
        "CREATE INDEX IF NOT EXISTS frontier_claim_kind ON frontier(generation,state,kind)"
    )
    self.db.execute(
        "CREATE INDEX IF NOT EXISTS frontier_claim_unit"
        " ON frontier(generation,state,kind,(listing_key IS NULL))"
    )


def _indexed_candidate(
    self, generation, now, url_prefix, scoped, prefer_inventory, prefer_units
):
    """The same candidate as _sorted_candidate, read kind by kind from an index.

    The sort reads every pending row. With 175,000 rows queued in Midtown West (Oct 13
    2026) it took about 0.35 s per call, and it held the crawl to about 75 claims a
    minute on one core. Each kind in KINDS has a rank of its own, so this walks each
    kind's rows in rowid order and takes the first one to pass the filter. While a
    pending row has some other kind, the claim falls back to the sort.
    """
    if _other_kinds_pending(self, generation):
        return _sorted_candidate(
            self, generation, now, url_prefix, scoped, prefer_inventory, prefer_units
        )
    args = _filter_args(generation, now, scoped, url_prefix)
    for kind, keyless in _buckets(prefer_inventory, prefer_units):
        if keyless is None:
            index, extra, more = "frontier_claim_kind", "", ()
        else:
            index, extra, more = (
                "frontier_claim_unit",
                " AND (f.listing_key IS NULL)=?",
                (keyless,),
            )
        row = self.db.execute(
            f"""SELECT f.* FROM frontier f INDEXED BY {index}
                JOIN generations g ON g.id=f.generation
                WHERE {FILTER} AND f.kind=?{extra} ORDER BY f.rowid LIMIT 1""",
            (*args, kind, *more),
        ).fetchone()
        if row:
            return row
    return None


def _other_kinds_pending(self, generation):
    """Whether a pending row has a NULL kind or one outside KINDS.

    Such a row ties with others in the sort, so the claim takes the sort instead. Each
    probe reads one end of a gap between known kinds in frontier_claim_kind.
    """
    _claim_indexes(self)
    known = sorted(KINDS)
    gaps = ["kind IS NULL", "kind<?"]
    params = [known[0]]
    for low, high in zip(known, known[1:]):
        gaps.append("kind>? AND kind<?")
        params += [low, high]
    gaps.append("kind>?")
    params.append(known[-1])
    probes = " UNION ALL ".join(
        "SELECT * FROM (SELECT 1 FROM frontier INDEXED BY frontier_claim_kind"
        f" WHERE generation=? AND state='pending' AND {gap} LIMIT 1)"
        for gap in gaps
    )
    args = []
    i = 0
    for gap in gaps:
        args.append(generation)
        n = gap.count("?")
        args += params[i : i + n]
        i += n
    return self.db.execute(probes, args).fetchone() is not None


def claim_structure_first(
    self,
    generation,
    now=None,
    url_prefix=None,
    scoped=False,
    prefer_inventory=False,
    prefer_units=False,
):
    now = time.time() if now is None else now
    with self._tx():
        while True:
            row = _indexed_candidate(
                self,
                generation,
                now,
                url_prefix,
                scoped,
                prefer_inventory,
                prefer_units,
            )
            if row:
                from .collection_policy import (
                    exclude,
                    exclusion_reason,
                    reuse_unit_capture,
                )

                reason = exclusion_reason(self, generation, row["url"])
                if reason:
                    exclude(self, generation, row["url"], reason)
                    continue
                if reuse_unit_capture(self, generation, row):
                    continue
            if row and self._reuse_listing_capture(generation, row):
                continue
            if row:
                self.db.execute(
                    "UPDATE frontier SET state='inflight',attempts=attempts+1 WHERE generation=? AND url=?",
                    (generation, row["url"]),
                )
                self.db.execute(
                    "UPDATE generations SET status='active',cooldown=NULL WHERE id=?",
                    (generation,),
                )
                self.db.execute(
                    "INSERT INTO metadata VALUES('next_request',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(now + 5),),
                )
            return row


ORIGINAL_CLAIM = ArchiveStore.claim


@contextmanager
def claim_order(order):
    """Use the named claim order for ArchiveStore inside the block."""
    if order not in ORDERS:
        raise ValueError(f"claim order must be one of {ORDERS}")
    previous = ArchiveStore.claim
    ArchiveStore.claim = (
        claim_structure_first if order == "structure-first" else ORIGINAL_CLAIM
    )
    try:
        yield
    finally:
        ArchiveStore.claim = previous
