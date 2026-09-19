# Full-cohort laundry measurement research

The experimental measurement now covers **72,065 source captures attached to
all 52,863 fitted observations**, including the 172 current listings. It reads
the hash-verified historical shards and archived current bodies, verifies raw
advertisement identity, and attaches only each capture's own recovered literal
description. No scraping, source mutation or analytical projection is involved.

The prior phrase-candidate screen was useful for development but could not
establish full-cohort support. The new `models.laundry_cohort_measurement`
command removes that lexical prefilter. It retains independent private/shared/
same-floor claims and their exact pointers/spans. An observation gets a
candidate category only when every attached capture agrees, including unknowns.
This does not infer installation/removal dates or propagate later attributes
backward to earlier advertisements.

## Iteration and remaining measurement limits

Version 2 fixes the previously reviewed same-floor paraphrases and laundry-room
denial. Adversarial checks reject relative floors, future installations and
exceptions. The first full-cohort pass exposed another error: generic modal
words such as “will” and “could” caused unnecessary withholding. Examples include
“Getting your laundry done will be easy with an in-unit washer and dryer” and a
room that “could be utilized as a bedroom” with a washer/dryer.

Version 3 ties uncertainty checks to equipment/installation language and splits
exclamations/questions as clause boundaries. Installation-review flags fall
from 364 captures to 51. Relative to version 2, candidate categories change in
434 captures covering 243 units in 106 buildings. These are parser-development
changes, not validated source corrections or estimated price effects.

All **47 focused tests pass**, including recovered-description use, raw byte/ad
identity rejection, unchanged input clocks, scope conflicts and future equipment.
On the 52 earlier manual labels, v3 detects all reviewed scoped denials and
hookup-review cases and misses two same-floor paraphrases. Those labels informed
development; their agreement is not independent accuracy.

The nine distinct additional installation-review clauses inspected outside the
old phrase screen concern hookups, equipment offered on request, equipment to be
added before move-in, renovation/appliance scope, or permission to install private
equipment alongside a shared laundry room. The last case (advertisement 1883177)
also exposes a remaining limitation: a shared laundry room “right outside your
front door” and optional private installation occur in the same clause. The
extractor conservatively withholds the clause rather than preserving the shared
claim separately. These cases require scoped reconciliation; a review flag does
not establish absence of equipment. Promised equipment and installed equipment
may also need separate representation for advertised-rent analysis.

## Provisional observation support

| Most convenient reported option | Observations | Units | Buildings | Current rows |
| --- | ---: | ---: | ---: | ---: |
| In unit | 15,540 | 7,953 | 739 | 84 |
| On floor | 259 | 149 | 21 | 0 |
| In building | 21,339 | 9,637 | 435 | 70 |
| Explicit none | 12 | 8 | 6 | 0 |
| Unknown/withheld | 15,713 | 8,206 | 898 | 18 |

Observation categories are mutually exclusive; unit and building counts can
overlap across observations. There are no category disagreements across attached
captures in this particular dataset and no direct positive/negative conflicts
under these rules. Neither establishes source truth or general extraction
accuracy. Explicit-none support remains particularly sparse and needs direct
absence-scope review. Same-floor claims can coexist with private equipment, so
these category counts are smaller than counts of all positive same-floor claims.

The next model experiment must retain scope/coexistence evidence, review remaining
flags and changes against the accepted encoder, and check within-building support.
No four-level fit or main-model change has been made. Unknown must stay separate
from explicit none; scarce support must remain visible in posterior contrasts.

Artifacts:

- `data/model/chelsea-full-cohort-laundry-v2-20260919`: preserved rejected
  full-cohort modal-word behavior and its exact extractor.
- `data/model/chelsea-full-cohort-laundry-v3-20260919`: revised capture measurements,
  unanimous observation candidates, source bindings and frozen code.
- `data/model/chelsea-full-cohort-laundry-v3-review-20260919`: comparison with all
  52 development labels and every changed capture category.

Reproduce the full-cohort pass with a fresh output directory:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.laundry_cohort_measurement \
  --dataset data/model/chelsea-reviewed-floor-masked-analysis-20260918 \
  --descriptions data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --historical-descriptions data/model/chelsea-analysis-descriptions-20260918 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --refresh-roots data/probes/chelsea-candidate-refresh-20260918 data/probes/chelsea-discovery-details-20260918 \
  --output data/model/chelsea-full-cohort-laundry-v3-20260919
```
