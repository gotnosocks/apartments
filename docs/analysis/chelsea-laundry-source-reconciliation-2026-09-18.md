# Laundry source reconciliation and a negation fix

The review verifies all **724 captures / 504 observations / 328 units / 100
buildings** in the earlier laundry phrase inventory against their own captured
structured fields. It checks analytical and typed capture identity, source
clocks, description/body/raw-listing hashes, source shard hashes and literal
offsets. Diagnostic replay supplies the verified recovered description where
necessary. The original raw payloads remain intact. This selected inventory
does not establish population accuracy or recall.

All six previously reviewed hookup-only cases have a `WASHER_DRYER` code in
their own `/propertyDetails/features/list`:

| Advertisement | Building | Structured evidence index |
| --- | --- | --- |
| 1574318 | 695 Avenue of the Americas | 2 |
| 1271335 | 322 Seventh Avenue | 1 |
| 3429697 | 453 West 21st Street | 5 |
| 3685392 | 237 West 19th Street | 3 |
| 1818725 | 110 Ninth Avenue | 1 |
| 5039794 | 345meatpacking condominium | 4 |

Their in-unit categories are not false positives caused solely by a hookup
regex. Preserve the structured code and prose separately. Advertisement 1271335
explicitly offers hookups for the tenant to install equipment; installed status
is unresolved. Hookup wording alone does not universally deny existing machines
or justify changing a unit to no/shared laundry.

The broader hookup phrase group contains **54 captures / 40 observations / 35
units / 17 buildings**: 36 captures carry the private-equipment code, six carry
the shared-laundry code, and 12 have neither. Every original category agrees
with replay of v3. These are capture counts, not independent apartments.
Hookup-only interpretation was manually reviewed for the six development cases,
not every phrase hit.

## Definite extraction error

Advertisement **4800947**, 340 Ninth Avenue unit 3, has two captures supporting
one historical observation. It explicitly denies laundry in the building twice,
including “doesn't have on-site laundry.” Neither capture has a structured
laundry code. The v3 parser skipped the first denial but recorded the contracted
second denial as a positive in-building assertion.

`attribute-evidence-v4` now recognizes these scoped laundry denials, preserving
`not:in_building` evidence. A separately reported private washer/dryer remains
compatible; a structured shared-laundry claim produces a visible conflict.
Without positive evidence, the old scalar category stays unknown. It does not
become a claim that every kind of laundry is absent.

Replay of the same 724 captures under v4 changes the scalar result for exactly
those two captures from in-building to unknown. The six hookup cases retain
their structured claims. Seventy-one focused tests pass across extraction,
source auditing, analytical transformation, description recovery and research
pipeline publication, including scoped denials and coexisting private equipment.

The frozen analytical rows and running Bayesian fit have not been revised.
Apply the named correction in the next versioned transformation, retaining the
original category and capture evidence. This correction does not date a physical
facility removal. Four-level extraction, independent validation and matched
Bayesian fitting remain pending.

## Artifacts

- Original replay: `data/model/chelsea-laundry-capture-source-audit-20260918`.
- Corrected replay: `data/model/chelsea-laundry-capture-source-audit-v4-20260918`.
- Both preserve source-bound capture records, support summaries and frozen code.
- Both publications and identical replays passed. The original freezes v3;
  replay under v4 requires a distinct output identity.

Reproduce the corrected audit with:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.laundry_source_audit \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --descriptions data/model/chelsea-analysis-descriptions-20260918 \
  --phrase-audit data/model/chelsea-laundry-location-phrase-audit-20260918 \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --refresh data/probes/chelsea-candidate-refresh-20260918 \
  --output data/model/chelsea-laundry-capture-source-audit-v4-20260918
```
# Versioned correction follow-through

The source correction has now been applied to a separate analytical revision,
`data/model/chelsea-reviewed-laundry-negation-analysis-20260918`, through
`models/laundry_negation_revision.py`. The ledger is
`config/reviews/chelsea-laundry-negation-20260918.jsonl`, correction
`6bbdcd31-2a0f-4b16-989d-3edcba8eeb21`, recorded at
2026-09-19T02:55:25.929195+00:00. Its target includes the exact complete source-row
version hash; it does not apply indiscriminately to every history of the unit.

Publication and identical replay pass. Independent full-dataset comparison
confirms 52,863 observations remain, exactly one historical laundry value becomes
unknown, and prices, membership, source clocks and all 172 current rows remain
unchanged. Both supporting captures retain their source hashes and scoped denial.
The row's review history records before/after values and the separate correction
clock. This revision has not yet been fitted or selected as the main model.
