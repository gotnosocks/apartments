# Thelio hosting and archive migration

The primary home for this project is `/home/ben/code/apartments` on SSH host `thelio`.
Python 3.12, jj 0.45.1, the archive/review tools and the tested CPU modeling packages
are installed in a project virtual environment. Use `.venv/bin/python` and
`.venv/bin/streeteasy-archive`; do not use `uv run` to recreate a tested environment.

## Authority and paths

**Cutover completed September 16, 2026 at 21:19 EDT.** All 36 bundles and
126,669 files (337,514,582,167 bytes) passed verification. SQLite quick_check
returned `ok`, and all 11 Parquet table counts matched the saved reports. See
[the cutover report](thelio-cutover-20260916.json). The authoritative marker is
`/data1/apartments/migration/cutover-ready.json` on thelio.

The review and raw archive services are active. Direct browser access over Tailscale is available at
[Review](http://thelio.tail3983e0.ts.net:8766/) and
[Archive](http://thelio.tail3983e0.ts.net:8765/). Both localhost URLs also use an
automatically reconnecting SSH tunnel from this Mac. Review submissions are
enabled; no artificial review or correction records were added during testing.
The old Modal review and migration deployments are stopped; the archive volume
is retained as a frozen backup.

| Purpose | Thelio path |
| --- | --- |
| Archive volume mirror | `/data1/apartments/archive` |
| Live crawl | `/data1/apartments/archive/crawls/chelsea-resume` |
| Frozen source snapshots | `/data1/apartments/archive/snapshots` |
| Content-addressed page bodies | `/data1/apartments/archive/bodies` |
| Granular tables | `/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-units` |
| Human review/overlay ledger | `/data1/apartments/archive/reviews/chelsea-granular-20260917-canonical-units` |
| Transfer state and checksums | `/data1/apartments/migration` |
| Available second-disk backup location | `/data2/apartments-backup` |

The frozen Modal inventory contains 126,670 files and 337,514,614,935 bytes
(337.5 decimal GB / 314.3 GiB). This is the sum of logical file sizes, not
a count of unique scraped content or measured physical disk allocation.
The live SQLite database and latest frozen SQLite snapshot each occupy
158,946,983,936 logical bytes (148.0 GiB); matching sizes alone do not prove
identical content. Saved compressed page bodies total 11,501,574,344 bytes
(10.7 GiB), and granular tables total 321,406,802 bytes (306.5 MiB).
The metadata audit reports zero free-list pages in all three SQLite files;
this does not measure partly filled pages or duplicate payload content. See
[the size audit](thelio-size-audit.json) for byte and page counts.

It includes the live crawl, older snapshots, saved page bodies, tables, fits,
and review state. The transfer does not collapse observations or change source
records. Legacy absolute links to the same Modal volume become relative links
within the destination archive. This is recorded in the transfer manifests.

Modal collection/processing deployments were stopped and cloud review mutations
were disabled before inventory. The existing two-hour crawl monitor was already
paused. Keep it paused: its old instructions target Modal.

The existing Modal volume remains a frozen backup after cutover. It is not
another active writer. No automatic second-disk backup is configured yet.
The project's ignored `data/archive` symlink points at the live crawl directory above.

## September 16 transfer repair

At 19:08 EDT the initial export stopped because read-only SQLite inspection had
changed `snapshots/chelsea-20260908/archive.sqlite3-shm`. This is SQLite's
regenerable coordination index. The repair verified that the database and WAL
file sizes and modification times still matched the frozen plan, and every
associated WAL was empty. It excluded this one 32,768-byte sidecar from the
unpublished bundle, retaining all source files on Modal. Plan revision 2 therefore
transfers **126,669 files / 337,514,582,167 bytes**. The prior plan and a repair audit
are retained in the migration directory. Completed bundles are reused unchanged.

New plans omit SQLite shared-memory indexes while preserving WAL files. Export
failures no longer cancel unrelated packs, and large-file reads log progress every
30 seconds. Thelio revalidates its existing part checkpoints when resumed.

## Transfer

`models/modal_migrate.py` plans and exports the frozen volume. Two CPU workers
stream files through SHA-256 and zstd; each completed bundle has an independently
committed checksum manifest and ready marker. The deployed controller's `.spawn()`
call persists independently of this laptop. Source file size and modification
checks reject changes after the freeze. No GPU is used.

Thelio's receiver downloads directly from Modal, verifies compressed bundles and
extracted files, and saves resumable per-bundle checkpoints:

```sh
cd ~/code/apartments
MODAL_CONFIG_PATH=~/.config/apartments/modal-migration.toml \
  .venv/bin/python -m apartments.archive_receive
```

The owner authenticated Modal directly on thelio on September 16; the service uses
`~/.config/apartments/modal-migration.toml`, with directory mode 0700 and file mode
0600. No laptop credentials were copied. Retain this owner-created login unless
the owner chooses to revoke it.

For future setups, a temporary copy of the owner's Modal credentials requires explicit authorization;
it must have mode 0600 and must be removed after the transfer is verified. Credentials
must not be logged, committed, or included in the archive. Alternatively authenticate
the Modal SDK directly on thelio and update the service's config path.

Inspect:

```sh
systemctl --user status apartments-migration
journalctl --user -u apartments-migration -n 30 --no-pager
cat /data1/apartments/migration/progress.json
systemctl --user status apartments-migration-finalize
journalctl --user -u apartments-migration-finalize -n 30 --no-pager
```

An independent streaming verifier is also available; it reads the full archive and
should not be run redundantly when all receiver checksum checks already passed:

```sh
.venv/bin/python -m apartments.archive_verify \
  --root /data1/apartments/archive \
  --manifest /data1/apartments/migration/all-files.jsonl \
  --summary /data1/apartments/migration/verification.json \
  --check-unexpected
```

The receiver is enabled at boot and skips once the cutover marker exists. It
resumes verified bundles if thelio reboots before completion. Download and final
validation run independently of the laptop; the laptop only supplies browser access.

Successful completion of `apartments-migration.service` triggers
`apartments-migration-finalize.service`. It reconciles manifest/file/byte counts,
checks the canonical SQLite database read-only, and compares Parquet row counts
with the saved dataset completion report. It publishes the cutover marker only
after validation, then starts the review and archive services. A failure leaves
the services gated and is visible in the finalize service journal. No GPU is used.

A pre-cutover read-only review smoke test on the transferred tables returned HTTP
200 and 96,783 rental observations across 1,217 building labels. These are source
observation counts, not distinct physical units. The transferred review ledger
contains no saved corrections or review decisions.

## Persistent services and access

User systemd lingering is enabled for `ben`, allowing services to run after logout
and start at boot. Unit files are in `deploy/thelio/`; review/browser units require
both the `/data1` mount and the cutover marker. They bind to loopback and the explicit Tailscale IPv4 address, with
memory limits of 3 GiB and 2 GiB respectively. They are enabled and were started after validation.

```sh
systemctl --user status apartments-review apartments-archive
journalctl --user -u apartments-review -n 30 --no-pager
```

The installed Mac LaunchAgent `com.ben.apartments-tunnel` forwards ports 8766
and 8765 and reconnects when the network returns. Its definition is in
`deploy/thelio/com.ben.apartments-tunnel.plist`, installed at
`~/Library/LaunchAgents/com.ben.apartments-tunnel.plist`. Logs are in
`data/logs/thelio-tunnel.log`. The old local Modal-backed frontend was stopped.

For a different client, or if the LaunchAgent is not loaded, open a tunnel:

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:8766:127.0.0.1:8766 \
  -L 127.0.0.1:8765:127.0.0.1:8765 thelio
```

The review app remains at `http://localhost:8766/`; raw archive browsing uses
`http://localhost:8765/`. Closing the tunnel disconnects browsing, not server work.
No public web endpoint or new public inbound port is required.

The source snapshot and live SQLite file have different SHA-256 hashes despite
identical sizes; both have been preserved. Do not deduplicate them by size.

## Direct Tailscale access

The Mac and thelio share `tail3983e0.ts.net`. Open these links from a connected
Tailscale device, including away from home:

- Review: http://thelio.tail3983e0.ts.net:8766/
- Raw archive: http://thelio.tail3983e0.ts.net:8765/

The services listen on `100.80.84.126` plus `127.0.0.1`, with no wildcard or LAN
listener. Network access follows the tailnet's access rules; people/devices with
access to port 8766 can review and correct the data. Both apps accept only explicit
configured hostnames. Review POSTs still require a session CSRF token and reject
cross-origin requests. Transport encryption is supplied by Tailscale; these links
use HTTP inside that network and do not require HTTPS certificate setup. See
[Tailscale Serve examples](https://tailscale.com/docs/reference/examples/serve)
for the optional proxy approach; this installation uses direct app listeners,
without changing Tailscale operator permissions or enabling Funnel.

`REVIEW_LISTEN` and `ARCHIVE_LISTEN` contain the space-separated Waitress listeners.
`REVIEW_ALLOWED_HOSTS` and `ARCHIVE_ALLOWED_HOSTS` contain comma-separated exact
hostnames. The two user systemd units set them. Without those settings, the apps
still default to loopback only. If the node's Tailscale IP changes on re-enrollment,
update both units and restart the services. `Restart=on-failure` lets them retry
if the Tailscale interface is not ready at boot. Localhost SSH access remains
available as an alternative.


### Mobile model report

The review service serves the self-contained local model report at
`http://thelio.tail3983e0.ts.net:8766/model-report`. A phone must be connected to
the existing Tailscale network. `REVIEW_MODEL_REPORT` selects exactly one HTML
artifact; it does not expose the model directory or provide a file browser.
The existing loopback/Tailscale listeners and allowed-host checks apply. This
route does not change the review dataset or annotations. Change the environment
path and restart the service when publishing a later report.
