"""Claim building-directory and building pages before units and advertisements.

ArchiveStore.claim takes advertisements first, then unit inventories, then building and
directory pages. In a neighbourhood crawl each building page adds dozens of units and
advertisements that jump ahead of the directory, so the building census finishes last and
the crawl's size stays unknown until near the end (East Village, Oct 2026). Ben, Oct 9
2026: "pull all the buildings first and then traverse the apartments and listings".

install() swaps in claim_structure_first, which is ArchiveStore.claim with one leading sort
key: directory pages, then building pages, then everything else in the original order.
The candidate filter, policy exclusions and capture reuse are unchanged, so only the order
of requests changes, not which pages are fetched. store.py is hashed by saved datasets,
so the change lives here; a runner opts in by calling install() before cli.main.
"""

import time

from .store import ArchiveStore

STRUCTURE_RANK = "CASE f.kind WHEN 'directory' THEN 0 WHEN 'building' THEN 1 ELSE 2 END"


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
            row = self.db.execute(
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
                    generation,
                    now,
                    now,
                    int(scoped),
                    url_prefix,
                    url_prefix,
                    url_prefix,
                    url_prefix,
                    url_prefix,
                    url_prefix,
                    int(prefer_inventory),
                    int(prefer_units),
                ),
            ).fetchone()
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


def install():
    ArchiveStore.claim = claim_structure_first
