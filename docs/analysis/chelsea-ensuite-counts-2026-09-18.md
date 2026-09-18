# En-suite counts: what the archived descriptions identify

The descriptions support some exact **advertised** inventories, but most useful cases identify only a lower bound. A new 30-unit context review found five exact advertised inventories, 14 lower bounds, and 11 unknown counts. Two exact-inventory cases conflict with the structured full/half bathroom totals, leaving three unconflicted exact claims. The reviewed cases do not yet identify an exact-count price contrast at the same bedroom/full-bath/half-bath configuration.

This research adds no model feature, inferred zero, correction, or price fit. Source claims remain distinct from independently verified physical layouts.

## Source, screen, and independent sample

The candidate screen verifies the immutable description and bathroom-audit bundles for all 52,712 reviewed-v3 observations and 71,922 captures. It searches different phrase structures rather than treating every occurrence of “en-suite” as the same measurement.

| Phrase family | Candidate rows |
|---|---:|
| Numeric phrase near en-suite | 541 |
| Both / each / every / all near bathroom or en-suite | 1,618 |
| Primary / master near en-suite | 1,205 |
| Hall / hallway / guest / shared bathroom | 199 |
| En-suite bedroom, laundry, washer, or other ambiguous subject | 67 |
| Potential / can / could / conversion near en-suite | 38 |
| No / not / without near en-suite | 2 |

There are 3,051 distinct candidate observations and 4,008 candidate captures across overlapping families. Counts are screening support, not verified en-suite prevalence. Numeric cues sometimes count closets; distributive cues often describe finishes rather than access.

The initial deterministic screen selects six distinct units per conceptual stratum, excluding all 25 units in the preceding en-suite review. The final 30-case adjudication makes one explicit coverage adjustment: replace two routine “can fit a bed” cases with both negation-wording candidates. The replacement IDs and selection seed are preserved in the review artifact. The final set still contains 30 distinct units and zero overlap with the preceding 25-unit review. Every final selected description was read in full, in addition to reviewing the exact candidate offsets.

This is a purposive, stratified development review. Its fractions are not population precision, recall, prevalence, or independent physical validation.

## What “count” means

The review target is distinct bathrooms explicitly described as attached to bedrooms. Fixture composition is separate: an access claim does not itself establish full versus half bath, shower availability, or number of sinks.

- **Exact advertised count:** the description enumerates a complete bathroom inventory and identifies the bedroom-associated en-suite baths. The statement can still be erroneous or conflict with structured data.
- **Lower bound:** one or more distinct en-suite bathrooms are explicitly identified, but other bathroom access is unspecified. A primary en-suite claim is usually “at least one,” not “exactly one.”
- **Unknown:** wording refers to laundry, closets, finishes, implicit bedroom labels, assigned private bathrooms without direct-access wording, or shared facilities. No zero is imputed.

The complete-enumeration cases illustrate the distinction:

| Advertisement | Advertised en-suite inventory | Structured full / half | Assessment |
|---|---:|---:|---|
| 2657511 | 3 | 3 / 1 | Three bedrooms all explicitly have full en-suite baths, plus a separate powder room. |
| 4241364 | 2 | 2 / 1 | Two bathrooms plus a powder room; both bedrooms explicitly have their own en-suite baths. |
| 1868905 | 4 | 4 / 1 | Primary en-suite plus three additional bedroom suites each with an en-suite, plus powder room. |
| 1893537 | 3 | 4 / 1 | Description says three bedrooms, all with en-suites, and 3.5 baths; structured total is 4.5. |
| 2770271 | 2 | 2 / 0 | Both named bedrooms have en-suites and a separate powder room; text says 2.5 baths, unlike structured 2.0. |

Only 2657511 explicitly labels the enumerated en-suite baths as **full** baths. The generic access counts in other cases should not automatically become “full en-suite counts” just because the row also has structured fixture totals. Those totals require their own provenance and contradiction checks.

## Ambiguities that matter for modeling

Advertisement 3738463 explicitly identifies two en-suites but only says the third bedroom “has a bathroom.” Its defensible explicit-access measurement is at least two, not an exact total of two. Advertisement 1639871 describes a primary en-suite and a nearby hall bath used by the office/guest room. It is a promising floor-plan review case, but hall access alone does not prove there is no additional connecting bedroom door. Guest use likewise does not establish non-en-suite status.

Advertisement 4068484 says each bedroom has its own bathroom. That establishes a claimed assignment or private-use arrangement but does not unambiguously state direct attached access. Advertisements 2672605 and 3518641 enumerate en-suite **bedrooms**, with an implicit bathroom subject; the strict review retains these as bedroom-access candidates rather than explicit bathroom counts.

The two negation-wording candidates provide no zero examples. Advertisement 1421091 says there is “no shortage of closet space” before describing an en-suite. Advertisement 3180057 says the primary suite “wouldn't be complete without” an en-suite, an affirmative marketing idiom. Neither is a negative bathroom-access statement. This search found no supported zero-en-suite claim; it does not prove such layouts are absent.

En-suite laundry (2996820) and en-suite washer/dryer (2886972) are not bathroom features. The conditional case 4794032 describes an existing upstairs en-suite next to a bedroom that can be fully enclosed; the proposed enclosure affects bedroom privacy, not necessarily the existence of the bathroom. A blanket “can” exclusion would misclassify it.

## Support at the same bedroom/full/half configuration

The following counts use **all 71,922 verified descriptions**, joined to the 52,508 complete, unflagged bathroom-composition rows in the separate reviewed bathroom projection. The phrase screen here is deliberately narrow: directly adjacent en-suite [full/master/primary] bath wording. Rows without that phrase retain unknown access; they are not non-en-suite controls.

| Bedrooms / full / half | Rows with direct phrase | Other rows, access unknown | Buildings containing both reporting groups |
|---|---:|---:|---:|
| 1 / 1 / 0 | 60 | 20,854 | 25 |
| 2 / 2 / 0 | 595 | 4,443 | 104 |
| 2 / 2 / 1 | 281 | 413 | 36 |
| 3 / 3 / 0 | 105 | 345 | 25 |
| 3 / 3 / 1 | 138 | 101 | 19 |

These cells provide candidates for a matched source review, especially two-bedroom/two-full-bath apartments. They identify variation in **reporting**, not verified variation in the number of en-suite bathrooms.

Within the adjudicated 30-unit set, no same-bedroom/full/half cell has two unconflicted exact inventories with different en-suite counts. The common two-bedroom/two-full/no-half cell contains lower bounds and unknowns, plus one exact advertised count whose half-bath total conflicts with structured data. A lower bound of one can still describe a unit with two en-suites. Fitting those values as 1 versus 2 would create a false composition contrast.

## Additional source problems found

- **2391038 and 2573882**, at 310 West 20th Street, explicitly advertise shared bathrooms despite structured full=1/half=0. These are additional exact advertisements beyond the preceding shared-access revision; no blanket building rule follows.
- **1893537 and 2770271** have the structured/text count contradictions above.
- **3886754** describes a two-bedroom/two-bath unit but reports two full plus one half structurally; its primary en-suite claim is a lower bound and does not resolve that discrepancy.

Exact selected capture IDs, raw/body/description hashes, full descriptions, context offsets, and review interpretations are retained. None of these findings applies an automatic correction or extends an existing decision bundle.

## Practical recommendation

Keep a measurement record with `exact_count`, `lower_bound`, or `unknown`, the source-scoped count/bound, bedroom attachment wording, fixture-type evidence, and planned/existing status. Preserve all count contradictions. A descriptive “explicit en-suite bathroom advertised” experiment is possible, provided it is presented as a wording association with reporting selection, not a physical premium or a substitute for count analysis.

For actual composition contributions, first adjudicate a focused set within the two-bedroom/two-full-bath cells, obtaining complete access inventories where possible. Seek explicit independent evidence for one-en-suite-plus-hall layouts as well as all-en-suite layouts; do not manufacture zero labels from missing descriptions. Floor plans, when already archived and interpretable, can help establish connections. Broader Bayesian uncertainty does not repair a mislabeled count. An eventual model that uses bounds must explicitly model their incomplete measurement rather than treating bounds as observations of the true count.

## Reproducibility

- Screen: `models/ensuite_count_audit.py`; artifact `data/model/chelsea-ensuite-count-evidence-20260918-v2`.
- Authoritative review: `data/model/chelsea-ensuite-count-review-20260918-v3`.
- `review.jsonl` records adjudication under `interpretation`, retaining the exact source and candidate spans. Its status distinguishes text review from physical verification.
- `candidate-cell-support.json` uses the complete description inventory; `review-cell-support.json` reports actual adjudicated count support.
- Earlier development artifacts are superseded. The authoritative versions use JSON-normalized selection metadata for exact replay and the complete source inventory for phrase-support counts; adjudicated classifications are unchanged.

Six focused screen tests pass, covering exact offsets, candidate-only semantics, misleading negation/non-bath/distributive wording, exclusion of previously reviewed units, deterministic selection, insufficient-support failure, and an end-to-end source-bound publication/replay regression. The full-source screen and adjudicated review both replay exactly against their published bundles. The combined bathroom/revision/en-suite test set has 34 passing tests. No scraping, fitting, feature promotion, or frozen-model changes were performed.
