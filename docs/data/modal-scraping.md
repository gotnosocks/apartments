# Optional remote Chelsea scrape

`models/modal_scrape.py` can resume the uploaded Chelsea archive on Modal CPU. It is opt-in and has not been used to start a paid scrape. The laptop performs control actions only.

First create a named Modal secret from the existing local `.env`:

```sh
.venv/bin/python models/modal_scrape.py setup-secret
```

This sends only `OXYLABS_USERNAME` (or its `OXYLABS_USER` alias) and `OXYLABS_PASSWORD` to the named `chelsea-oxylabs` secret. It does not print values or upload `.env`. Existing secrets are not silently replaced; use the Modal dashboard for deliberate credential changes.

When ready to spend provider credits on a bounded run:

```sh
.venv/bin/modal run models/modal_scrape.py --snapshot chelsea-20260908 --workspace chelsea-resume --max-requests 100 --concurrency 5 --api-rps 1
```

The default is 100 scheduled requests, five concurrent jobs and one submission per second. Zero/unlimited budgets are rejected. Provider retries and API billing rules mean the request budget is not an exact dollar cap. No JS-rendering flag is added; the existing transport handles historical inventory needs. The crawler retains Chelsea plus West Chelsea scope excluding Hudson Yards, unavailable-unit discovery, existing frontier progress and cooldown handling.

The first run bulk-copies the closed, WAL-free uploaded snapshot SQLite database into `/crawls/chelsea-resume/` on Volume `chelsea-archive`. It shares content-addressed body files at `/bodies`, without changing existing bodies or the source snapshot database. Subsequent runs with that workspace resume its own queue. A workspace cannot be silently repointed to another snapshot. An incomplete clone requires inspection or a new workspace ID.

One CPU-only worker uses two cores and 8 GiB, a one-hour hard timeout and no Modal retries. A subprocess deadline at 55 minutes leaves time to checkpoint and commit its output. A new process for each run avoids reusing a stopped Twisted reactor. Normal completion commits the SQLite archive and run log, then releases the distributed lock. No browser checkpoint or automatic browsing copy is created. Exit code 3 generally denotes the crawler's pause/cooldown state; examine the returned state and log before resuming.

A Modal Dict atomic `put(..., skip_if_exists=True)` enforces one writer across app invocations. There is no automatic expiry or stale-lock takeover. If a worker crashes, times out, or cannot commit, the lock remains:

```sh
.venv/bin/python models/modal_scrape.py show-lock
# Stop the associated worker and confirm no remote scrape worker is active first.
.venv/bin/python models/modal_scrape.py clear-lock --owner OWNER_FROM_SHOW_LOCK
```

Manual clearing while a writer is active is unsafe. Do not run separate tools that write the same remote crawl workspace outside this lock.

New captures and logs stay in `/crawls/{workspace}/`. **The local archive browser does not automatically display remote scrape progress or data.** Remote results are also not automatically imported into the prepared model snapshot. Publish a new explicit snapshot using the commands below; the original preparation provenance and local archive are preserved.


## Publish remote captures for analysis

After a bounded crawl run has exited and committed, publish a new snapshot entirely within Modal:

```sh
.venv/bin/modal run models/modal_scrape.py --action publish-snapshot --workspace chelsea-resume --new-snapshot chelsea-20260908-expanded
.venv/bin/modal run models/modal_archive.py --action prepare --snapshot chelsea-20260908-expanded
.venv/bin/modal run models/modal_fit.py --snapshot chelsea-20260908-expanded
```

Publication acquires the same distributed writer lock as scraping. It copies the workspace SQLite database to a **new** `/snapshots/{id}/` directory, records parent snapshot and last-run provenance, and writes `complete.json` last. Existing snapshot IDs are rejected. No data is downloaded to or processed on the laptop. The preparation worker resolves shared body files itself.

By default, preparation builds a fresh derived DuckDB database. Optional `--seed-database` copies the original snapshot's derived database to reuse its completed imports; this requires the original preparation's metadata and no active WAL. It does not copy the old prepared model table or overwrite the original database. Do not rerun preparation against that original snapshot concurrently with seeded publication.

A completed bounded run can still have pending URLs; publishing preserves that state and is not a claim that Chelsea collection is complete. A failed publication leaves no usable readiness marker until all copies finish, and retains its writer lock for inspection. Use a new snapshot ID after investigating an incomplete destination.


Cloud copies use bounded filesystem copying after a stopped writer’s WAL is checkpointed and verified empty. This avoids slow per-page SQLite backup writes on the Volume. Immutable uploaded sources are not modified; only their copies are converted to standalone DELETE journal mode. A busy checkpoint or nonempty WAL blocks publication instead of risking a partial database.
