# Rental review workflow

Open the primary app directly over Tailscale at
http://thelio.tail3983e0.ts.net:8766/. The localhost SSH tunnel remains available.

Human review decisions, parser issue tickets, and observed-capture corrections are stored in an append-only JSONL ledger. The primary dataset on thelio uses:

```text
/data1/apartments/archive/reviews/chelsea-granular-20260916/review-ledger.jsonl
```

This path belongs to that immutable dataset. Create a new dataset and ledger for a new collection; do not repoint an existing ledger at a changed dataset. Every event includes the dataset name and participates in a SHA-256 hash chain. The review ledger is separate from `config/corrections.jsonl`, which has a different schema and is not automatically combined with it.

Review each capture in stages: identity, prices, layout, size, and amenities. Record a decision as `confirmed`, `needs_attention`, or `parser_issue`, with a concise note and reviewer identity. Parser issues become tickets grouped by a stable selection and field, with the affected snapshot IDs. They describe a problem for investigation; recording a ticket does not change parser code.

In the **Identity** stage, select rows using the checkboxes and click **Confirm selected**. Shift-click a checkbox or row to select a range from the last clicked row; Ctrl/Cmd-click toggles individual rows without clearing other selections. Plain clicks on row space also toggle selection; an ordinary click on the listing title still opens its details. The header checkbox selects all observations on the current page. Use the building, issue, search, and review-status filters to find the desired postings. Selection clears when the list reloads or filters/pages change. Each selected observation receives an identity confirmation; labels, attributes, and prices remain unchanged. Other stages are unaffected. The request is safe to retry without duplicating decisions; if another review changed the ledger, refresh and select again. Previous decisions remain in the audit history, and a later individual decision can supersede a bulk confirmation.

Corrections apply only to the explicitly selected observed captures. They do not assert a historical effective date or backdate a value. A correction batch must name between 1 and 5,000 unique snapshot IDs. Preview the complete batch against a frozen ledger revision before recording it. Preview tokens expire after one hour; submit against the exact revision used by the preview. A stale revision requires a refreshed preview. A request ID makes retrying a submitted batch safe if the response was lost.

To correct one historical price, open the observation and use **Edit price** beside the specific entry in **Price and status history**. Enter the price (or leave blank for unknown), add the supporting evidence, preview, and apply. The correction targets that capture's exact rental history occurrence, including its episode and event position, rather than every event with the same date or the listing's advertised asking price. The history view shows the effective price and retains the original source price beside it. Use **Undo correction** in recent activity to retract it. Repeated mentions in other captures are not changed automatically.

History-price corrections use the existing overlay at `/archive_listing/propertyHistory/<episode>/rentalEventsOfInterest/<event>/price`. The view verifies the occurrence against its archived event JSON before offering an edit. Consumers of the review overlay must read the corrected nested price for that original occurrence; immutable `event_mentions.price` remains the source value. Source-based issue flags remain visible after a correction; record a separate Prices-stage review decision when that capture's review is complete. A replacement inferred from a same-day asking-price event is human evidence, not verification of the contract or signed lease price.

Corrections are replayed in append order by `ReviewLedger.apply(raw, snapshot_id)`. The model or export path that wants these corrections must invoke that overlay explicitly; creating review events does not mutate archive documents or automatically change existing model inputs. Retraction appends an event that deactivates a correction batch, so replay then recomputes the result without that batch. The app preflights retractions and refuses an undo that would break a later patch; undo the dependent patch first.

Run the review application against a local archive and ledger with:

```sh
.venv/bin/python -m apartments.review_web \
  --dataset-root /data1/apartments/archive/datasets/chelsea-granular-20260916 \
  --review-state /data1/apartments/archive/reviews/chelsea-granular-20260916 \
  --port 8766
```

The same paths can be supplied with `REVIEW_DATASET_ROOT` and `REVIEW_STATE`. Open `http://127.0.0.1:8766`; the server defaults to loopback. On thelio, explicit `REVIEW_LISTEN` and `REVIEW_ALLOWED_HOSTS` settings also allow direct Tailscale access. An SSH tunnel remains available. Local requests use the `ReviewService` directly. Its DuckDB operations and ledger writes are serialized in the Flask process, while the raw dataset remains unchanged. To freeze an older app during a cutover, set `REVIEW_READ_ONLY=1` or pass `--read-only`; it will continue serving GET requests and reject POST requests.

The Modal deployment uses `/archive` in place of `/data1/apartments/archive`. That deployment is now stopped; the primary app uses the local thelio paths. For backwards compatibility, omitting both paths retains the SDK-backed Modal mode. It requires an authenticated Modal session and uses the private cloud review function:

```sh
.venv/bin/python -m apartments.review_web --port 8766
```

Deploy or update the private backend with:

```sh
.venv/bin/modal deploy models/modal_review.py
```

Use **File grouped parser issue** when the archived payload has a value but extraction gets it wrong. That records the exact affected captures for a code fix and re-extraction from the archive, without another scrape. Use a bulk correction only when the same human-verified replacement applies to every selected capture. Issue counts and the main table describe source values; open an observation to see its corrected values beside the source.

The immutable collection has many observations of the same source unit label. The comparisons preserve that granularity, and do not prove that matching labels refer to one physical apartment. Review decisions belong to a capture and stage, rather than implicitly approving its older history. Price/status rows are source mentions, not signed lease prices.

For reproducible downstream work, freeze `events = ledger.events()` and record the final event hash, then call `ledger.apply(raw, snapshot_id, events=events)`. Rebuild the raw document with the same normalized field names and `archive_listing` payload used by `ReviewService.raw`. No episode aggregation is required.

Issue counts above the list reflect the selected building, search, and review status for the active stage. Each issue button shows how many observations would match that issue; All observations removes only the issue filter. The result total and pagination reflect all active filters. Counts refresh after review decisions. Dataset summary and stage overview totals describe the full dataset.

## Merge housing unit identities

Open **Merge unit records** from the review app, or visit `/units`. This tool saves
the assertion that selected StreetEasy **rental listing IDs refer to one housing
unit**. It is independent of per-capture review confirmations and price edits.

**Possible matches** suggests distinct identities sharing an observed building
and unit label, including normalized-field identity corrections. Missing and
generic labels are not pooled. Search by building, unit label, or rental ID,
then choose **Compare**. Alternatively, enter rental IDs directly to compare
records with different labels. Check the desired listings, compare the revised
selection if needed, add a reason, and choose **Merge into one unit**.

Each saved merge assigns one durable `unit:<uuid>` to the selected rental IDs.
All their captures resolve to it, including repeated URLs of the same listing.
Unmerged rental IDs have the provisional identity `streeteasy:rental:<listing_id>`;
that default is not verification of a physical apartment. Selecting a member of
an existing merged unit expands the comparison to its full membership. Combining
units preserves an existing unit ID; adding a listing never silently removes
other members. The **Merged units** list reopens saved units and their histories.

The authoritative declarations are stored separately in an append-only,
hash-chained file alongside the review ledger:

```text
/data1/apartments/archive/reviews/chelsea-granular-20260916/unit-identities.jsonl
```

The ledger records exact listing IDs, dataset, reviewer, reason, recording time,
and the review-ledger revision used for comparison. Writes lock the ledger,
reject stale identity revisions, and support idempotent retries. **Undo the latest
identity merge** appends a reversal; dependent later merges must be undone first.
It restores the preceding identity assignments, without changing source records,
corrections, or stage decisions. New rental IDs are never added by matching labels
alone. The ledger belongs to this immutable dataset; carrying decisions into a new
dataset must be deliberate.

The resulting unit record exposes **one combined history**. Repeated rental
mentions are combined only when their history listing ID, complete source event
JSON, and effective corrected price agree. Every combined event retains its
capture/episode/event occurrence references. Different episodes, statuses, source
prices, and conflicting correction versions stay distinct; matching dates alone
are insufficient. Missing history listing identities are not combined across
captures. Attribute observations remain separately dated, and non-null differences
are highlighted. A unit merge does not assert unchanged condition over time.

`GET /api/units/inspect?unit_id=...` returns the resolved unit and history;
`GET /api/units/export?unit_id=...` downloads that record, including membership,
observation attributes, history provenance, and both ledger revisions.
`GET /api/units/mapping` exports the declared rental-listing-to-unit mapping.
Normal observation/list responses also expose the resolved `unit_id`. Downstream
code can use `identity_map(events)` or `resolve_unit(listing_id, events)` from
`apartments.unit_identity`, freezing the identity ledger hash with model inputs.
The legacy rent model is not automatically rerun or rewritten by a merge.

The merge utility resolves identity and builds the unit history; it does not
propagate per-capture price corrections or review decisions to other captures.
Original observation and event tables remain immutable evidence.
