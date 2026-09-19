# Scoped laundry extractor: first validation

The experimental extractor preserves private equipment, shared building
facilities and same-floor access separately, with exact source pointers/spans.
It derives the most convenient reported option after checking conflicts.
Unknown remains distinct from explicit absence. Structured equipment claims
alongside hookup-only prose require review. This is not yet a model input.

Twenty-seven focused tests pass. Replaying all 724 captures from the existing
phrase audit uses the same-capture structured laundry assertions and recovered
literal descriptions, with source hashes and identities checked. The replay
reconstructs only those audited fields, not a complete raw listing.

Of the 20 shared same-floor claims in the 36-case development review, 18 are
detected. The two misses concern full laundry facilities down the hall and a
coordinated list of amenities reached on the same floor. None of the other
16 development cases is assigned a positive same-floor claim. These examples
informed the rules and cannot estimate independent accuracy.

A frozen sample from buildings outside that development review contains 16
cases across 11 buildings. Manual review finds:

- Three misses among four positive same-floor claims, including “laundry with a
  brand new washer and dryer on your floor” and coordinated laundry/roof-deck
  wording.
- One missed shared-room denial: “No Laundry Room On-Site.”
- All four hookup cases flagged for installation review.
- No unsupported same-floor positives among these selected cases. Four examples
  correctly keep “trash disposal on every floor” separate from on-site laundry.

This small, deliberately selected sample contains repeated building copy. It is
neither a full-corpus accuracy estimate nor a sufficient validation for fitting.
Changes made using its labels turn it into development evidence for the next
extractor. Broader positive/negative review and capture reconciliation are still
needed, including relative floor wording and explicit absence scope.

The lexical-candidate replay produces the following provisional support. Units
and buildings can appear in multiple categories across captures; these are not
mutually exclusive full-cohort model counts.

| Reported option | Captures | Units | Buildings |
| --- | ---: | ---: | ---: |
| In unit | 47 | 28 | 10 |
| On floor | 356 | 148 | 19 |
| In building | 50 | 32 | 14 |
| Explicit none | 19 | 8 | 6 |
| Unknown or withheld | 252 | 131 | 73 |

Explicit-none candidate support is particularly small. It needs direct scope
review and overlap checks before estimating a distinct price contribution.
No four-level fit, analytical projection, source correction or main-model change
has been made from this extractor.

Artifacts: `data/model/chelsea-scoped-laundry-evaluation-20260919` contains all
capture outputs and the frozen validation sample;
`data/model/chelsea-scoped-laundry-validation-20260919` contains the 16 manual
decisions and disagreements. Both archive their generating scripts and bind
their inputs. The evaluation also archives the exact extractor used.
