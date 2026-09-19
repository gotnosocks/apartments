# Review of all label-derived floor disagreements

The manual source review covers **all 37 conflicting observations, 29 units,
18 buildings and 57 captures** in the fixed label-floor disagreement inventory.
Each observation has a named decision, reason, exact description, context spans,
capture hashes and review timestamp. No user adjudication is needed for this queue.

| Disposition | Observations | Interpretation |
|---|---:|---|
| Retain the explicit apartment-floor claim | 20 | 14 locally supported numbering offsets; six labels whose numeric prefix is not the floor |
| Withhold the apparent floor claim | 2 | The number describes a reference video/apartment |
| Withhold pending better source evidence | 15 | Inconsistent numbering or conflicting/copy-like descriptions |

At 152 West 20th, reviewed labels 1C/1D, 2D and 3D describe floors 2, 3 and 4;
stated flight counts corroborate that local pattern. Similar floor/flight
agreement appears at 132 West 15th #3A and 337 West 21st #4E. These observations
support retaining their explicit claims, not applying an offset to every unit
in those buildings.

Unit numbers can encode something other than floors. At 439 West 21st, #1D is
advertised on the fourth floor and one description offers #2D on the same floor.
Prefixes such as 41A, 34A, 18E and 33C also should not automatically become floors
41, 34, 18 and 33. Nor do these examples establish a universal first-digit rule.

Advertisements **3850761** (307 West 29th #4A) and **3849614** (454 West 22nd #3C)
put the conflicting floor number in a media disclaimer. That is insufficient
evidence of the advertised apartment's floor. At 180 Seventh #3C and 452 West
22nd #3A, different advertisements report different floors for the same source
unit. At 222 West 16th, disagreement directions vary across units, with repeated
template-like wording. No renumbering date, identity merge or physical change
can be inferred from these contradictions.

The source-bound policy is
`config/reviews/chelsea-floor-label-conflicts-20260918.json`; the full decision
archive is `data/model/chelsea-floor-label-conflict-review-20260918/decisions.jsonl`.
The recommendations have now been projected into a separate analytical revision;
**they have not yet been fitted.** Literal labels and old source claims remain
preserved. This fixed disagreement review is not an accuracy estimate for all
11,722 candidate unit-label inferences.

The revision `data/model/chelsea-reviewed-floor-masked-analysis-20260918` follows
the one-row laundry correction. All 37 reviewed observations still match their
original source rows exactly. Seventeen exact-version ledger corrections mask
only `advertised_floor`; the 20 retained claims remain unchanged. Known modeled
floors decrease from 366 to 349. All 52,863 rows, every price/nonfloor field,
prior review history and all 172 current observations remain unchanged apart from
those 17 floor values and their appended review records. Raw current evidence
is byte-identical. Independent comparison and deterministic replay pass; evidence
is in `data/model/chelsea-reviewed-floor-mask-verification-20260918`.

`config/reviews/chelsea-floor-masks-20260918.jsonl` targets complete source-row
hashes. Its final recorded timestamp is 2026-09-19T03:47:57.591531+00:00. Each
changed row preserves the old floor, review decision, source spans/capture hashes
and distinct review/correction clocks. This represents corrected knowledge, not
a physical floor change at that timestamp. Thirteen tests cover exact scope,
stale versions, capture identity, chronology, canonical floor encoding and replay.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m models.reviewed_floor_revision \
  --dataset data/model/chelsea-reviewed-laundry-negation-analysis-20260918 \
  --reviewed-source data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --review data/model/chelsea-floor-label-conflict-review-20260918 \
  --ledger config/reviews/chelsea-floor-masks-20260918.jsonl \
  --as-of 2026-09-19T03:47:57.591531+00:00 \
  --output data/model/chelsea-reviewed-floor-masked-analysis-20260918
```

The current running fits retain their frozen input. Loader/evidence-reader
integration and a matched refit of this new revision remain pending. No unreviewed
label prefix or building-wide offset has been added as an analytical floor.

Reproduce with:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m models.floor_label_conflict_review \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --descriptions data/model/chelsea-analysis-descriptions-20260918 \
  --label-audit data/model/chelsea-unit-label-floor-audit-20260918 \
  --policy config/reviews/chelsea-floor-label-conflicts-20260918.json \
  --output data/model/chelsea-floor-label-conflict-review-20260918
```
