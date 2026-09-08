# Cloud archive authority

Modal Volume `chelsea-archive` is the active home of the archive. The initial
snapshot `chelsea-20260908` remains immutable. The working archive is
`/crawls/chelsea-resume`, selected by `/authoritative.json`. The original
`data/archive` on this laptop is a backup, not a second active crawler database.
Its `CLOUD_AUTHORITATIVE.json` marker prevents local crawler writes.

The browser remains at `http://localhost:8765`:

```sh
.venv/bin/streeteasy-archive serve-cloud --port 8765
```

This process does no archive queries locally. It forwards read-only requests
through the authenticated Modal SDK to `chelsea-archive-browser.read`. No public
HTTP endpoint, web password, or browser-exposed API credential is required.
The local gateway binds only to loopback and accepts no user-selected remote host.

The cloud function queries a committed SQLite checkpoint under `/browser`, with
shared archived bodies. Each bounded remote crawl refreshes that checkpoint only
after the crawler exits, using a SQLite backup and atomic file replacement. While
the next crawl is active, the browser displays the preceding committed data and
the cloud writer state. This avoids querying a changing WAL across containers.

The browser labels its cloud source and last checkpoint time. It refreshes every
30 seconds while visible and recently used; hidden/inactive tabs stop polling.
The read worker uses one CPU core, up to 2 GiB RAM, at most one container, no minimum
containers, and a ten-second scale-down window. It allocates no GPU.

Deployment and first activation, already handled during setup:

```sh
.venv/bin/modal run models/modal_cloud_browser.py --snapshot chelsea-20260908 --workspace chelsea-resume
.venv/bin/modal deploy models/modal_cloud_browser.py
```

See [remote scraping](modal-scraping.md) for bounded collection, credential setup,
and publishing snapshots, and [remote processing](modal-processing.md) for import
and preparation. Fits read prepared data directly from the Volume. Downloading
artifacts for local inspection is optional; no repeated full archive transfer is
needed. The cloud browser checkpoint is a derived copy and can be rebuilt from
the authoritative archive. The local backup is not automatically synchronized.
