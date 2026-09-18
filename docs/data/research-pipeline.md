# Reproducible rental research pipeline

The [project intent](../project-intent.md) is the governing scope. The new path is:

```text
Oxylabs → immutable archive → retained capture interpretations
                                      + dated correction ledger
                                      ↓
                         verified analytical bundle
                                      ↓
                          interpretable pricing model
                                      + explicit candidate snapshot
                                      + personal dollar preferences
                                      ↓
                            preference/Pareto ranking
```

## Collect and import

Use the existing environment on Thelio. Populate the ignored project `.env` with
`OXYLABS_USERNAME` and `OXYLABS_PASSWORD` (see `.env.example`). All live archive
crawls now enforce Oxylabs, including resumes of older direct-transport profiles.
Public-record/API enrichment remains separate from listing collection.

For an isolated, bounded building capture:

```sh
uv run --locked streeteasy-archive --data data/probes/example-building backfill \
  --building https://streeteasy.com/building/the-sierra-chelsea \
  --transport oxylabs --max-requests 10 --concurrency 1 --no-include-unavailable

uv run --locked python -m apartments import-archive data/probes/example-building \
  --db data/example.duckdb
```

Keep archive scope and coverage reports with each collection. A request budget
counts queued document fetches; an individual fetch may involve provider retries.
An unfinished queue is resumable, not complete coverage. `--building` can target
NYC buildings beyond Chelsea; the automatic neighborhood discovery profile
currently covers Chelsea and West Chelsea. Citywide collection expansion remains
an explicit next stage.

Raw bodies, source versions and fetch observations remain separate. New captures
retain redacted provider metadata even when parsing fails, a page is blocked,
or its body duplicates a previous fetch. Legacy observations have empty provider
metadata rather than invented provenance.

## Dated corrections and analytical output

Corrections use the existing [append-only ledger](corrections.md). For a unit
layout change, create two non-overlapping edits targeting the original building
and unit: `/attributes/bedrooms = 0` valid `[date0,date1)` and `= 1` valid from
`date1`. Add each through `apartments corrections add` with an author, reason
and evidence. Do not edit older ledger lines. Conflicting overlapping writes fail
until explicitly revised or retracted.

```sh
uv run --locked python -m apartments build-analytical data/exports/example \
  --db data/example.duckdb \
  --ledger config/corrections.jsonl --as-of 2026-09-18T15:00:00Z
```

The output includes:

| Artifact | Meaning |
| --- | --- |
| `observations.jsonl` | ACTIVE gross asking-price observations with attributes from the same capture, flags, patches and provenance |
| `intervals.jsonl` | Attribute observations carried forward until another observation or correction boundary, explicitly labeled as an assumption |
| `attribute_assertions.jsonl` | Sparse dated facts explicitly asserted by correction writes, including intervals before the first capture |
| `quarantine.jsonl` | Conflicts, unknown clocks/identity, inactive listings and unusable price observations with reasons and evidence |
| `corrections.jsonl` | Frozen visible correction-ledger prefix |
| `complete.json` | Input identity, cutoff, code version, record counts and output hashes |

An assertion about 2018 bedrooms does not invent 2018 rent, bathrooms or elevator
service. Assertions and observed intervals are deliberately separate tables.
Queries about historical truth must use the explicit assertion provenance and
must not relabel carry-forward as verified change dates.

The knowledge cutoff requires collection and interpretation timestamps no later
than the cutoff and selects the correction ledger as it was known then. Unknown
clocks are quarantined. Inactive ads may contribute attribute evidence but their
last asking prices do not become current rental observations. Normalized source
page IDs are explicitly not independently verified physical-unit identities.
Programmatic callers can provide supported `unit_id` mappings in the immutable
observation envelope.

Identical reruns verify and reuse the completed output. Changing source evidence,
code, cutoff or corrections requires a new output directory. Partial publication
can resume only with the same inputs. Original source files and ledgers are never
modified. Consumers verify completion and every artifact hash before fitting.

The `build-analytical` CLI consumes the imported DuckDB `attribute_versions`
contract. The separate `build-historical` CLI consumes the completed canonical
granular dataset and reconstructs historical own-advertisement initial asks:

```sh
uv run --locked python -m apartments build-historical \
  /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  data/exports/chelsea-history --as-of 2026-09-18T23:59:59Z --end 2026-08-31
```

Use the `-canonical-url-v1` source directory. The older `-canonical-units`
directory inspected during the first pass lacks membership artifacts; the newer
completed source already has them. The [historical dataset contract](historical-own-advertisement.md)
keeps price dates separate from collection, interpretation and identity knowledge.
It uses the explicit correction ledger and does not silently import legacy review
decisions. The canonical review state's fresh-start record says those older
decisions were not imported. Existing granular and Bayesian workflows remain
available, and neither historical reconstruction nor canonical URLs prove actual
physical-unit identities or contemporaneously known attributes.

## Fit and compare

```sh
uv run --locked python -m apartments fit-pricing-legacy data/exports/example data/model/example
```

The default reserves later UTC months for validation. Encoding and fitting use
only training rows. The model does not refit on the holdout. Repeated captures
reduce to the latest observation per unit/month; explicit furnished, short-term,
and concession observations are excluded with counts. This is a selected sample
of gross asking rents, not a lease-price model.

If all observations are in one month, the default refuses to claim validation.
For an explicitly **descriptive, unvalidated** fit:

```sh
uv run --locked python -m apartments fit-pricing-legacy data/exports/example \
  data/model/example-descriptive --holdout-fraction 0
```

Inspect `report.json` for sample selection, feature support, convergence,
holdout metrics and limitations. `model.json` preserves the complete training
encoder and coefficients. `analytical-manifest.json` pins the source bundle.
See [pricing model details](../model/pricing.md) for the API and marginal
contribution calculations. Unsupported feature contrasts are warned about;
an unobserved feature's zero coefficient is not evidence it has no market value.

## Personal preferences

Supply an explicit candidate JSONL file with monthly `rent`, `unit_id`,
`observed_at`, and known attributes. Select and verify availability separately;
the historical analytical observation table is not a current inventory feed.
The following preferences are illustrative, not the owner's inferred preferences:

```json
{"bedrooms":500,"laundry_type=in_unit":150,"elevator":100,"window_exposures.south":75}
```

```sh
uv run --locked python -m apartments rank-apartments candidates.jsonl preferences.json \
  data/exports/example-frontier --budget 5000 --model data/model/example-descriptive
```

Dollar amounts are monthly willingness to pay per attribute increment or
category indicator. Negative values are allowed. Unknown valued attributes
exclude a candidate by default; `--unknown-policy zero` explicitly treats them
as zero benefit. The output retains unknown flags, utility, Pareto membership,
preferences, input hashes, and optional model comparison. Monthly preference
surplus and asking-minus-predicted rent are separate quantities.

There is no automatic assertion of live availability, citywide coverage, causal
amenity values, calibrated predictive intervals, or successful model validation.
Those require additional data and checks described in the project intent.
