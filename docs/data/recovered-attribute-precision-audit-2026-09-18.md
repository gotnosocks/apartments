# Recovered-description attribute audit, 2026-09-18

An independent Codex-agent review examined 60 extracted assertions from 60
recovered descriptions: ten each for floor, elevator, HVAC, laundry, unit views,
and directional exposure. The source was
`data/exports/chelsea-description-recovery-20260918/accepted.jsonl`: 27,240 records
containing 16,547 unique description texts. The extractor ran on descriptions
alone. Within each feature family, deterministic hash selection prioritized up
to three nearby negation contexts and three shared-space contexts, then ordinary
examples, without repeating a description within that family.

These are **agent judgments about literal source text**, not human ground truth
or inspections of apartments. This deliberately enriched sample of extracted
assertions cannot estimate population precision or recall. A nearby negation word
also need not negate the extracted feature; reviewing that scope was part of the
exercise.

The review judged 55 selected assertions supported, three unsupported, and two
scope-ambiguous. The concrete defects were:

| Snapshot | Source text | Incorrect interpretation | Resolution |
| --- | --- | --- | --- |
| 70528 | “A two-minute walk up Ninth Avenue will get you to Gristedes” | No elevator | A pedestrian route supplies no elevator evidence |
| 44049 | “window a/c units are permitted” | Installed room AC | Equipment permission leaves installation unknown |
| 22244 | “Many of the residences offer expansive city views” | This apartment has city views | A statement about some residences does not identify this unit |
| 20975, 63615 | “CHELSEA'S FINEST ROOF DECK” followed by “Open River & City Views” | This apartment has city views | Mixed roof-deck and generic marketing scope remains unknown |

After the review, the parent task authorized narrow fixes and stopped the pending
v3 amenity comparison. `attribute-evidence-v3` now rejects those unsupported
inferences. It preserves actual residential walk-up statements, explicit installed
HVAC, direct unit-view assertions, and laundry explicitly identified as in-unit.
A subsequent apartment-feature heading restores unit exposure scope after a
roof-deck heading. The extractor and source data were not changed while the earlier
historical build was running; the corrected extractor is frozen for the separate
historical **dataset v4** rebuild.

All 60 description-only audit expectations match the revised extractor, including
the five deliberate unknowns. This is regression agreement with these agent labels,
not an independent validation result. Structured amenity fields or human correction
overlays can separately support or conflict with description-only evidence.

Artifacts under `data/exports/recovered-attribute-precision-audit-20260918/`:

- `selected.jsonl`: full descriptions, literal evidence and offsets, source IDs,
  selection hashes, pre-fix values, and context strata.
- `labels.jsonl`: individual judgments, rationale, source excerpts, expected values,
  and post-fix description-only values.
- `sampling.json` and `summary.json`: population-of-recovered-text counts, sampling
  procedure, limitations, and artifact/extractor hashes.

Validation: 63 tests passed across attribute extraction, historical dataset
construction and analytical transformations. Four new source-grounded regression
tests exercise the failure modes and corresponding legitimate positive controls.
The frozen extractor SHA256 is
`b183ea556c2411ba528840b28f205d60d0cf1205cfa97d9de9932ee1b6d8203c`.
Published historical datasets remain immutable; the next model comparison must
record the new dataset and extractor hashes.
