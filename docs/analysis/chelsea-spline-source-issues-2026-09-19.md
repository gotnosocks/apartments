# Three source issues: independent archived-capture check

The archived pages support three narrowly scoped annotations: **furnished-only offer** for ad 4141846, **furnished offer without an exclusivity claim** for ad 2021775, and **structured-versus-prose bathroom conflict** for ad 2728974. They do not justify changing rent, assigning a physical conversion date, or propagating an attribute across other advertisements of the same unit. No source, fitted dataset, or model was modified.

## Verification and scope

Starting from the frozen [34-case review inputs](../../data/model/chelsea-spline-floor-movement-review-inputs-20260919/cases.jsonl), independently located all four own-advertisement captures in `/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1`. Checked each listing shard against the immutable historical export's `source-files.json`, each `raw_listing_json` against the evidence hash, and each decompressed HTML body against its SHA256 under `/data1/apartments/archive/bodies`.

Reparsed every complete HTML body with `apartments.granular_parse.parse_listing`. In all four cases the resolved description exactly matched the bound evidence, and **every non-description field of the full reparsed listing payload equaled the original archived payload**. The original description was a React `$3f` reference in each capture; literal offsets below refer to the resolved `/description` string, not HTML bytes or that reference. Description hashes also matched. No network retrieval, image interpretation, or new price collection was involved.

The source observation is a historical initial ask using `retrospective_same_advertisement` attributes. Own-advertisement price history is available, but the HTML was collected in September 2026. This establishes that the captured advertisement carries both the quoted text and its own historical price events. It does **not** establish when the wording first appeared or that it was unchanged throughout the marketing interval.

## Decisions and exact literal spans

Offsets are zero-based Python Unicode character indices, with the end excluded. Each quotation is an exact source substring.

| Advertisement | Capture(s) | Span | Literal | Conservative decision |
|---|---|---|---|---|
| 4141846 — Vesta 17 / 201 West 17th Street 6B | 38104 | `[2064,2146)` | `Please note: The apartment is being offered furnished only, for 1 or 2 year lease.` | Explicit furnished-only offer for this advertisement. The fitted `furnished=null` leaves a material cohort/attribute issue. A one- or two-year offer is not evidence of short-term rent. |
| 4141846 — same | 38104 | `[344,410)` | `a utility closet with stacked front-loading Whirlpool washer/dryer` | Explicit installed in-unit laundry claim; fitted `laundry_type=null`. Keep this as a separate extraction lead. |
| 2021775 — Walker Tower 18D | 31802 and 88893 | `[163,272)` | `This furnished rental is the epitome of luxury and is available immediately for the most discerning resident.` | Explicit furnished offer. It does **not** say furnished-only, exclude an unfurnished alternative, or quantify a furnishing premium. Fitted `furnished=null` warrants an annotation, without strengthening the claim. |
| 2728974 — Chelsea Modern PH9/10A | 16523 | `[212,234)` | `5 bed, 5.5 bath duplex` | Conflict: `/propertyDetails/fullBathroomCount=5` and `/propertyDetails/halfBathroomCount=0`, also represented as five full/zero half in the fitted row, versus 5.5 baths in prose. Preserve both claims; do not automatically replace zero half baths with one. |

All four payloads have `pricing.furnishedRent=null`; this is not evidence against the explicit furnishing prose. They also have null `netEffectiveRent`, `monthsFree`, `leaseTermMonths`, and `rentedPrice`. These nulls do not establish a signed lease, a transaction price, or an independently verified gross-versus-net basis. No separate furnished price is available.

## Own-price chronology

The following events are from the **matching** `/propertyHistory` item where `listingId` equals the reviewed advertisement, not from another advertisement of the same unit. The structured `pricing.price`, sole `pricing.priceChanges` entry, and every listed own-history event agree on the amount in each case.

| Ad | Own historical events | Exact initial price-change timestamp | Other source clocks / limits |
|---|---|---|---|
| 4141846 | 2023-06-05 ACTIVE **$18,000**; 2023-07-06 TEMPORARILY_OFF_MARKET $18,000; 2023-10-05 NO_LONGER_AVAILABLE $18,000 | `2023-06-05T12:00:38.000-04:00` | `createdAt=2023-06-05T11:33:06.000-04:00`; status becomes ACTIVE at `12:01:18-04:00`; `offMarketAt=2023-07-06`, while final unavailable status is October 5. Do not collapse those two statuses into one date. |
| 2021775 | 2017-03-01 ACTIVE **$35,000**; 2017-04-02 IN_CONTRACT $35,000; 2017-05-04 NO_LONGER_AVAILABLE $35,000 | `2017-03-01T15:23:41.000-05:00` | Both captures agree. `createdAt` equals the initial price timestamp; `updatedAt=2017-05-04T18:36:30.000-04:00`. “In contract” does not establish the eventual rent or furnishing terms. |
| 2728974 | 2019-05-07 ACTIVE **$42,000**; 2019-10-04 NO_LONGER_AVAILABLE $42,000 | `2019-05-07T00:00:00.000-04:00` | `createdAt=2019-05-09T07:27:55.000-04:00` follows the source's initial event by two days; retain both rather than rewriting history. `updatedAt=2019-10-31T11:53:10.000-04:00`. Neither clock dates a bathroom change. |

The fitted `period` values are June 2023, March 2017 and May 2019 respectively. An annotation can target that exact historical source row and its captured evidence. A valid-time interval asserting furnishing status or bathroom configuration throughout those months, or throughout the complete marketing interval, would require an additional explicit temporal-assignment policy or dated corroboration.

## Capture identities and knowledge clocks

All timestamps below are UTC. Walker Tower's two captures contain the same resolved description but different body and raw-listing hashes; both remain independently bound.

| Ad / capture | Source URL | Captured at | Description interpreted at | Evidence `known_at` |
|---|---|---|---|---|
| 4141846 / 38104 | `https://streeteasy.com/rental/4141846` | 2026-09-09 17:27:22.288343 | 2026-09-18 15:14:09.947093 | 2026-09-18 15:14:09.947093 |
| 2021775 / 31802 | `https://streeteasy.com/rental/2021775` | 2026-09-09 15:06:26.159216 | 2026-09-18 15:14:01.515121 | 2026-09-18 15:15:18.885019 |
| 2021775 / 88893 | `https://streeteasy.com/building/walker-tower/18d` | 2026-09-10 23:11:51.635715 | 2026-09-18 15:15:18.885019 | 2026-09-18 15:15:18.885019 |
| 2728974 / 16523 | `https://streeteasy.com/rental/2728974` | 2026-09-09 08:48:25.853057 | 2026-09-18 15:13:39.464600 | 2026-09-18 15:13:39.464600 |

The later `known_at` on Walker Tower's earlier capture reflects the bound observation's combined evidence clock; it is not the original advertisement date. A newly recorded manual annotation should have its own actual recording time, separate from both capture and historical price dates.

### Exact bindings

All hashes below are SHA256. `row` hashes use canonical JSON for the exact current analytical observation, including its floor projection.

```text
4141846
  audit_id: 15b0a695cf02ea4e2102d83f014a109ef7bdd423d20fdfbd2cedef7593922302
  unit_id: unit:7f433d11-8474-56d0-a1ab-e0f0534fdc4b
  row: ba461d2b9e858c289bc65651f919c5cdcf652bd2d44ad3ebd8419169beb99bf6
  capture: 38104
  body: af908674d165a415894df71729f36cb71d4ec1e744d4a4d86df84ba276f1900a
  raw_listing: 2ba3eb6c9538ab646dbc1479099795431beb67a7b3384ccb2df1bbf1afc9a8c8
  description: 4a9d5df33574a4c534ba5e9c1a37959fa1559d9f5304d37d07927bf16705af4c
  shard: listing_observations/part-00019.parquet
  shard_hash: b9d3667b491c8b5b90bd7112f91338b17279640683325af4092bd1da4b777b60

2021775
  audit_id: b97bfb2f62f56515737f38c5a8352486864118749a3ef45b81ab0414b42a3aa5
  unit_id: unit:7ffce4e2-f07a-50e8-86d5-7b24db111bbc
  row: f274224c993292efbc12c051524e974e31b0efef52c730de789dcba2a2cf2672
  shared_description: 0618e3751f98607ffc01a25373452e3dee02252167c711708a7c22ea50218570
  capture: 31802
  body: 94ad2e2abae02efe4d45e84d272dcb604f4ba5a3f7623ed54d0e06955786be04
  raw_listing: e64758690493142adc48cad01503a8f264919b5ca0a31fe5d916999f12da0f43
  shard: listing_observations/part-00015.parquet
  shard_hash: 5543108023bf7b55ecca4c06e2d5ce5530d0d08de3fbc09e1ac08ebb41738722
  capture: 88893
  body: 245bd8412ec2b2a8b9b0fe593c96fe1329dfb28f66779cc9c001a75f0d311121
  raw_listing: 72b9f0ac20cbde5954ac85ade4b476870511f1b8e709b723643c7661656f59ba
  shard: listing_observations/part-00044.parquet
  shard_hash: 672934b15ac6d61aacc2bd8868e28ad2fb5e4bbfeb55b57fb5b357e52615331f

2728974
  audit_id: 03c8e14364538ae2750529efa9bda9082461d74e0a9725b7ad5a8af72e469180
  unit_id: unit:e4118256-e903-5b5b-9b0f-468383e440e8
  row: 45d7ad2fa84e408edbae31a00650ca32262791fb2256b0eb079a727ebc1e0982
  capture: 16523
  body: d33fbab911c1fce23e13b4693dd07892b47c9dff98370d888ceea634009867ee
  raw_listing: 555d1da2ebbeaf52434fa64dfea80f11bf7969229b79493d77dad0f315a08979
  description: 8c145425c12a42a2a71f01e2b0b445c5ca9c034d7cca6e72bfa863b7ecb7b3b2
  shard: listing_observations/part-00008.parquet
  shard_hash: d79f5c96deca6b7d01cd555ed04522c9624190235d5fff625827785ef1849251
```

For the main-analysis review layer, retain these as source-bound unresolved issues with the different furnishing strengths explicitly named. A later numeric correction or cohort exclusion should be a separate versioned action with its own scope and reason. In particular, the bathroom conflict does not justify altering the already-conservative unknown floor for `PH9/10A`.

## Expanded-source annotation bundle

Four issues on these three advertisements are now published against the exact
expanded source in `data/model/chelsea-expanded-floor-source-issues-20260919`:
the two distinct furnishing claims, the separate unextracted laundry claim,
and the bathroom-count conflict. Review time is `2026-09-20T00:08:00Z`.
The publication process independently loaded the resulting bundle and checked
all source-row identities, observed fields, literal spans and attached captures.
Its manifest SHA-256 is
`23ca6c13d393d5580ccf41084e8061d5a8234ff4dd323431100998736fe528d7`.

The source hashes above describe the original reviewed rows. The annotation
bundle binds the expanded row versions separately, including their new floor
provenance. The completed expanded-source verifier establishes unchanged
nonfloor observations and literal evidence. The annotations do not mutate
observations or posterior estimates. They are prepared for the candidate's
main-analysis review layer; the selected main fit has not yet changed.

Reproduce using `docs.analysis.scripts.publish_expanded_source_issues` with
the expanded dataset, the bound September 18 description archive, the output
above, and `--reviewed-at 2026-09-20T00:08:00Z`.
