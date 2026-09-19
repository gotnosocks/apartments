# Cohort, floor measurement and manual adjudication

## What “current” means

The selected analytical dataset contains 52,653 observations: 52,481 historical
own-advertisement initial asking prices and 172 eligible capture-time asking prices.
Both groups enter fitting. “Current” is shorthand for the second measurement
group, not a holdout, representative panel, or live availability claim.

The refresh cutoff was **2026-09-19 00:45:56.975589 UTC** (September 18 in NYC),
with a seven-day maximum capture age and no budget filter. Its frozen selection
processed 227 candidate records: nine superseded observations, 13 latest captures
not confirmed ACTIVE, 22 concession exclusions and 11 furnished exclusions left
172 units. Discovery was bounded and incomplete. This is an eligibility rule
over collected inventory, not probability sampling of the Chelsea market.
See `data/model/chelsea-refreshed-analysis-cohort-20260918/summary.json`.

The eight highlighted source cases were originally selected for large absolute
residuals. They are now explicitly pinned in
`config/reviews/chelsea-residual-development-panel-20260919.json` for repeat
development checks. The reviewer keeps those IDs even when residual ranks change;
missing members fail visibly. New residual outliers form a separate diagnostic
queue. Neither group should be called representative or independent validation.
A representative stratified evaluation panel has not yet been constructed.

## Floor extraction versus fitted features

The source-bound label audit reads `/propertyDetails/address/displayUnit`.
Its conservative rule maps labels such as 3D to 3, preserving the source label.
It found candidates for **31,931 observations / 11,722 units** in the older
52,704-observation audit cohort. These are candidate advertised numbering proxies,
not physical floors or measured elevation.

All 37 overlapping explicit-floor disagreements were reviewed: retain 20 explicit
claims and mask 17 unreliable claims. Those masks **are incorporated in the
selected model's dataset lineage**. The earlier conflict report's “not fitted”
wording describes its status at publication and is superseded here.

The broad label-derived candidates **have not been projected into model inputs**.
The selected model still uses only 349 known explicit advertised/listed floors
among 52,653 observations (0.66%). It represents floor with cumulative threshold
increments. The completed pooled floor/elevator candidate uses the same sparse
floor input; it does not test the benefit of label-derived floors.

The next floor experiment must introduce an explicitly named label-derived metric,
retain explicit versus inferred provenance and reviewed numbering exceptions,
then compare its cumulative increments and elevator interaction. Missingness
reports must state the measurement stage and dataset rather than implying that
the label extraction itself failed.

## Thomas Eddy 2C: manual studio determination

Ben's manual review resolves the bedroom conflict for advertisement **3223153**,
canonical unit `the-thomas-eddy/2c`, capture 68524. The structured count was one;
the preserved description says “Beautiful Studio in Prime Chelsea!” The correction
records **zero bedrooms** in an append-only ledger at
`config/reviews/chelsea-thomas-eddy-studio-20260919.jsonl`.

It targets the exact reviewed analytical row version, rather than asserting a
physical conversion date or modifying other advertisements. The replay script
`docs/analysis/scripts/record_thomas_eddy_studio.py` publishes original and corrected
values, source hashes and correction provenance in
`data/model/chelsea-thomas-eddy-studio-review-20260919`. Repeating it does not
append another edit. **The correction is recorded and verified; incorporation
into the next full analytical dataset and a refit remain pending.** The selected
posterior still reflects the original count and must not be described as corrected.
This is distinct from advertisement 5155021's unresolved bedroom conflict.

## Elevator evidence policy

Use StreetEasy building-page tax class, NYC Department of Finance building class
and DOB elevator device/filing records in addition to listing descriptions.
[DOF's classification table](https://www.nyc.gov/assets/finance/jump/hlpbldgcode.html)
distinguishes walk-up and elevator apartment classes.
[DOB's public portal guide](https://www.nyc.gov/site/buildings/industry/dob-now-public-portal-faqs.page)
explains address/BIN/device searches and the split with historical BIS records.
These are complementary sources; no new building-specific adjudications have
been made from them in this update.

Bind evidence to building identity (including alternate addresses, BIN and BBL),
record type and time. Preserve conflicting assertions for review. Distinguish
passenger elevator access from other device types; no search match is not proof
of absence, and a contemporary classification does not establish every historical
listing's elevator state. Collect building records through Oxylabs. The legacy
`apartments.nyc.fetch_pluto` still calls NYC directly and must be adapted before
use under the project's all-scraping-through-Oxylabs instruction.
