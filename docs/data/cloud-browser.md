# Browse the authoritative cloud archive locally

The local archive browser can read the authoritative Modal archive without downloading or opening the local archive database:

```sh
.venv/bin/streeteasy-archive serve-cloud --port 8765
```

Open `http://127.0.0.1:8765/`. The gateway binds only to loopback. It invokes the deployed `chelsea-archive-browser` / `read` function using the existing Modal SDK login. There is no public HTTP endpoint, proxy token, account cookie forwarding, or user-selectable remote destination. Only GET requests for the root page, static assets and archive API are accepted. The Modal read function selects the active archive through `/archive/authoritative.json`.

The UI labels the cloud archive authoritative and the local archive a backup. It shows the last cloud commit reported by the read function. Cloud summaries read a standalone browser checkpoint published between bounded crawl runs. The database is replaced atomically after its bulk SQLite copy is closed; readers never open the active writer’s cross-container WAL. A running crawl’s new captures become visible after checkpoint publication and Volume commit. The local `serve` command remains available explicitly for inspecting the backup and retains its original polling cadence.

Cloud automatic refresh runs every 30 seconds while the tab is visible and the user has interacted within two minutes. Hidden or inactive tabs stop automatic cloud queries; explicit navigation, filters and Refresh still work. This limits idle compute. Requests and archived-data processing run remotely; the local gateway merely returns bounded response bytes. It rejects responses larger than 32 MiB; the remote function should apply the same limit before transfer.

If the gateway reports cloud unavailable, check the existing Modal login and that the named read function is deployed. The browser receives a generic error rather than exception text that might reveal configuration details. Starting this gateway never opens `ArchiveStore`, creates a local archive directory, starts scraping, or imports data.


When the local archive contains `CLOUD_AUTHORITATIVE.json`, CLI writer commands refuse to modify that backup and direct you to cloud resume. The read-only browser remains available; `serve-cloud` displays the authoritative checkpoint. Removing the marker is not part of normal operation.
