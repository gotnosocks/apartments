# Remote archive processing

**Hosting update (September 16, 2026):** thelio now owns the primary archive and
review ledger. The former Modal volume is a frozen backup. These legacy cloud
commands do not automatically see new thelio observations or human corrections;
use thelio for archive processing, or explicitly upload current inputs for a new
cloud run. See [the hosting runbook](../operations/thelio.md).

Use Modal for archive import, the building coverage audit, model preparation, and
posterior fitting. The laptop transfers files and displays downloaded results.
Do not run a full archive audit or model preparation locally on the M1.

```sh
cd ~/code/apartments
uv sync --extra modal
.venv/bin/modal run models/modal_archive.py --action upload --snapshot chelsea-20260908
.venv/bin/modal run --detach models/modal_archive.py --action prepare --snapshot chelsea-20260908
.venv/bin/modal run models/modal_archive.py --action download --snapshot chelsea-20260908
```

The upload takes a consistent SQLite backup on disk while holding the scraper's
writer lock. Allow free disk space for one SQLite copy. It uploads that copy and
the derived DuckDB file individually, then uploads compressed bodies in batches
of at most 128 files or 16 MiB (an individual larger file streams separately).
It never loads the extracted archive into laptop memory. Only explicitly selected
data and source paths are uploaded; the project `.env` and logs are excluded.
The temporary SQLite backup is removed after its successful upload.

Uploads resume using ignored ledgers in `data/modal-upload/`. Repeat the command
with the same snapshot ID after a network interruption. Keep the local archive
unchanged until that upload completes; use a new snapshot ID for later data.
Do not remove the remote Volume while retaining its local upload ledgers.
An uploaded `complete.json` marker prevents processing a partial transfer.

Data persists in the `chelsea-archive` Modal Volume. Snapshot databases live under
`/snapshots/<id>/`, and immutable compressed bodies are shared under `/bodies`.
Preparation imports missing captures, streams one building record at a time for
the audit, and writes `prepared/training_data.parquet`, `metadata.json`, and
`buildings.jsonl`. Import failures prevent publishing a prepared result. Repeating
a successful preparation returns its saved result. Use a new snapshot for a
new preparation version. Run one writer at a time against a snapshot; the local
archive and local browser remain separate from this cloud copy.

The metadata records training-file SHA-256, imported counts, queue states,
coverage, and building totals. A completed preparation is not a completed
historical backfill. Source unit labels are not verified physical unit identities.

See [Modal fitting](../model/modal.md) for fitting directly from the Volume.
Use [remote scraping](modal-scraping.md) for bounded collection in a separate cloud
workspace. The initial snapshot remains immutable for reproducible analysis.
Downloading the prepared table is optional; it is useful for inspection, not
required for the cloud fit. Keep fitted results in their own output directory
until diagnostics have been reviewed.

## Cost controls

Preparation uses CPU only: 2 cores, 8 GiB RAM, at most one container, a one-hour
timeout, and no automatic retries. At [Modal's September 8, 2026 prices](https://modal.com/pricing),
that allocation is approximately $0.16 per running worker-hour. Builds, storage,
and applicable transfer charges are additional. No endpoint or scheduled worker
is deployed; no GPU is allocated for uploading, importing, or preparing data.
The Volume persists after workers stop and is subject to storage pricing.
Use `modal run --detach` for long processing jobs that should survive a laptop
disconnect; the same worker timeout still applies. The final files persist even
if the submitting terminal can no longer receive the result.

Model fitting defaults to CPU as well. A T4 is opt-in: the initial small benchmark
was slower on T4 than the M1 CPU, so a GPU is not presumed to save money. Use bounded
smoke runs and inspect diagnostics before spending on a full posterior fit.
