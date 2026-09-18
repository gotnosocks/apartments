# Archived floor-plan references for en-suite research

Existing archived listing metadata supports direct floor-plan acquisition for a focused en-suite access review. **2,151 of 3,051 en-suite-screen candidate observations (70.5%) have explicitly labeled floor-plan asset IDs.** In the two-bedroom/two-full-bath/no-half-bath candidate cell, 691 of 864 observations (80.0%) have them. Eight previously reviewed cases in that cell have exact full-resolution image URLs in their archived HTML responses.

This inventory covers references only. A subsequent [four-image visual review](chelsea-floorplan-visual-review-2026-09-18.md) records newly acquired image bytes and bathroom-door interpretations separately. No bathroom feature, count, dataset, or fitted model was changed by the inventory.

## Why these are floor-plan references

The raw listing payload labels assets under `/media/floorPlans`, separately from `/media/photos`. That field is the classification evidence; filenames and photo position are not used to guess whether an image is a floor plan.

For the eight selected cases, the local archived response was decompressed and checked against its recorded SHA-256. The response contains both:

- HTML images with an explicit `floor plan 1` label.
- Serialized gallery objects with `mediaType: floor_plan` and exact `mediaSrc` URLs, including the `full` variant.

The inventory matches those URLs to the exact asset key in the same advertisement's raw `media.floorPlans` metadata. URLs are copied from the response, never constructed by substituting an ID into an assumed URL pattern. The payload's advertisement and unit identity, raw JSON hash, capture identity, and historical shard hashes are checked against the verified source bundles.

This confirms **same-advertisement reference scope**, not that the image depicts the correct unit, the advertised historical layout, or the current physical layout. The eight assets have not been seen. When fetched later, the image bytes will be newly collected data; the old HTML capture proves only that the reference existed then. Record the new request time, returned URL/status, media type, image hash, and source-reference ancestry separately.

## Coverage

| Measure | Count |
|---|---:|
| Candidate observations | 3,051 |
| Candidate captures | 4,008 |
| Observations with explicit floor-plan IDs | 2,151 |
| Units with explicit floor-plan IDs | 1,223 |
| Distinct floor-plan asset IDs | 2,006 |
| Captures with explicit floor-plan references | 2,811 |
| Captures with an empty `floorPlans` list | 1,086 |
| Captures with missing or unresolved media metadata | 111 |
| Same-advertisement rows with changing asset-ID sets across captures | 0 |
| Two-bedroom/two-full/no-half candidate observations | 864 |
| Those observations with explicit floor-plan IDs | 691 |

An empty or unresolved metadata field means no usable reference was established by this inventory; it does not establish that no floor plan exists. Candidate membership comes from the prior en-suite phrase screen, including ambiguous or hall/guest wording, and is not a sample of all Chelsea rental advertisements.

## Suggested first comparison set

All eight cases below have reported two bedrooms, two full bathrooms, and zero half bathrooms. Their en-suite classifications remain the previous text-only lower bound or unknown, pending actual plan inspection.

| Advertisement | Unit | Selected capture | Why inspect |
|---|---|---:|---|
| 1639871 | Loft 25, 6H | 61276 | Primary en-suite plus a nearby hall bath; inspect whether the latter also connects to a bedroom. |
| 4068484 | 248 Tenth Avenue, 2B | 27967 | “Each bedroom has its own bathroom”; distinguish direct access from assigned use. |
| 3059501 | 520 West 28th Street, 0007 | 20316 | Compressed bedroom/en-suite list; identify which bedrooms connect to which baths. |
| 3213567 | Chelsea Stratus, 23B | 36238 | Master/guest bath labels without an explicit access inventory. |
| 3080726 | Flow Chelsea, 24A | 33795 | “Master bathroom” and finish descriptions do not establish the two-bath access arrangement. |
| 4799624 | 133 West 22nd Street, 8B | 97344 | Primary en-suite explicit; second bathroom access unmentioned. |
| 4320516 | 118 West 27th Street, 11R | 41235 | Primary en-suite explicit; do not turn one mention into an exact count. |
| 5064467 | 252 West 30th Street, 2B | 33888 | Primary en-suite plus an additional full bath; connection of the latter is unspecified. |

Start with the first four. They offer a useful mix of hall, assigned-private, ambiguous-bedroom, and guest-access wording, rather than four repetitions of the same positive primary-suite description. They are candidates for distinguishing one versus two en-suite bathrooms, not preassigned one/two classes.

For each image, first verify unit/address labels and whether it is a representative, proposed, or actual plan. Then trace bedroom-to-bathroom doors, including hall-access bathrooms with an additional bedroom door. Preserve an explicit unknown where doors, partitions, labels, or room identity cannot be read. A plan can help identify adjacency and access but does not independently certify present construction or historical validity.

## Artifact and schema

`data/model/chelsea-floorplan-reference-audit-20260918` contains:

- `inventory.jsonl`: compact source-bound raw metadata for all 4,008 candidate captures.
- `selected-comparisons.jsonl`: eight source-linked cases, their previous text reviews, and all exact archived labeled image references.
- `summary.json` and `changing-asset-sets.json`.
- Frozen audit implementation and manifest hashes for relevant source/parsing code.

Each selected row includes `audit_id`, `source_listing_id`, `unit_id`, `canonical_unit_url`, `capture_id`, `body_sha256`, `raw_listing_sha256`, `description_sha256`, and source clocks. `floorplan_metadata.references` preserves `asset_id`, raw metadata, exact JSON source path, and explicit floor-plan label. `recommended_images` selects the actually observed `full` variant where available; its `image_url`, `source_kind`, `source_path`, and explicit gallery type remain available for acquisition provenance. No selected URL is inferred from a filename.

Implementation: `models/floorplan_source_audit.py`. Five focused tests cover explicit versus guessed classification, unresolved metadata, matching the source asset key, exact gallery URLs, and rejection of altered archived response bytes. The complete source inventory and selected references replayed exactly against the published bundle. All eight selected assets have both explicit HTML and gallery labels and an observed full URL. The combined bathroom/en-suite/floor-plan test set has 39 passing tests. No network requests were made.
