# Fit-ready rows

Before it samples, a fit reads two tables: the rows it models, one for each advertised price, and
a feature matrix with a row for each of them. This file describes both as the current fits
prepare them. The rebuilt pipeline in [the pipeline handoff](../handoff/data-pipeline.md) has to
produce the same rows from API records, so I froze copies of the current ones as references,
listed at the end.

## Preparation inside a fit

`rentfrontier.run` makes four calls before sampling:

1. `data.load` reads the dataset's `observations.jsonl`. For each line, `data._flatten` keeps 34
   fields. Then `load` parses the two dates and adds `log_rent`, for 35 data columns.
2. `data.split_and_rules` draws the held-out rows and applies the fit's data rules. The rules
   drop quarantined rows, correct coded fields, and merge or split units.
3. `features.build` builds the feature matrix from the rows, the description evidence and the
   outside tables.
4. `model.prepare` turns the rows and the matrix into arrays for the sampler.

I treat the frame passed to the last two calls, with its held-out mask, as the fit-ready rows.
Each fit hashes them with `data.rows_sha256` and records the hash in its result.json as
`rows_sha256`.

## Columns

To list the columns each step reads, I ran `ops/pipeline/reference.py columns` on the served
fit's frozen rows. The command repeats the last two calls with pandas' column lookups patched to
note each column asked for, and it compares the feature matrix with the frozen
`features.parquet`. Then it drops the columns neither call read, runs both calls again and
compares every field of the two feature builds and of the two prepared results, the sampler's
arrays among them. On the served rows, the two calls read 31 of the 35 data columns, besides
`heldout`. The first build equals the frozen matrix, and without the other four columns both
calls gave the same results as with them. The trace took 1.9 minutes.

In the table, F marks a column read by `features.build` and P a column read by `model.prepare`.
The nulls column counts nulls among the served fit's 214,887 rows.

| column | type | read by | from the observation's | nulls |
|---|---|:-:|---|--:|
| `audit_id` | string | F P | `audit_id` | |
| `unit_id` | string | F P | `unit_id` | |
| `building` | string | F P | `building` | |
| `canonical_unit_url` | string | F P | `canonical_unit_url` | |
| `source_listing_id` | string | F | `source_listing_id` | |
| `asking_rent` | float | | `asking_rent` | |
| `log_rent` | float | P | log of `asking_rent` | |
| `period` | timestamp, first of the month | F P | `period` | |
| `price_at` | timestamp, UTC | F P | `price_at` | |
| `price_basis` | string | F | `analysis_price_basis` | |
| `bedrooms` | float | F P | `bedrooms` | |
| `bathrooms` | float | | `bathrooms` | |
| `full_baths` | integer | F | `reported_full_bathrooms` | |
| `half_baths` | float | F | `reported_half_bathrooms` | 506 |
| `square_feet` | float | F | `square_feet` | 160,052 |
| `listed_floor` | float | F | `listed_floor` | 86,543 |
| `label_derived_floor` | float | | `label_derived_floor` | 91,705 |
| `elevator` | yes, no or unknown | F | `elevator` | |
| `doorman`, `laundry`, `hvac`, `pets` | string, or unknown | F | `doorman_type`, `laundry_type`, `hvac_type`, `pet_policy` | |
| `has_description` | boolean | | `description_interpreted_at`, when set | |
| `neighbourhood` | string | F P | `neighbourhood` | |
| `view_city`, `view_courtyard`, `view_garden`, `view_park`, `view_skyline`, `view_street`, `view_water` | yes, no or unknown | F | `view_exposures` | |
| `window_east`, `window_north`, `window_south`, `window_west` | yes, no or unknown | F | `window_exposures` | |
| `heldout` | boolean | P | the split | |

The fit uses `asking_rent` only through `log_rent`. Of the other three unread columns, the
rebuilt pipeline can leave out `bathrooms`, `has_description` and `label_derived_floor` without
changing a fit. The feature build joins the description evidence on `audit_id` and checks each
match against `source_listing_id`. It joins listing extras on `source_listing_id` alone.
`model.prepare` finds each unit's line, such as C in 4C, from the end of `canonical_unit_url`.

## Keys

In the served rows:

- `audit_id` is unique. It hashes the old pipeline's audit record, which lists page-capture ids,
  so the rebuilt pipeline can't reproduce it from API records.
- `(source_listing_id, price_at)` is unique, and so is `(source_listing_id, period)`. To compare
  rebuilt rows with frozen ones, I match them on `(source_listing_id, price_at)`.
- All rows of a `source_listing_id` carry the same `unit_id`, and all rows of a `unit_id` carry
  the same `building`. Of the `canonical_unit_url` values, 7,520 carry more than one `unit_id`
  after the unit rules.

Besides the description evidence, these rules key their entries on `audit_id`: the quarantine,
the bedroom, bath and size corrections, and the elevator and pet fills. Quarantine entries also
carry `source_listing_id` and `period`, and the corrections carry `unit_id` and `building`. The
unit labels key on `unit_id` and `canonical_unit_url`, and the unit reviews on `building` and
the unit's labels. The frozen rows give each kept row's listing and price date, so steps 4 and 5
can move the `audit_id` entries to the new keys.

Four rules read no file. `fields-review-v3` returns the rows as they came. The cases of
`building-joins-v1` and `west-coast-wings-v1` are constants in the code at the reference's
commit, so step 5 has to copy them into the ledger. `unit-splits-v4` holds no cases: it splits
unit histories by an algorithm over the rows, so it stays a pipeline step.

## Feature matrix

`features.parquet` holds `audit_id` and a float column for each feature, in the matrix's order.
`features.json` holds the feature set's id, the feature names, each feature's group and its
`prior_scale`. The served set, `nb8-nostuy-v1`, has 115 features in 23 groups. Besides the rows,
the feature build reads the files listed by `run.feature_sources`: description evidence for each
area, the building registry, PLUTO, the basemap, building footprints, listing extras, LPC
landmarks and the dated PLUTO releases.

## References

Each reference is a folder under `/data1/apartments/pipeline/reference/` on thelio. It holds
`rows.parquet`, the fit-ready rows with a `heldout` column, and for a reference with a feature
set, `features.parquet` and `features.json`. Its `manifest.json` records the spec, the hash and
size of each input and output, and for a fit with a result.json, whether the row hash and each
input hash equal the fit's record. An input missing from the record counts as a mismatch.

The freeze hashes each input file as the preparation reads it. It hashes the rule files and the
feature sources before the calls and again after them, and the observations file as `data.load`
reads it, with an empty cache so the load parses the file afresh. Then it copies each input
into `blobs/`, named by its SHA-256 and read-only, and stops if a file's hash differs from the
hash taken at the read. So the blobs hold the bytes the preparation read, and later edits to
the originals leave the references alone.

| reference | feature set | rows | held out | features | minutes |
|---|---|--:|--:|--:|--:|
| `served-nb8-5c1e5c7e` | `nb8-nostuy-v1` | 214,887 | 21,511 | 115 | 2.2 |
| `queued-nb9-lots2-9c1055f` | `nb9-nostuy-lots2-v1` | 296,182 | 29,669 | 117 | 3.6 |
| `queued-nb9-wholefloor-lots2-9c1055f` | `nb9-nostuy-wholefloor-lots2-v1` | 296,182 | 29,669 | 119 | 3.9 |
| `api-manhattan-below-59th-9c1055f` | `api-manhattan-below-59th-v1` | 312,388 | 31,239 | 126 | 10.9 |
| `api-manhattan-west-59th-110th-9c1055f` | `api-manhattan-west-59th-110th-v1` | 153,551 | 15,355 | 108 | 9.8 |
| `api-manhattan-east-59th-110th-9c1055f` | `api-manhattan-east-59th-110th-v1` | 208,399 | 20,840 | 110 | 11.2 |
| `api-manhattan-59th-110th-rows-9c1055f` | | 361,950 | 36,195 | | 1.0 |
| `api-brooklyn-prospect-park-rows-9c1055f` | | 194,277 | 19,428 | | 0.6 |
| `api-brooklyn-north-crown-heights-rows-9c1055f` | | 527,438 | 52,744 | | 1.5 |
| `api-brooklyn-greenpoint-bushwick-rows-9c1055f` | | 254,473 | 25,447 | | 0.7 |
| `api-brooklyn-williamsburg-crown-heights-rows-9c1055f` | | 272,965 | 27,296 | | 0.8 |

The minutes column gives the time each freeze took to prepare the rows and build the features,
hashing included. I froze them one after another on Oct 15 between 18:16 and 19:04 ET, beside
Data improvements' jobs, at a peak of 4.4 GiB.

Before this, I had frozen each reference once with earlier code. It hashed each input when it
copied the file, and it let `data.load` read a cached flattening of the observations. The
second freeze gave each reference the same input
hashes and the same row hash as the first. Six of the eleven folders also hold byte for byte
the same files. In the other five, `rows.parquet` came out with other bytes, while pyarrow reads
the same schema, metadata and values from both. So the row hash and the values, rather than the
file's bytes, decide whether two freezes agree.

The served reference comes from the served fit's dataset,
`chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-analysis-20261010-3ebfea0`, at commit 5c1e5c7e
with the fit's rules: `baths-ad-v3`, `bedrooms-ad-v3`, `fields-review-v3`, `quarantine-v12`,
`unit-labels-v15`, `unit-reviews-v1` and `unit-splits-v4`. Its row hash and all 20 input hashes
equal the fit's record in its result.json: the observations, five rule files and 14 feature
sources.

The two queued references share their dataset,
`chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-mw-analysis-20261014-cd891c8`, and their rows. Each
API reference comes from the dataset `api-REGION-analysis-20261015-6064263` of its region. The
four regions of the latest-ask run of Oct 15 are `manhattan-below-59th`, `manhattan-59th-110th`,
`brooklyn-prospect-park` and `brooklyn-north-crown-heights`, 1,396,053 rows in all. Data
improvements cut the second and the fourth by area into two parts each, and only the parts have
feature sets, so I froze the whole regions without features. Between them, the two Manhattan
parts hold the rows of `manhattan-59th-110th`, and the two Brooklyn parts the rows of
`brooklyn-north-crown-heights`, with equal values in all 35 data columns. Only `heldout`
differs, since each freeze draws its own split.

The queued and API references come from master at 9c1055fa. The queued ones use the unitnu4
line's rules as queued: `baths-ad-v3`, `bedrooms-ad-v6`, `building-joins-v1`,
`elevator-from-ad-v1`, `fields-review-v3`, `latest-ask-v4`, `pets-from-ad-v1`,
`quarantine-v31`, `sqft-units-v1`, `west-coast-wings-v1`, `unit-labels-v17`, `unit-reviews-v2`
and `unit-splits-v4`. The API references use the same rules with `latest-ask-api-v1` in place
of `latest-ask-v4`, as the held API lines do.

To freeze, check or trace a reference:

```sh
python ops/pipeline/reference.py run RUN_DIR NAME
python ops/pipeline/reference.py spec NAME --commit SHA --dataset DIR --rules R1,R2,... \
    [--features SET]
python ops/pipeline/reference.py verify NAME
python ops/pipeline/reference.py columns NAME
```

I ran each freeze as a `systemd-run --user` unit with a 7 GB memory limit and `TMPDIR` under
`/data1`.

## Checks for the rebuilt pipeline

1. API region tables: the rebuilt rows match the frozen rows on `(source_listing_id, price_at)`,
   with equal values in every column marked F or P. A difference needs a ledger entry or a
   listed bug in the old code.
2. Page-crawl references: on ads found in both a page-crawl reference and the API, the columns
   marked F or P agree, or the difference is explained the same way.
3. Feature matrices: the feature build on the rebuilt rows gives the frozen matrix, row for row,
   with rows matched through `rows.parquet`.
