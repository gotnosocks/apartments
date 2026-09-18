# Local scrape experiments

Run a single request from the apartments project using the existing `.env`
Oxylabs credentials. The probe does not open either archive database, launch a
crawler, discover more pages, or retry a failed API call. It leaves Modal running.

```sh
uv run --locked python -m streeteasy_archive.probe \
  https://streeteasy.com/building/one-high-line --mode sales
```

Use `--mode rentals` for rental inventory, `--mode sales` for sales inventory,
or `--mode html` for the initial unrendered page. Inventory modes use the same
request builder as the production scraper. Requests still run through Oxylabs:
local execution removes deployment overhead, not the provider's rendering time.

Each run creates a new ignored directory under `data/probes/`, containing the
request payload (without credentials), sanitized response envelope, page HTML,
extracted data, and timing/status metadata. Failures retain available evidence.
The response size is bounded, timeout defaults to 180 seconds, and output paths
cannot overwrite an existing experiment. These are diagnostic samples, not the
authoritative point-in-time archive.

To iterate on parsing without another request, reuse a saved body:

```sh
uv run --locked python -m streeteasy_archive.probe \
  https://streeteasy.com/building/one-high-line --mode sales \
  --replay data/probes/local-one-high-line-sales/body.html
```

Replay makes zero network calls and does not load credentials. Use a mode matching
the original capture. The original body stays unchanged and each replay saves its
own extraction and metadata. Keep bulk scraping, archive scans, and model fitting
on Modal.
