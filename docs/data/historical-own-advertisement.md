# Historical own-advertisement dataset

`apartments.historical_dataset.build_historical_dataset` reconstructs one initial
asking-rent record per advertisement from a completed `canonical-url-v1` granular
transform. The source must contain `listing_observations`, `event_mentions`, and
`rental_unit_memberships` Parquet shards. Production inputs are read only.

```python
from apartments.historical_dataset import build_historical_dataset
build_historical_dataset(
    source_directory, output_directory,
    as_of='2026-09-18T23:59:59+00:00',
    ledger='config/corrections.jsonl', start='2010-01-01', end='2026-08-31',
)
```

To incorporate verified recovered descriptions from the same archived bodies,
also pass `description_recovery=<completed recovery bundle directory>`. The CLI
exposes the same setting as `build-historical --description-recovery`. The current
Chelsea example and its immutable v4 artifacts are documented in the
[recovery follow-up](../analysis/chelsea-recovery-ablation-2026-09-18.md).

The initial price is the earliest ACTIVE rental event whose event listing ID
matches the captured advertisement's listing ID. Historical mentions of other
advertisements are never used to borrow current attributes. Accepted canonical
membership must be unique and agree with every contributing capture URL.
Conflicting initial prices, layout values, or canonical identities are excluded
with explicit reasons; conflicting optional amenity values become unknown.
Advertisements with inconsistent bedroom/bathroom layouts for a unit in the same
month are also excluded. Furnished, explicit concession, and short-term records
are excluded. No signed-lease interpretation is implied.

## Clock contract

- `price_at` is the initial advertised event's effective date.
- `observed_at` is an explicit compatibility alias of `price_at` for modeling;
  **it is not the date when the evidence was collected or available**.
- `collected_at` is the latest contributing source capture timestamp.
- `known_at` is the latest contributing capture, parse, or applied correction
  recording timestamp, also bounded below by `identity_known_at`, the canonical
  source transform completion time. Source created/updated times are retained only as audit
  evidence, never substituted for collection time.

The build rejects a knowledge cutoff earlier than the source transform's completion
time: canonical memberships were derived at that time and are not retrospectively
available before it. Earlier historically available identities require a fresh
source transformation at the intended cutoff.

Each model row states `attribute_assumption=retrospective_same_advertisement`.
This reconstructs historical advertised attributes using later captures of the
same advertisement. It does not establish that the attributes were known at the
price date or that every attribute was unchanged throughout the advertisement.
Temporal model validation is therefore retrospective reconstruction validation,
not a historically executable forecast backtest. Prospective observation data
must use the distinct dated analytical dataset contract.

## Corrections and audit

Correction selectors use immutable source listing IDs, source building/unit
labels, and snapshot IDs (`capture_id` and `version_id`). `episode_id` is the
advertisement listing ID. The overlay's knowledge cutoff is the build's `as_of`;
effective intervals are evaluated at `price_at`, never `collected_at`.

The supported normalized correction paths are `/attributes/<attribute>` and
`/asking_rent`. Raw source metadata and `/archive_listing` remain available for
JSON Patch tests; normalized attributes define the model values. A correction
can explicitly resolve conflicting prices or layouts. Conflicting correction
rules fail the build instead of silently choosing one.

`audit.jsonl` preserves normalized uncorrected capture values, original initial
price candidates, source JSON hashes and snapshot selectors, literal extracted
attribute evidence, all correction records, corrected values, and exclusions.
The immutable production shard supplies the full raw payload. Accepted rows link
to the audit by its canonical content hash. `coverage.json` reports selections;
reasons can overlap, so exclusion-reason counts need not sum to excluded rows.

Every consumed shard and participating implementation file is hashed before and after construction. Completion is
published only after the input hashes agree. The complete bundle hashes its
observations, audit, coverage, and source file manifest; implementation and active
correction ledger-prefix hashes are also pinned. Identical reruns verify and
reuse a bundle; changes require a new output directory.

## Verified archived-description recovery

Pass `description_recovery=<completed bundle directory>` to enrich captures whose
original payload contains an unresolved description reference. This is a new
parser interpretation of retained source bytes, not a human correction and not a
new scrape. The production source data is never rewritten.

The recovery bundle must have the supported `description-recovery-v1` contract,
verified `accepted.jsonl` and `source-files.json` artifacts, and an inventory
matching the current source listing and snapshot shards. Every accepted
interpretation must agree with an independently read source snapshot ID, body
hash, listing ID, exact original listing JSON hash, and description reference.
The recovered description's hash must also match. Unknown or duplicated
snapshots, changed source identities, malformed versions, or mismatched hashes
fail construction.

Only interpretations recorded on or before `as_of` apply. Each capture audit
retains its original description, original normalized attributes, original
extraction evidence, parser interpretation provenance, and interpreted
attributes. Human corrections run after interpretation and can test or override
those interpreted values. `description_interpreted_at` records the latest applied
interpretation time on accepted model rows, and `known_at` includes this clock.
Future interpretations remain unused at earlier knowledge cutoffs.

Source completeness is independently checked: actual row counts for every
consumed table must equal `complete.json` declarations. When
`canonical-units.json` exposes its membership digest and count, both must match
the consumed membership artifact. An input with missing shards or an altered
membership table cannot be legitimized merely by generating fresh output hashes.
