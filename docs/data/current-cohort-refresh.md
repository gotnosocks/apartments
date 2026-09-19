# Refreshing the current analytical cohort

`models.refresh_analysis_cohort` builds a same-month research dataset from the
reviewed historical cohort and completed detail collections. It performs no fit.
The transform verifies each collection's plan, target/result bindings and snapshot
contents before combining captures. It checks each selected current listing's raw
body, canonical identity and raw-listing hash, then projects explicit full/half
bathroom reports using the existing measurement policy.

Historical analytical rows, including their source-review overlays, are preserved
exactly. Current attributes never fill earlier observations. The supported operation
is a refresh within the parent's analysis month; rolling an older current capture
into a historical initial-ask cohort requires a separate policy.

Selection resolves each advertisement's latest visible capture before combining
units. A later failed refresh blocks an older success for that advertisement, but
does not declare it inactive. A later verified success can supersede that failure.
Changed unit identity across captures requires review rather than silently becoming
two units. Different advertisements for one unit retain the existing compatibility
checks. Missing search results do not remove earlier fresh candidates.

Existing current bathroom reviews cannot silently disappear on rebuilding the
same capture. A new capture of the same advertisement supplies new dated evidence;
capture-specific reviews are not propagated without review. The output retains
all failures, exclusions and current source text/count evidence separately.

## September 18 transformation

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m models.refresh_analysis_cohort \
  --parent data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --collection data/probes/chelsea-candidate-refresh-20260918 \
  --collection data/probes/chelsea-discovery-details-20260918 \
  --as-of 2026-09-19T00:45:56.975589+00:00 \
  --output data/model/chelsea-refreshed-analysis-cohort-20260918
```

The result has **52,863 observations / 22,189 units / 1,131 buildings**:
52,691 unchanged historical rows and **172 current rows**. The current set consists
of 168 newly captured candidates plus four earlier fresh captures absent from the
incomplete discovery pass. Nine previously selected captures are superseded.
Across the combined collections, 13 latest inactive advertisements, 22 concession
offers and 11 furnished offers are excluded. Nine unresolved identity failures
remain in the separate failure evidence. No retained current row has a structural
full/half-count consistency flag; that does not establish physical correctness.

Publication and identical replay passed. Eight new tests exercise failure and
knowledge-clock behavior, identity drift, inactive updates, historical preservation,
same-month scope, retained current reviews, real parser/body integrity and replay.
The combined transformation, current-analysis and bathroom-projection checks have
14 passing tests.

The bundle is explicitly **pending current-source review**. A preliminary wording
screen finds both ordinary residential live/work permission and an actively used
art-gallery triplex advertised as residential. Those are different scope questions;
neither is automatically excluded by a keyword. Net-effective wording in several
listings concerns approval standards rather than a claim that the advertised price
is net. Full source review, a new Bayesian fit and main-model selection remain
separate steps. The existing source/floor comparison cohort remains frozen.
