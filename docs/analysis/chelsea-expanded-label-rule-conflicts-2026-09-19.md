# Explicit-floor conflicts for expanded unit-label rules

Review of all six disagreements found when testing numeric three/four-digit
labels and multiple-letter suffixes against the selected cohort's explicit
floor values. Five are erroneous attribution of a photograph disclaimer to the
advertised apartment. The sixth is a genuine disagreement between the label
proxy and an explicit apartment description; its cause remains unresolved.
No source, correction ledger, analytical dataset or fitted model was changed.

## Review method and source binding

The complete own-ad descriptions were read for all six advertisements and both
captures of each advertisement. `load_evidence` verified the selected dataset's
lineage and its exact description archive. The twelve corresponding archived
`raw_listing_json` records were checked against their capture-level hashes,
advertisement IDs and the historical export's shard hashes. All twelve contain
literal parsed descriptions matching the archive; none uses recovered text.
None has a floor-named field in `propertyDetails`.

Replaying `extract_attribute_evidence` on those own raw records reproduces the
selected explicit floors solely through `/description` pattern matches. Thus
these are not disagreements with an independently populated structured floor
field. Label values below come from each capture's
`/propertyDetails/address/displayUnit`, not from another advertisement.

Bound inputs:

- Selected dataset: `data/model/chelsea-label-floor-analysis-20260919`;
  manifest SHA-256
  `5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605`.
- Descriptions: `data/model/chelsea-refreshed-bayesian-descriptions-20260918`;
  manifest SHA-256
  `79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08`.
- Historical source inventory:
  `data/exports/chelsea-serving-history-20260918-asof1600`;
  manifest SHA-256
  `31cab6c92c095dc52d33bc89900f9fbfa02e1633b810883eb18a91fbdf08f22d`.
- Raw archive:
  `/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1`.
- Replayed extractor: `src/apartments/attribute_evidence.py`, SHA-256
  `3366fa2efd18d3d5b009b4e7d8ad7e2fac912f27fa5bd3420f480c067c4fd6ff`.

## 160 West 22nd Street: photograph disclaimers

All five advertisements contain this exact sentence:

> Photos are of the same unit on the 3rd floor.

The extractor selects only `unit on the 3rd floor`, losing the photograph
scope. Each description begins by naming the advertised residence shown below.
The description therefore does not support assigning floor 3 to that residence.

| Advertisement | Own label | Numeric-label candidate | Current extracted floor | Captures | Matched character span |
|---|---|---:|---:|---|---|
| 4501831 | `#601` | 6 | 3 | 32516, 91235 | `[470, 491)` |
| 4592739 | `#801` | 8 | 3 | 32515, 91229 | `[478, 499)` |
| 4637006 | `#802` | 8 | 3 | 32518, 91242 | `[478, 499)` |
| 4668696 | `#902` | 9 | 3 | 32514, 91227 | `[478, 499)` |
| 4758888 | `#402` | 4 | 3 | 32512, 91214 | `[478, 499)` |

For 4592739 and 4637006, the next sentence explicitly says the advertised
unit has better views and light than the photographed unit. Advertisement
4668696 makes that same distinction and mentions an additional kitchen window.
Advertisement 4758888 starts with `Residence 402`, but later repeats
`Unit 902 has much better views and light`; that is additional evidence of
copied descriptive material, not evidence that apartment 402 is apartment 902.
Advertisement 4501831 lacks the extra comparison sentence but has the same
photograph disclaimer and separately names residence 601.

**Decision:** `erroneous_description_scope_for_floor`, for all five ads.
These observations do not establish a building numbering offset or invalidate
the numeric-label rule. The prose match refers to illustrative photography.

**Recommended handling:** in a future reviewed projection, invalidate the
floor-3 description assertion while preserving the raw sentence and its
provenance. Amend extraction to recognize photograph/video/example-unit scope
and add these actual cases as regression tests. The numeric-label values
6, 8, 8, 9 and 4 remain separately identified label-derived candidates; accept
them only through the expanded label rule and its applicable review/support
checks. Do not present them as newly discovered structured measurements or
independently verified physical floors. The existing frozen fit remains intact.

## 244 West 16th Street: `#1RE`

Advertisement **3219430**, captures **26561** and **76812**, explicitly says:

> This apartment is on the 2nd floor walk-up

The extractor's exact match is `This apartment is on the 2nd floor`, character
span `[184, 218)` in both descriptions. The preceding text describes the
advertised one-bedroom apartment's renovation, kitchen, bedroom and living
room. The following text continues with its light, quietness and West 16th
Street location. There is no photograph, example-apartment or shared-amenity
scope around this assertion. Both own captures have display label `#1RE`.

**Decision:** `unresolved_label_vs_explicit_apartment_floor`.
The explicit floor-2 extraction is correctly scoped. A label-first-digit proxy
would give floor 1, but the text alone does not establish whether that reflects
a numbering convention, a mistaken label, or an inaccurate description.
Other reviewed ads in this building include matching label/prose floors, so a
blanket building-wide +1 offset is not justified.

**Recommended handling:** retain the existing explicit source floor 2 for this
advertisement and record the candidate label floor 1 as conflicting evidence.
Do not overwrite it with the generic suffix rule, infer a physical height, or
propagate a building-wide offset. Review this exception at advertisement/unit
scope when admitting additional labels from the building.

## Exact description identities

Both listed captures share the same description hash for each advertisement:

| Advertisement | Description SHA-256 |
|---|---|
| 4501831 | `a0de7449da331b0bc90df9f6e410d2c586c98e5ad2a784ec119ae8a93ef22048` |
| 4592739 | `26c8c26573f8c77df332bd19c0ef6c39153e67076cb1505543af9cd96445b0f2` |
| 4637006 | `169353047f0836a237ae2621a8c32cf2c98a8a9d22338847fd7e9654b5791fde` |
| 4668696 | `a97e6910b10c984255216ddf4db6462729512c6794d2bf9816f4cb9e57b7af26` |
| 4758888 | `7477b64f58ba56780dc9b1303ca0b26028faafd4d4a12d7c50bed4de4070d6b9` |
| 3219430 | `08145d115c556ded8ad07769997df73b2b820d6c5d0cd8a80018061f6b4f34fe` |

The corresponding raw captures are in `listing_observations/part-00013.parquet`,
`part-00016.parquet`, `part-00038.parquet` and `part-00045.parquet` under the
bound raw archive. Character offsets are zero-based and end-exclusive in the
literal description, before any rendering or whitespace normalization.

## Extractor repair

`attribute-evidence-v6` now rejects floor matches directly governed by a
reference-unit or media phrase and records
`reference_unit_floor_claim_withheld`. The check is scoped to the floor claim;
it preserves unrelated direct apartment-floor assertions and structured floors.
Replaying all twelve verified complete descriptions removes floor 3 from all
ten captures of the five 160 W22 ads and preserves floor 2 for both captures of
244 W16 `1RE`. The focused extractor suite passes 57 tests; the broader scoped
extractor, analytical, granular, StreetEasy and laundry-revision run passes 99
tests in total (including the focused cases).

This repairs future extraction only. The currently selected dataset and fit are
immutable and still need the five source-bound corrections in the next
analytical projection. The review above records the old v5 extractor hash so
the original failure remains reproducible.
