# Chelsea: outdoor evidence, contributions and residuals

Outdoor-feature estimates depend materially on how source claims are accepted.
Eighteen matched fits show a terrace-versus-balcony contrast near **3%** using
structured labels, versus **5–7%** when private types require explicit text
corroboration. Garden-versus-balcony contrasts change even more. These are
conditional associations among advertised type subsets; they do not yet support
settled physical amenity values.

The main reviewed analysis model remains
`data/model/chelsea-reviewed-analysis-20260918-v3`. Both outdoor experiments are
research artifacts. They retain the same 52,712 observations, all 13 current
captures, original asking prices, and prior interior inputs.

## Why this iteration

The [interior experiment](chelsea-interior-model-2026-09-18.md) found that seven of
eight triplexes with the largest fitted changes also advertise private outdoor
space. That suggested an omitted-feature explanation for part of the level-count
contrast. This iteration examines that mechanism through source review, matched
fits and changed residuals, rather than selecting features by fit error alone.

## Source evidence and two policies

The audit binds 71,922 captures to the fitted cohort, preserving original body
and parsed-record hashes, descriptions, structured field paths, capture clocks
and interpretation versions. Empty arrays remain unknown. Garden views do not
imply garden access; roof rights do not imply a usable roof deck. No claim is
copied across advertisements, and historical physical effective dates remain
unverified.

Structured fields report private outdoor categories on 15,125 rows and shared
categories on 25,396. A deterministic development review inspected 45 cases:
30 private and 15 shared categories. Only ten of the 30 private cases contained
explicit matching private-type wording in the inspected text. Missing wording
does not prove absence. However, examples paired private-garden codes with shared
gardens or garden views. Rechecking four original archived bodies confirmed that
these fields came from the source, rather than an extraction error.

Two policies therefore remain visible:

1. **Structured:** use recognized reported private/shared type combinations;
   unresolved codes block the category, while generic presence is unspecified.
2. **Text corroborated:** retain a private type only when the same capture has
   both its structured code and accepted explicit private/own wording. Shared
   categories retain the structured policy. Known private coverage falls to
   1,964 rows. Supported types may be retained alongside an unresolved code;
   that code itself is never interpreted as usable space.

Review of 25 accepted corroborated cases found supporting private/own wording
in each inspected example. This is agent development review, not an independent
precision estimate. The rule is deliberately narrow: it misses implied access,
can reject genuine coexisting shared/private spaces, and can retain only part of
a multi-feature description. Its categories are reported subsets, not complete
inventories. The resulting missingness is strongly selective.

Outdoor-area wording occurs on 1,440 rows. Review of 20 deterministic units plus
16 extreme/scope cases (31 unique units in total) found unit-private areas,
building roof decks, aggregate terrace areas and lower bounds. For example,
12,000 square feet described as private outdoor space belongs to building-wide
roof facilities, while another advertisement describes 7,000 square feet across
six unit terraces. **Outdoor area is excluded from these fits** pending better
scope and measurement handling.

## Matched fits

Each policy compares the prior interior model, outdoor reporting indicators,
and known-only centered outdoor type contrasts. Three building/unit penalty
settings test contribution sensitivity. Rare categories with fewer than 25 rows
are pooled. Unknown is never encoded as physical absence. All results below are
descriptive in-sample diagnostics.

| Policy | Building/unit penalties | Types log RMSE | Triplex vs duplex | Terrace vs balcony | Garden vs balcony |
| --- | --- | ---: | ---: | ---: | ---: |
| Structured | 2 / 2 | 0.093751 | +8.902% | +2.813% | +1.381% |
| Structured | 10 / 8 | 0.120326 | +10.052% | +2.938% | +1.337% |
| Structured | 50 / 40 | 0.145494 | +10.859% | +2.844% | +1.443% |
| Corroborated | 2 / 2 | 0.094107 | +8.937% | +4.813% | +5.318% |
| Corroborated | 10 / 8 | 0.121208 | +10.463% | +6.099% | +7.815% |
| Corroborated | 50 / 40 | 0.146858 | +11.601% | +7.364% | +10.622% |

At standard penalties, interior-only log RMSE is 0.121983. Outdoor reporting
alone yields 0.121012 under the structured policy and 0.121590 under corroboration.
Type values improve fit beyond those reporting controls, but the lower error of
the structured policy does not establish that its physical interpretation is
correct. Source quality and selection both affect these comparisons.

The predominantly triplex-versus-duplex contrast falls from 11.702% to 10.052%
or 10.463% at standard penalties. Outdoor terms explain some overlapping price
variation without resolving sparse within-building level support or other luxury
features. The contrast remains unsuitable as a general value of adding a level.

## Follow the changed residuals

Switching policy changes fitted rent by a median absolute **$24.45**, with a
maximum of **$2,119.17**. Review of the six distinct units with the largest changes
found that absolute residuals improved for one and worsened for five:

| Advertisement | Ask | Structured fit | Corroborated fit | Source finding |
| --- | ---: | ---: | ---: | --- |
| 610152 | $49,000 | $23,413 | $21,293 | Two terraces described with misspelled private wording; only generic structured presence. |
| 4015554 | $48,000 | $35,977 | $34,105 | Townhouse terraces, yard and pool; no direct private qualifier. |
| 2549061 | $48,000 | $38,586 | $40,403 | Explicit private terraces; category unchanged, so movement reflects the global refit. |
| 4892020 | $42,500 | $32,359 | $30,573 | Private balcony retained; doors to landscaped garden omitted by strict rule. |
| 4222933 | $9,750 | $11,904 | $13,673 | Private balconies/roof deck corroborated despite an additional unresolved roof-rights code. |
| 2730313 | $39,500 | $36,313 | $34,607 | Terrace off living room plus garden views; stricter rule misses plausible unit access. |

These selected cases are not a representative performance sample. They reveal
both ambiguous structured labels and conservative text recall. No source prices,
cohort membership or correction overlays changed. Advertisement 2730313 also
contains condominium offering boilerplate; rental scope needs separate review
before considering an exclusion. Whole-house elevators, private pools and outdoor
area remain plausible omitted distinctions.

The next measurement revision should distinguish explicit private claims,
unit-access claims, shared facilities, views and unresolved scope, with source
confidence separate from physical features. Validation should include implied
access and coexisting private/shared amenities outside the development cases.

## Artifacts and validation

- Evidence: `data/model/chelsea-outdoor-evidence-20260918`.
- Structured source review: `data/model/chelsea-outdoor-source-review-20260918`.
- Structured projection: `data/model/chelsea-outdoor-projection-20260918`.
- Corroborated projection: `data/model/chelsea-outdoor-corroborated-projection-20260918`.
- Corroborated source review: `data/model/chelsea-outdoor-corroborated-review-20260918`.
- Nine structured fits: `data/model/chelsea-outdoor-structured-experiment-20260918`.
- Nine corroborated fits: `data/model/chelsea-outdoor-corroborated-experiment-20260918`.
- [Full comparison and all current captures](../../data/model/chelsea-outdoor-policy-comparison-20260918/report.md).
- Six changed-residual reviews: `data/model/chelsea-outdoor-changed-review-20260918`.

Structured protocol SHA-256:
`eef7972a6d12d3bfd2edea3e054946a3fada35733bf312ea7d685674ef645417`.
Corroborated protocol SHA-256:
`274d4b7b6fe706a0059a740cf330223654a142ddaeb90253e63723931a0b34cc`.

All 18 fits completed; saved model reloads reproduce fitted values. All six
interior reference fits reproduce the earlier interior experiment exactly.
Evidence, corroborated projection, both experiments and the comparison report
passed exact replay. The full suite passed **724 tests, with two skipped**;
the report was additionally exercised against both complete experiments.
