# Bathroom evidence and research directions — Chelsea, 2026-09-18

Separate reported full and half bathroom counts are available in the existing raw data. The old analytical scalar collapses these fields to `full + 0.5 × half`; it is not sufficient to reconstruct the original counts. This audit recovers the explicit source reports for the same 52,712 fitted observations and changes no rent, cohort membership, or existing feature.

## Source and identifiability

The verified description archive contains 71,922 captures for the reviewed v3 cohort. Every raw capture contains the keys `/propertyDetails/fullBathroomCount` and `/propertyDetails/halfBathroomCount`; the latter is sometimes null. No `bathroomCount` key or other bathroom-named structured field was found in these captures.

The source-bound projection exposes:

- `reported_full_bathrooms`: known for 52,712 rows.
- `reported_half_bathrooms`: known for 52,555 rows; unknown for 157 rows whose captures have null half counts.
- `bathroom_count_evidence`: per-field consensus status, exact capture IDs, and review flags.

Counts must be explicitly reported nonnegative integers, consistent across every capture of the same advertisement. Each field is evaluated separately, so a null half count does not erase an explicitly reported full count. There are no observed capture conflicts. For the 52,555 complete pairs, recombining the fields reproduces the analytical scalar exactly. **That agreement verifies transformation consistency, not the correctness of the source.** No missing count was inferred from the scalar, no null was interpreted as zero, and no description-based correction was applied.

These are retrospective same-advertisement attributes, frequently captured after the initial asking-price event. Same-advertisement identity does not prove that a layout was unchanged throughout the historical interval.

## Source review changes the modeling plan

Thirty-three rows report multiple half baths; four of these also report zero full baths. A review of all 33 descriptions found a mixture of valid layouts, source errors, scope errors, and unresolved cases. The immutable review also adds one shared-bath advertisement found by the phrase screen.

| Advertisement | Reported full / half | Source evidence | Consequence |
|---|---:|---|---|
| 3184136 | 2 / 5 | Describes a two-and-a-half bath home and powder room | The integer five is not a reliable physical half-bath count. |
| 4181206 | 1 / 5 | Describes a three-bedroom, 1.5-bath apartment | Same apparent decimal-entry error; do not automatically repair every five. |
| 1945700 | 1 / 2 | Explicitly describes one full and two half baths | Two half baths can be real; scalar 2.0 loses the layout distinction. |
| 2762077 | 2 / 2 | Explicitly describes two baths and two powder rooms | Another corroborated multi-half layout. |
| 1453421 | 0 / 2 | Describes two full bathrooms | Zero-full does not necessarily mean no private shower. |
| 3303145 | 0 / 2 | Explicitly nonresidential, office use only | Existing cohort scope problem, not an amenity premium. |
| 2533438 | 0 / 2 | Studio with shared bathrooms | Bathroom access must be represented separately from fixture totals. |
| 2430461 | 1 / 0 | Two full and two half baths shared with other apartments on the floor | Even an ordinary-looking count pair can conceal shared external bathrooms. |

Across the 34 reviewed issue cases: 18 explicit count contradictions, two corroborated multiple-half layouts, one nonresidential case, two external-shared-bath cases, one planned-layout contradiction, one internally inconsistent description, one quantity ambiguity, and eight unresolved cases. These are selected issue cases, not an error-rate estimate. Exact descriptions, capture identities, raw/body/description hashes, and review notes are retained in the source-review bundle. No quarantine or correction is enacted by this audit.

For an initial sensitivity fit, treating flagged bathroom composition as unknown is more defensible than taking large reported half counts literally. It also retains the advertisements for other terms. Scope exclusions and affirmative count corrections should be explicit separate decisions. Ordinary unflagged counts remain source claims; the shared-bath example shows that the numeric screen cannot certify them.

## Support for separate increments and bedroom/bathroom balance

Among 52,522 rows with complete, unflagged count pairs:

| Candidate contrast | Positive rows | Buildings with within-building variation | Units with reported variation |
|---|---:|---:|---:|
| At least one half bath | 2,696 | 313 | 195 |
| More than one full bath | 9,625 | 457 | 258 |
| More than two full baths | 1,064 | 152 | 25 |
| More than three full baths | 119 | 42 | 8 |
| More than four full baths | 14 | 5 | 0 |

Reported variation can reflect renovation, advertisement errors, or changing attribution; it is not proof of a physical transition. High increments have thin support and should carry greater uncertainty/partial pooling.

A research design can replace the current linear scalar term with full-bath threshold increments and a separate half-bath term, followed by a bedroom-dependent full-bath increment. Keep explicit missingness and source-quality sensitivity visible. The desired comparison is the same-bedroom contrast from one fewer full bathroom than bedrooms to equal counts, versus equal counts to one additional full bathroom. Estimate these at supported bedroom counts rather than averaging studio, one-bedroom, and large-apartment configurations together.

Raw net-count support is: −1 = 7,300 rows; 0 = 28,103; +1 = 14,695. The +1 group includes studios with one full bath, so these totals are not matched comparison groups. A linear `full bathrooms − bedrooms` term is an exact linear combination of linear bedroom and full-bath terms; adding it does not identify a separate balance effect. Nonlinear deficit/surplus terms or explicitly pooled bedroom-by-full-bath cells provide the needed flexibility. Check rank and posterior dependence, and report row, unit, and building support for each requested contrast.

## En-suite access: promising, not ready as a physical count

The broad `en suite` / `en-suite` / `ensuite` screen matches 2,192 rows, 1,256 units, and 279 buildings. An additional deterministic 25-unit review, selected with a different hash seed from the five-case initial sample, found 24 explicit bathroom-access claims and one implicit “ensuite master bedroom” clause without an explicit bathroom noun. These are text-support counts, not independent physical validation or population precision. Sampling seed-positive text says nothing about recall; missing wording remains unknown.

Advertisement 1900095 describes a downstairs half bath with a tiled stall shower. This illustrates why bathroom **access**, fixture composition, and marketing labels require separate fields. A first conservative feature could be “explicitly advertised bedroom en-suite bathroom,” with source text and scope, rather than a total en-suite count or an assumption that unmentioned bathrooms are hall baths. The initial five-per-family review also found two “Jack and Jill” cases referring to sinks rather than shared bedroom access. The exact object matters.

## Varied seed phrases and testable research ideas

The audit deliberately searches different concepts, including low-price constraints as well as luxury amenities. Sixty-five deterministic cases (five distinct units per family, 65 unique units overall) were reviewed in context. Candidate counts describe wording, not verified feature prevalence.

| Seed family | Candidate rows | Research question and next measurement step |
|---|---:|---|
| Full bath / half bath / powder room | 3,107 / 686 / 661 | Do separate full-bath increments and half-bath access explain residuals better than fractional scalar totals? Reconcile explicit source/text contradictions first. |
| En-suite / shared, hall, guest, private bath | 2,192 / 259 | Does bedroom-private access matter beyond counts, and do externally shared facilities explain unusually low asks? Distinguish shared within a unit from shared with other units. |
| Double vanity / separate shower / soaking tub | 3,089 | Are fixture quality and usable simultaneous capacity explaining apparent en-suite premiums? Separate fixture luxury from access. |
| Split bedrooms | 391 | Does bedroom separation command a premium at the same counts and approximate size, especially for two-bedroom homes? Inspect whether the advertised layout exists or follows a conversion. |
| Railroad / walk-through bedroom | 150 | Does circulation through a bedroom explain low residuals or reduced roommate suitability? Reject neighborhood references to the High Line's railroad history. |
| Convertible / flex / temporary walls | 1,356 | Does marketed bedroom count exceed existing enclosed sleeping rooms, confounding bedroom and bathroom balance? Record current versus proposed partitioning rather than asserting legal bedroom status. |
| Home office / den / windowless | 2,344 | Does usable non-bedroom space explain high residuals among one-bedroom units? Keep actual extra rooms distinct from staged work areas and convertible bedrooms. |
| Quiet / soundproof / noise / interior-facing | 6,335 | Is acoustic privacy an omitted unit effect, and does it trade off against light? Reject “whisper-quiet dishwasher” and distinguish street marketing from physical insulation evidence. |
| Open or unobstructed views / air shaft | 1,314 | Does obstruction modify the contribution of compass exposure or floor? Separate unit view from shared-roof views and avoid assuming permanence. |

Prioritize source verification on units with large unit effects and residuals, but retain an independent sample of ordinary cases. Selecting all feature definitions from extremes can overfit the review process itself. For each hypothesis, compare a reporting/knownness term with the proposed feature value, inspect effects within buildings, and examine how residuals move for the source-linked review cases.

## Reproducible artifacts

- `data/model/chelsea-bathroom-evidence-20260918`: verified raw bathroom fields, phrase candidates, exact offsets, original description provenance, frequency/support, deterministic review sample.
- `data/model/chelsea-bathroom-projection-20260918`: all 52,712 original observations plus explicit reported counts and source flags.
- `data/model/chelsea-bathroom-source-review-20260918`: 65 phrase reviews, 34 source-quality issue cases, and model-design support.
- `data/model/chelsea-ensuite-text-review-20260918`: separate 25-unit en-suite text review and its limitations.

Implementation: `models/bathroom_evidence_audit.py` and `models/bathroom_projection.py`. The new focused checks cover missing versus zero, multiple half baths, capture disagreements, exact text offsets, and preserving original analytical fields. Eighteen focused tests pass. No scraping, fitting, model-runtime changes, or automatic corrections were performed by this research task.
