# Laundry measurement policy for the next experiment

The existing Bayesian comparison is **reported in-unit versus reported
in-building laundry**, with a separate unknown indicator. Its +2.399% contrast
(95% credible interval +2.051% to +2.741%) is not a four-level result. The next
measurement version should separate the following claims before fitting.

| Candidate level | Evidence required | Common ambiguity to preserve |
| --- | --- | --- |
| No on-site laundry | Explicit denial covering both unit and shared on-site facilities | “No washer/dryer in unit” does not deny building laundry; “no building laundry” does not necessarily deny private equipment |
| In building | Installed shared facilities accessible to this residence | An unspecified laundry-room floor does not establish same-floor access |
| On floor | Shared installed facilities on this apartment's floor, or a credible each/every-residential-floor claim | “Across the hall” may describe a private laundry nook or another amenity |
| In unit | Installed private equipment serving this residence | Hookups, permission to install, proposed equipment and a washer without a stated dryer need separate evidence |
| Unknown | No adequate claim, unresolved contradictory claims, or ambiguous scope | Unknown must not become the no-laundry reference group |

Retain independent tri-state claims for private equipment, shared building
facilities and same-floor access, together with equipment type, restrictions,
planned/installed status, literal spans, capture identity and knowledge clocks.
Same-floor shared access implies building access; it does not imply private
equipment. Explicit absence remains scoped to the statement's subject.

Facilities may coexist. For a compact four-level experiment, a **most convenient
reported option** can be derived in the order in-unit, on-floor, in-building,
explicit none. Name that measurement honestly: a shared-laundry claim does not
prove that unmentioned private equipment is absent. Preserve the other facility
claims and review whether a separate coexistence indicator is supported. A
convenience ordering does not require monotone price coefficients.

Before deriving categories, resolve contradictory evidence. A positive structured
washer/dryer flag alongside hookup-only prose is a conflict to review against the
exact capture; neither channel automatically overrides the other. Do not
propagate a latest listing's facilities backward or treat a changed description
as a dated installation/removal. Any accepted correction belongs in the overlay.

The [first source review](../analysis/chelsea-laundry-location-2026-09-18.md)
contains 36 development cases and six hookup-only examples currently represented
as in-unit laundry. Validate the next extractor on different units and buildings,
including negative and unrelated hallway examples. Report errors by claim scope,
not just agreement with the old category.

Freeze the revised measurements before a matched PyMC comparison. Use the same
rows, nonlaundry terms, likelihood and group priors. First compare the previous
encoding with the reviewed encoding; then test whether splitting shared
building/floor access adds useful information. Report joint category contrasts,
distinct-unit and building overlap, sensitivity to category priors, changed
current residuals and the largest affected unit/building effects. Sparse explicit
none or on-floor evidence may justify deferring an effect rather than forcing
four coefficients. No four-level fit or accepted new encoding is claimed here.
