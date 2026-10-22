# Converter notes (crawl ACTIVE ads -> site candidates)

From the Unified crawl backend plan thread after reading master, 2026-10-10. To verify against the code before building.

1. Namespace capture ids per crawl, e.g. `crawl:<crawl name>:<snapshot id>`. `candidate_snapshot.build_snapshot` rows use the crawl's integer snapshot id as `capture_id`, and those ids repeat across crawls. `site/captures.py:90` skips a whole capture folder if any `capture:<id>` is already a dataset audit id.
2. Carry each row's `body_sha256` and keep a readable `*/archive/archive.sqlite3` (or equivalent), so `site/ad_dates.py` can date the ads. `build_snapshot` rows have no page hash today.
3. `captures.rows` skips units the fitted dataset already holds as current (`captures.py:351-362`), so a newer sighting never replaces an older dataset row. The today's-date cutoff change should also let the newer sighting win there.
4. Pulls and converter output reach the site only at a full site build (`ops/autoselect-publish.sh` step 3), so each pull or converter run needs a site build after it.

# Lean-write PR (Ben 2026-10-10 20:01Z: "the best part is no part")

Assumptions from the Unified crawl backend plan, step 0. Verify the PR matches these:
1. The write-time strip produces exactly what compact writes today. In provider_capture.results[], content is replaced by content_sha256 = body_hash, appended last, and only when the content hashes to the body; otherwise the row is kept as is. Use json.dumps defaults, so the existing compact tests cover the new rows.
2. It lives in a new module applied from cli.run_crawler, the same way structure_first.claim_order is. crawler.py, store.py, oxylabs.py and capture.py are hash-locked, so the change ships in a new frozen runtime.
3. A finished crawl DB is frozen where it lies and becomes the snapshot, with no copy and no compaction. compact stays only for DBs written before the change.
Current pulls (candidate_refresh) already write lean, so this only affects ArchiveSpider.
