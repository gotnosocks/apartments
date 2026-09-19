# Laundry phrase revision: complete-cohort replay

Extractor v4 recovers the two explicit same-floor phrases missed during the
residual review. A replay across **all 72,065 captures / 52,863 observations**
changes exactly those two measurements; everything else reproduces v3, apart
from the version identifier. There are no current-listing changes and no new
units or buildings with any same-floor evidence. This improves measurement
consistency but adds little independent information for a laundry coefficient.

| Advertisement | Literal recovered claim | Candidate change | Revised-source status |
| --- | --- | --- | --- |
| 3895033, Thomas Eddy #5S | “Residents here enjoy the convenience of a washer/dryer on every floor” | in building → on floor | Retained in the pending 210-exclusion source |
| 970866, 101 W23 #6Q | “laundry with new machines on every floor” | in building → on floor | Already quarantined for its explicit short-term offer |

Both complete descriptions and all changed claim spans were reviewed. Each
advertisement has one attached capture, with its own structured laundry code.
The changes therefore increase unanimous same-floor candidate observations from
259 to 261 on the original source, still covering 149 units and 21 buildings.
In-building candidates decrease from 21,339 to 21,337. Only the Thomas Eddy
observation survives the pending revised source. No earlier or later ad for the
same unit is relabeled by this revision.

The original residual-selected cases informed these rules. The full replay
establishes the complete effect of this code change, not independent extraction
accuracy. The two older development misses—private washer plus “full laundry
facilities down the hall” in ad 860067, and a multi-amenity same-floor-access
clause in ad 2158973—remain unresolved by the extractor. They require further
scope-aware rules or individually reviewed evidence. Unknown is never converted
to explicit no-laundry.

## Method and checks

`apartments.laundry_measurement` v4 expands the existing “laundry with … on …
floor” construction to include machines. A second narrow rule recognizes
residents' explicit access/convenience wording for washer/dryer equipment on
each/every floor. It does not infer shared access from bare equipment somewhere
within a duplex. Existing negation, future-installation, exception, private
equipment priority and relative-floor guards remain in force.

`models.laundry_measurement_revision` checks the baseline measurement and
description archive manifests, then indexes descriptions on disk. For every
capture it verifies typed observation/capture/ad/unit identity, raw/body and
literal-description hashes, source paths and unchanged knowledge clocks. It
reconstructs only the structured laundry codes at their exact original list
indices and the recovered literal prose. **The archived v3 extractor must
reproduce its entire saved measurement exactly** before v4 is evaluated on that
input. Missing, duplicate or extra captures fail closed. Every new literal span
is checked against its description.

This is a verified replay of previously decoded evidence, not a fresh raw-page
parse. Empty placeholders for unrelated structured codes are harmless only
because exact full v3 reproduction is required and v4 adds prose rules only.
The previous extractor, current extractor, revision code, changed captures with
full descriptions, and before/after cohort support are archived. All input and
implementation hashes are checked again before publication. Disk indexing avoids
holding the complete description corpus and parsed source records in memory
beside the running sampler.

**109 focused tests pass**, covering the extractor, original capture reader,
revision replay, experimental projection and source audit. New tests include
negative/future/exception/relative-floor examples, equipment-versus-other-amenity
scope, preserved structured indices, raw identity and clock mismatches, exact
baseline failure, unknown descriptions, actual disk indexing and deterministic
publication. The real full-cohort command also completed twice against the same
output, verifying identical replay.

The live laundry fit's **20 bound implementation hashes still match** its
protocol. This extractor is not one of those dependencies, and the frozen
239-observation split used by that fit remains unchanged. No source projection,
new laundry fit or main-model selection was made from v4. The next production
fit must still isolate the pending source quarantine before any further laundry
measurement change is introduced.

Artifact: `data/model/chelsea-laundry-v4-full-replay-20260919`.
This is a delta/review artifact, not a replacement full-cohort measurement bundle
for `models.laundry_floor_projection`.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.laundry_measurement_revision \
  --baseline data/model/chelsea-full-cohort-laundry-v3-20260919 \
  --descriptions data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --output data/model/chelsea-laundry-v4-full-replay-20260919
```
