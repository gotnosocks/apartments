# Rental review workflow

Human review decisions, parser issue tickets, and observed-capture corrections are stored in an append-only JSONL ledger. The deployed dataset uses:

```text
/archive/reviews/chelsea-granular-20260916/review-ledger.jsonl
```

This path belongs to that immutable dataset. Create a new dataset and ledger for a new collection; do not repoint an existing ledger at a changed dataset. Every event includes the dataset name and participates in a SHA-256 hash chain. The review ledger is separate from `config/corrections.jsonl`, which has a different schema and is not automatically combined with it.

Review each capture in stages: identity, prices, layout, size, and amenities. Record a decision as `confirmed`, `needs_attention`, or `parser_issue`, with a concise note and reviewer identity. Parser issues become tickets grouped by a stable selection and field, with the affected snapshot IDs. They describe a problem for investigation; recording a ticket does not change parser code.

Corrections apply only to the explicitly selected observed captures. They do not assert a historical effective date or backdate a value. A correction batch must name between 1 and 5,000 unique snapshot IDs. Preview the complete batch against a frozen ledger revision before recording it. Preview tokens expire after one hour; submit against the exact revision used by the preview. A stale revision requires a refreshed preview. A request ID makes retrying a submitted batch safe if the response was lost.

Corrections are replayed in append order by `ReviewLedger.apply(raw, snapshot_id)`. The model or export path that wants these corrections must invoke that overlay explicitly; creating review events does not mutate archive documents or automatically change existing model inputs. Retraction appends an event that deactivates a correction batch, so replay then recomputes the result without that batch. The app preflights retractions and refuses an undo that would break a later patch; undo the dependent patch first.

Run the local SDK review application to review and preview changes before submission:

```sh
.venv/bin/python -m apartments.review_web --port 8766
```

Open `http://127.0.0.1:8766`. The browser talks to the SDK's cloud review function; credentials stay in the local process and never reach the browser. The app writes review events and correction previews into the dataset’s separate cloud review directory. The raw dataset is never modified. Queries run on one CPU worker that scales to zero after two idle minutes; no GPU or public cloud endpoint is provisioned. The app needs this device’s authenticated Modal SDK session.

Deploy or update the private backend with:

```sh
.venv/bin/modal deploy models/modal_review.py
```

Use **File grouped parser issue** when the archived payload has a value but extraction gets it wrong. That records the exact affected captures for a code fix and re-extraction from the archive, without another scrape. Use a bulk correction only when the same human-verified replacement applies to every selected capture. Issue counts and the main table describe source values; open an observation to see its corrected values beside the source.

The immutable collection has many observations of the same source unit label. The comparisons preserve that granularity, and do not prove that matching labels refer to one physical apartment. Review decisions belong to a capture and stage, rather than implicitly approving its older history. Price/status rows are source mentions, not signed lease prices.

For reproducible downstream work, freeze `events = ledger.events()` and record the final event hash, then call `ledger.apply(raw, snapshot_id, events=events)`. Rebuild the raw document with the same normalized field names and `archive_listing` payload used by `ReviewService.raw`. No episode aggregation is required.
