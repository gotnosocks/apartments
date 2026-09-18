# Bounded Chelsea rental pagination

`apartments.rental_discovery` follows the two configured Chelsea rental-search seeds through only the next links accepted by the offline parser. It uses the existing one-request Oxylabs HTML probe for every new capture. It does not request listing details, visit building directories, alter the archive, or claim complete inventory.

The global ceiling is mandatory for a new run. It counts **verified reused provider submissions plus every durable new request intent**, including an intent whose submission is uncertain after interruption. With the four existing preflight captures and `--max-requests 32`, at most 28 new attempts can occur. There are no retries and no concurrent requests. The Chelsea prefix is followed first, then West Chelsea; a low ceiling may therefore leave the second prefix unextended.

## Commands for review

Prepare a run using the verified four-page artifact, without making requests:

```sh
.venv/bin/python -m apartments.rental_discovery \
  --output data/probes/NEW-UNUSED-RENTAL-PAGINATION-RUN \
  --max-requests 32 \
  --preflight-bundle data/model/chelsea-current-search-four-page-audit-20260918-v2 \
  --replay-only
```

After reviewing that prepared run, continue its fixed protocol:

```sh
.venv/bin/python -m apartments.rental_discovery \
  --output data/probes/NEW-UNUSED-RENTAL-PAGINATION-RUN --resume
```

Replay an existing run without any network calls:

```sh
.venv/bin/python -m apartments.rental_discovery \
  --output data/probes/NEW-UNUSED-RENTAL-PAGINATION-RUN --resume --replay-only
```

Resume uses the original ceiling, timeout, implementation hashes, seeds, and copied sources. Supplying a different ceiling or a new preflight bundle fails. Changed implementation hashes require a separately reviewed new run. The ceiling has no default; 32 above is an explicit example based on the displayed 24+8-page hints, not an assumption of inventory completeness. Increasing the ceiling is not a resume operation.

Python entry point: `run(output, *, max_requests=None, preflight_bundle=None, resume=False, replay_only=False, timeout=180)`. It returns the immutable report directory, reason for stopping, request accounting, and unresolved next URLs. There is no alternate transport parameter.

## Durable evidence and resume behavior

Before any provider invocation, `attempts/NNNN/intent.json` is written exclusively, fsynced, and linked into a fsynced directory. It binds the exact observed URL, sequence, protocol hash, timestamp, and reserved budget slot. A nonblocking run lock prevents two processes from submitting against the same ledger. The capture probe writes under `attempts/NNNN/capture/`; the orchestrator then fsyncs saved files and records an immutable outcome.

The existing probe performs one Oxylabs API submission with no automatic retries. Credentials are loaded by that probe from the existing environment and `.env`; this module does not inspect or record them. Successful reuse requires the exact expected Oxylabs request payload, successful API/target status, one non-replay provider submission, exact provider-response/body equality, matching byte count, and successful fail-closed page parsing.

- A finalized successful capture is replayed locally after interruption; its URL is never submitted again.
- Intent without finalized metadata is `uncertain`: its budget slot remains consumed, no automatic retry occurs, and further collection stops.
- Failed provider capture is `capture_failed`; HTTP-200 content rejected by source validation or the parser is `capture_rejected`. Raw saved files remain available and hashed. Either stops the pass without retries.
- Hostile, ambiguous, missing, or mismatched pagination is rejected by the parser before it can authorize another request.
- Reused captures must form continuous observed prefixes from the configured seeds. Merely supplying an arbitrary later-page capture cannot authorize collection.
- Copied preflight files and accepted captures are verified on resume. Tampering fails closed. Original external preflight directories are no longer required once their verified copies are complete.

Immutable `reports/<state-hash>/` bundles contain `run.json`, `pages.jsonl`, `coverage.json`, and a completion manifest. Completion means that this artifact was published; it does **not** mean complete market coverage. Each page includes its local capture path and raw-file hashes. The protocol binds the implementation and preflight manifest; request/outcome records preserve failures and source clocks. Offline checkpoints, interrupted states, and later completed pagination states have separate immutable reports. Identical replay reuses the same report.

`run.json` separates `reused_provider_submissions`, `new_request_intents`, `global_reserved_requests`, and `max_requests`. It exposes `pending_observed_urls` and the stop reason. `complete_inventory` remains false and `market_coverage_status` remains `unverified`, even after every observed next-link chain closes. Coverage includes ordinary duplicates, page signatures, source totals, aliases, and advertisement identity conflicts as separate review evidence; nothing is silently merged or corrected.

## Offline verification on 2026-09-18

Tests: `tests/test_rental_discovery.py` plus `tests/test_rental_search.py`: **65 passed**. Coverage includes a durable intent visible before the mocked provider call, budget accounting with reuse, interruption before/after finalized capture, offline checkpoint/resume, immutable replay, hostile and ambiguous next links, source-page gaps, failed/raw outcomes, capture tampering, self-contained copied evidence, and concurrent-run rejection. Tests make no requests.

The real four-page preflight bundle was verified and replayed under `data/probes/chelsea-rental-discovery-offline-replay-20260918`, with ceiling 32, four reused submissions, and **zero new attempts**. Its first report is:

`reports/d8663ec80cb26dfdda7cf1423a5f9d38d1413ce966ffa12845fe5a0119a1c049/`

It reports `offline_replay_only`; both page-3 URLs remain pending. This is an offline implementation check, not an executed pagination pass.
