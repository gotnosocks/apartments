# Optional remote Chelsea scrape

`models/modal_scrape.py` can resume the uploaded Chelsea archive on Modal CPU. A ten-request cloud smoke run completed with ten HTTP 200 responses on September 8, 2026. The laptop performs control actions only.

First create a named Modal secret from the existing local `.env`:

```sh
.venv/bin/python models/modal_scrape.py setup-secret
```

This sends only `OXYLABS_USERNAME` (or its `OXYLABS_USER` alias) and `OXYLABS_PASSWORD` to the named `oxylabs` secret. It does not print values or upload `.env`. Existing secrets are not silently replaced; use the Modal dashboard for deliberate credential changes.

When ready to spend provider credits on a bounded run:

```sh
.venv/bin/modal run models/modal_scrape.py --snapshot chelsea-20260908 --workspace chelsea-resume --max-requests 100 --concurrency 10 --api-rps 2
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


## Continue a backfill in bounded cloud batches

```sh
.venv/bin/modal run --detach models/modal_scrape.py --action finish --workspace chelsea-resume --batch-size 750 --total-budget 30000 --concurrency 10 --api-rps 2
```

A small CPU controller invokes one crawl worker at a time. It stops on provider
failures, lack of progress, a drained scoped queue, the overall scheduling budget,
or its 24-hour limit. A worker that reaches its time limit after making progress
can continue in the next batch after committing its state. The scheduling budget
is conservative across batches and is not an exact provider dollar cap. The
controller uses 0.125 CPU and 256 MiB, about $0.008/hour at current listed rates;
workers keep the bounds described above. No GPU or browser service is involved.

Progress is stored in the Modal Dict `chelsea-backfill-runs`. The key
`latest:chelsea-resume` identifies the current report. The report includes batch
results and scoped queue counts. `queue_drained` means discovered work was handled;
it is not proof of exhaustive historical coverage. Run the coverage audit before
claiming completion.

Parser completeness failures remain pending and do not stop unrelated work. Their
retries back off after repeated failures; provider/authentication/challenge errors
still pause the crawl. The expanded inventory instructions wait for the requested
tab and actual detail rows before the existing count checks accept a capture.

Cloud batches default to 10 concurrent requests and 2 API submissions per second.
Scraper output is streamed into Modal logs and retained in each batch log on the Volume.
Once crawling starts, Scrapy normally prints statistics every minute; scope reconstruction
prints progress every 100 archived snapshots. These messages do not themselves prove
inventory completeness: final coverage must check current inventory outcomes and detail URLs.

Backfill requests prioritize unavailable inventories before listing details so a growing
detail queue cannot postpone historical discovery indefinitely. Lean runs retain their
existing ordering. `coverage_gaps` is the historical error-event count;
`current_coverage_gaps` counts URLs whose latest observation still has an error.
Neither count substitutes for the final scoped inventory/detail coverage audit.

For a safe update, set `stop-after-batch:chelsea-resume` to `True` in the
`chelsea-backfill-runs` Modal Dict, and wait for `stopped_at_batch_boundary`
and the writer lock to disappear. Clear the flag before starting a replacement.
Do not suspend the controller process: Modal can interpret lost heartbeats as
failure and cancel its worker before a commit finishes.
