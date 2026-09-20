# Residual-driven residential-scope revision

The [full residual-tail review](../analysis/chelsea-expanded-fit-residual-research-2026-09-19.md)
identified four advertisements whose own evidence warrants exclusion from
residential, location-dependent apartment-price attribution. This experiment
changes their analytical membership, preserves every source row and capture,
and keeps the PyMC spline specification fixed.

## Decisions and temporal scope

| Advertisement | Residual rank | Decision | Own-source basis |
|---|---:|---|---|
| 1260588 | 6 | Nonresidential scope | Professional loft explicitly offered for business use. |
| 937046 | 7 | Nonresidential scope | Equipped restaurant, liquor rights, key money and commercial rent plus taxes. |
| 609730 | 12 | Unresolved location | Raw address 130 W30; description explicitly places the loft in Greenwich Village across from Blue Note. |
| 2993341 | 14 | Unresolved location | Raw address 133 W14; description explicitly names 145th and Malcolm X Boulevard and nearby uptown parks. |

All four are historical initial-own-advertisement asking-price observations.
Seven attached captures were reviewed in full and their exact raw-listing hashes
rechecked against the canonical archive. The review clock is
`2026-09-20T01:32:42Z`. Same-advertisement descriptions were captured later than
the initial price dates; this review changes analytical membership at its review
clock, not physical-use or location history at those earlier dates.

The policy is `config/reviews/chelsea-residual-scope-20260919.json`. Decisions bind
the exact row, every typed capture identity, both floor-provenance capture
hashes, complete descriptions, literal spans, raw JSON witnesses and clocks.
The source is the accepted `chelsea-expanded-label-floor-analysis-20260919`,
manifest SHA-256
`d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`.
Residual magnitude selects the review queue; it is not the exclusion rule.

The ambiguous 500 W21 access case, SRO/shared-bath product case, income-restricted
offers and unsupported extreme prices remain separate research questions. This
revision does not guess replacement addresses, alter asking prices, change
bathroom counts, or remove other advertisements for a reviewed unit or building.

## Transformation contract

`reviewed-residual-scope-projection-v1` is an outer membership projection over
the frozen expanded-floor source. The four unchanged excluded rows retain their
original positions and full decisions in `residual-scope-quarantine.jsonl`.
Every retained row is unchanged, and both floor sidecars plus the earlier
quarantine and elevator sidecars are copied intact. The inverse must reconstruct
the exact ordered parent observations and then replay the complete older chain.

The output is `data/model/chelsea-residual-scope-analysis-20260919`; the decision
bundle is `data/model/chelsea-residual-scope-decisions-20260919`. Identical reruns
must verify and reuse their completed artifacts. Later scope decisions should
accumulate against the same expanded base, rather than recursively nesting this
scope version or mutating earlier outputs. The previous selection and all
excluded observations remain available for comparisons or policy reconsideration.

The decisions and source publication completed successfully: **52,649 rows,
22,152 units and 1,129 buildings**, with all **172 captured-current rows**
unchanged. The publisher reconstructed the exact expanded parent and replayed
the complete older source chain. The new source manifest SHA-256 is
`0cf701ba314c722dc90bc8c64f5dedc2609fb891430eb37c90ad40eb4e588267`;
its observation hash is
`4f8d54497a91076a40ecc25b043ea21e3e26e4d42617772d4565745b95c8da17`.
The decision manifest is
`800d487e681dbdc947a44a4a948ab0328718e2942a6fe37a235dabe32a82cd3a`.

Contract tests passed (64), reader integration/regression checks passed (275),
and publisher preservation/idempotence/failure checks passed (3). The existing
selected expanded-floor posterior also loaded successfully after the reader
changes. The actual full-source replay, design/evidence and graph preflights are
running; these checks do not yet establish a completed new posterior.

## Matched full PyMC fit

Before fitting, verify exact source reversal, unchanged retained description
evidence, all 172 capture-time ACTIVE observations, feature support and design
rank. Reconstruct both designs and report centering, scale, category frequency
and size-reference changes. Removing observations can change normalization even
when all retained raw values and statistical code are identical. Verify floor
knots, basis and induced contrast priors explicitly. Run the full direct versus
compressed PyMC log-density/gradient check on the new cohort.

Use the same natural spline with coordinate prior scale 0.10, reference floor 2,
full/half-bath balance specification, shared Student-t residual scale, building
prior scale 0.35 and unit prior scale 0.25. Retain four chains, 4,000 warmup and
6,000 retained draws per chain, nutpie/Numba diagonal NUTS, target acceptance
0.93, maximum depth 10 and seed 20260924. No surrogate or short-fit speed claim.

Planned fit: `data/model/chelsea-bayesian-residual-scope-spline-disk-20260919`.
Reference fit: `data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919`.
Producer implementations must remain frozen throughout sampling and publication.

## Assessment and selection

Require the same parameter, derived-contribution and joint-floor convergence
gates. Use `models.residual_scope_fit_comparison` to compare common observations
separately from excluded rows. Removing four extreme residuals necessarily
changes the evaluated cohort; an aggregate error decrease over different rows
is not evidence that the pricing model improved.

Compare fitted-price movements, floor curves and physical bedroom/bathroom and
amenity contrasts within each joint posterior, plus building effects against a
common reference. Keep source-derived scaling changes visible and never pair
draws from independent fits. Reuse the fixed development panels, review large
movements and the newly exposed residual tail, and preserve source annotations
in the actual contribution/counterfactual UI before considering promotion.

The selected expanded-floor fit remains in place until these steps are complete.
This experiment does not resolve the broader eligibility, SRO, terrace/duplex,
bathroom-composition or floor/elevator research questions.
