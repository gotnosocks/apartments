# Human corrections and point-in-time observations

The data path is:

`immutable response → retained capture interpretation → human correction overlay → derived model inputs`

Human edits live separately in **`config/corrections.jsonl`**, a Git/jj-versioned,
append-only ledger. The default ledger starts empty. No example below is a real
correction. Neither ledger edits nor exports update archive bodies, captures,
`attribute_versions`, or the current `listings` projection.

The overlay supports any apartment attribute, including nested objects and lists.
Examples include square footage, bedrooms, bathrooms, amenities, views, building
assignment, unit labels, marketed floor and physical elevation floor. The latter
two are separate attributes. Adding an unknown attribute does not require a
schema migration. Source identity and collection metadata are protected: correcting
a displayed unit label does not silently merge/rekey units or rewrite capture IDs.

## Three independently retained layers

- `raw` in an observation export is the preserved **parsed capture interpretation**.
  Original HTTP responses remain in the archive and are referenced by provenance.
- `corrected` is a copy with the selected human edits applied.
- `corrections` records the applied IDs, author, reason, evidence, dates, patch and
  changes. Original values remain accessible in `raw`; the full ledger is retained.

The ledger uses standard JSON Patch (`jsonpatch`, RFC 6902) with `add`, `replace`,
`remove` and `test`. `null` is an explicit unknown value; `remove` removes the
attribute; no patch means retain source data. Replacing a missing field fails;
`add` may introduce a missing field or replace an existing object member. Parent
objects must exist. A `test` operation can guard an edit against unexpected input.
Use `/attributes/square_feet` and `/attributes/bedrooms` for the normalized fields
that future model preparation will consume. Raw-only fields can be overlaid under
`/archive_listing/...`; changing a duplicate raw representation does not implicitly
recompute normalized fields. Nested historical episode IDs are also duplicate
source assertions: editing them never changes the immutable observation envelope
or rekeys event evidence. Downstream consumers must use the envelope for identity.
If both representations must change, patch both in
one edit. Provenance and original source values remain separate in either case.

## Time semantics

Every edit has an automatically generated `recorded_at`: when the correction was
entered. Its validity is a separate, **explicit** human assertion:

- `{"from":"2018-01-01","until":"2022-01-01"}` means from inclusive, until exclusive.
  An open start or end is allowed. A matching bounded edit requires an explicit
  `effective_at`; the overlay never substitutes scrape time for historical time.
- `{"all_time":true}` explicitly applies across times within the selected target.
  Prefer an episode or version target when only one listing/capture is known to
  be wrong. All-time scope is never inferred from when the edit was entered.

Dates mean midnight UTC. Timestamps must include a timezone. Knowledge-time
cutoffs are inclusive. A 2026 correction asserting a 2018 fact can be used in a
2026 retrospective analysis of 2018, but is absent from a view of knowledge as of
2018. A listing's historical date does not establish when we learned its attributes.

`--known-as-of` is the convenient strict cutoff for **all three** collection,
interpretation and human-correction clocks. It excludes observations with unknown
collection times. Separate `--collected-as-of`, `--interpreted-as-of`, and
`--corrections-as-of` support intentionally different research questions; the
manifest preserves each choice. When only `--interpreted-as-of` is specified,
the CLI uses that cutoff for human corrections too. Explicit independent cutoffs
must not be described as a strict single-time reconstruction.

## Targets and conflicts

A target requires `source` plus at least one of `version_id`, `capture_id`,
`episode_id`, `source_listing_id`, or `building_slug`. Add `unit` or additional
keys to narrow it. All keys must match **original** observation identifiers exactly.
`source_listing_id` is currently a source unit label, not a verified physical-unit
ID. Matching an episode never implies merging its units with similarly named ones.

Edits to disjoint fields combine. Overlapping edits from different correction
records fail, even if one has a narrower target. Parent/child paths and edits to
indices of the same array count as conflicts. No silent “latest wins” or specificity
rule exists. Intentional multi-step changes can be a single patch.

To revise an edit, add a new edit with `supersedes` set to the current active ID.
The target and validity must remain the same; the entire previous patch is replaced.
To change scope, retract the old edit and add a new one. Withdrawal appends a
record; it does not delete history or resurrect a superseded predecessor. Replaying
an earlier correction cutoff still produces the old result.

## Commands

An illustrative `edit.json` (values are examples, not assertions about real units):

```json
{
  "target": {"source":"streeteasy", "episode_id":"example-episode"},
  "validity": {"all_time":true},
  "patch": [
    {"op":"test", "path":"/attributes/square_feet", "value":700},
    {"op":"replace", "path":"/attributes/square_feet", "value":750},
    {"op":"add", "path":"/attributes/advertised_floor", "value":14},
    {"op":"add", "path":"/attributes/physical_floor", "value":12},
    {"op":"add", "path":"/attributes/view", "value":{"courtyard":true,"street":false}}
  ]
}
```

```sh
uv run --locked python -m apartments corrections add edit.json \
  --author Ben --reason 'Verified against measured floor plan' \
  --evidence 'reference to floor plan'

uv run --locked python -m apartments corrections list
uv run --locked python -m apartments corrections list --as-of 2026-09-15T23:59:59Z
uv run --locked python -m apartments corrections retract CORRECTION_ID \
  --author Ben --reason 'Wrong floor plan'
```

For a small local fixture or selected version:

```sh
uv run --locked python -m apartments export-observations /tmp/example-corrected \
  --db /tmp/example.duckdb --version-id VERSION_ID \
  --known-as-of 2026-09-16T12:00:00Z --effective-at 2018-06-01
```

For the real archive, run the export/preparation on Modal using the selected
ledger copied into that run. This change does not deploy a new cloud service or
transfer the archive. The exporter requires an already imported analysis database;
it does not scan/import the raw archive or launch a fit. `--raw-only` disables
edits while preserving the same observations. The ledger must still exist so the
manifest can record the compared correction version.

## Reproducibility and operational behavior

A new export directory contains `observations.jsonl`, the visible correction-ledger
prefix, and `metadata.json` written last. The manifest includes source-observation
and output hashes, correction-prefix hash, cutoffs, applied IDs, counts and dataset
version. It can be used to pin the correction input to a model run. Existing output
directories are never overwritten. Interrupted/failed exports lack a ready manifest.
Readers stream 32 observation versions per batch; full-data runs belong on Modal.

Ledger appenders use a filesystem lock and fsync; readers verify the hash chain.
A partial tail or edited record fails closed. This is corruption detection and
reproducibility, not an authenticated signature. Do not hand-edit old ledger lines
or concatenate conflicting branch histories. Author is an explicit attribution,
not an authentication system. Use Git/jj to retain/review the ledger and record a
new correction when changing a decision.

## Integration boundary

This is the correction and observation layer for step one of the new modeling
pipeline. The existing monthly fitter still uses the legacy latest-unit projection;
it does **not** consume this export yet. The preparation stage preserves every capture and price-event occurrence; an
episode ID is a source link, never a required aggregation level. Physical-unit
resolution, temporal attribute alignment, and aggregation belong to an explicit
model-stage projection. See [granular tables](granular-dataset.md). It must retain applied correction IDs and the
manifest rather than joining the latest corrected attributes onto every past event.
The fixed `effective_at` export is a selected-time view, not a claim that all source
attributes were valid then. Per-event preparation can call `Overlay.apply` with
each event's effective time and immutable source context.

Existing `config/building_overrides.json` rules remain only in the legacy ingestion
path. They are not silently imported into this ledger or applied to the observation
export: their author/knowledge dates are unavailable. A future explicit migration
must preserve them as legacy assertions with that limitation, rather than inventing
historical correction timestamps. No fabricated floor/size corrections have been
added to the production ledger.
