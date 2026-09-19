# Floor model geometry and specification review

The expanded floor model passes its completed convergence checks, but its
parameterization and prior specification deserve revision before promotion.
Raising the tree-depth ceiling solved a truncation problem; it did not establish
that the model is well specified or computationally efficient. The main model
selection remains unchanged. The running elevator comparison is a diagnostic
experiment, not an automatic promotion candidate.

## What the completed draws show

The source cohort is unchanged at 52,653 advertisements, 22,155 units and 1,129
buildings. Floor extraction increased known-floor rows from 349 to 29,907. This
review concerns the resulting model, not a reversal of that source extraction.

| Retained trajectory work | Previous sparse-floor fit | Expanded floor fit |
|---|---:|---:|
| Median leapfrog steps | 63 | 127 |
| Mean leapfrog steps | 63 | 289.97 |
| 99th percentile steps | 63 | 4,095 |
| Transitions exceeding 1,023 steps | 0% | 6.20% |
| Share of all steps in those transitions | 0% | 60.58% |

Both runs retained 24,000 draws. The expanded fit used 4.60 times as many
leapfrog steps. This is a comparison of trajectory work, not a controlled
wall-time ratio: graph implementation and the allowed tree depth also changed.
The expanded fit has zero divergences or depth-limit hits, maximum R-hat
1.0041, minimum bulk ESS 2,075 and minimum BFMI 0.442. Those results support
using its draws for this audit. They do not establish the model's substantive
validity. The earlier expanded fit hit its depth-10 ceiling on 5.8% of draws;
the replacement allowed depth 14 and actually reached depth 13.

## The main concerns

**Cumulative floor increments are highly correlated in the current sampling
coordinates.** All 93 fixed-feature columns are linearly independent; their
standardized singular-value ratio is about 75.3. Full rank excludes an exact
fixed-column duplication, but does not make the posterior easy to sample. The
floor >12 and floor >13 columns correlate at 0.995, and their posterior
coefficients correlate at -0.920. These are the two lowest-bulk-ESS coefficients.
Floor 13 has only 51 advertisements from 15 units in seven buildings, compared
with 528 advertisements at floor 12 and 462 at floor 14. Opposing increments
can leave much of the cumulative curve nearly unchanged. This makes correlation
a plausible contributor to long trajectories; a controlled reparameterization
experiment is still needed to demonstrate how much runtime it causes.

**The increment prior is much broader than its name suggests.** Each increment
is independently Normal(0, 0.15) in log rent. Its central 95% prior interval is
approximately -25.5% to +34.2% rent per floor. Across 51 increments, the log prior
standard deviation is 1.071, giving a floor-52/floor-1 rent ratio interval of
approximately 0.123 to 8.16 before observing data. Adding supported levels also
changes this long-range prior variance. A cumulative representation is sensible;
these particular independent prior scales have not earned their place merely
because the posterior converged. Most fitted adjacent-floor intervals cross
zero, and high-floor evidence is concentrated: floor 40 has two buildings,
floor 52 only one. Prior sensitivity must accompany that interpretation.

**Unit effects compete with mostly time-invariant features.** There are 22,155
unit offsets, and 10,440 units (47.1%) have only one advertisement. For every
floor threshold, less than 1% of encoded feature variance remains after
subtracting its unit mean; above floor 30 it is numerically zero. Some remaining
variation reflects missingness or source disagreement, not apartments moving
floors. A unit-constant feature can be absorbed by free unit offsets in the
likelihood. The hierarchical zero-mean unit distribution and its shrinkage
separate these components statistically. That is a real modeling assumption,
not a programming error or a reason to discard all unit effects. It needs to be
explicit for factor interpretation. Simply imposing new zero-sum constraints
would change the model and is not a neutral computational fix.

The completed posterior unit-scale interval is 0.0843–0.0873 and residual
Student-t scale interval is 0.0651–0.0665. The full-range floor contribution's
largest building-effect correlation is -0.274 at Beatrice, not near-perfect
correlation with every building. Thus the audit does not support claiming that
all building effects are unidentified or that a classic near-zero group-scale
funnel has been demonstrated.

**The bedroom/bathroom construction also needs attention.** Posterior
correlations are -0.904 between the second-bedroom and second-full-bathroom
increments, -0.890 between the second-bedroom increment and bathroom shortfall,
and +0.846 between the latter bathroom terms. These parameters can still have
well-estimated joint contrasts, but individual coefficients are not independent
premiums. The shortfall term should be tested against the simpler full/half-bath
increment model, using supported joint contrasts and residual cases, rather
than retained simply because it arose from an earlier research idea.

**Some supposed amenity dimensions currently measure reporting.** All four
window-direction and seven view dimensions enter this fit only as `.unknown`
indicators. Their known values do not vary enough to create a measured-presence
contrast. A coefficient therefore compares recorded presence with unknown
status, not presence with confirmed absence. Elevator presence and its unknown
indicator have posterior correlation -0.866. Unknown values should not be
silently recoded as absent. These terms need clear reporting-status labels and
a sensitivity analysis before being described as physical amenity premiums.

Finally, the quoted in-sample residuals include each unit's fitted offset.
Small residuals partly reflect that unit's own advertised prices influencing its
estimate. They remain useful for model checking, but should be accompanied by a
structural price excluding the unit offset and, for suspicious advertisements,
a leave-one-advertisement-out or earlier-listings-only estimate. This is about
honest residual interpretation within known buildings, not prioritizing unseen
building prediction.

## Next experiments, in order

1. Preserve the extracted floors and current completed fits. Do not promote a
   model solely because a higher depth ceiling made it pass diagnostics.
2. Test an exact change of sampling coordinates for the cumulative floor block
   (orthogonal rotation with the original prior covariance preserved), retaining
   named floor increments as derived quantities. Verify full-data density,
   gradients, and reconstructed contrasts before comparing fits. This isolates
   computation from changes in the statistical model.
3. Separately compare calibrated/shrunk floor-increment priors and the
   bedroom/bathroom model with and without the shortfall term. Preserve matched
   rows and targets; assess joint contribution stability, support and residual
   examples as well as effective samples per unit of time. Do not automatically
   add a new hierarchy without checking whether it introduces another difficult
   geometry.
4. Audit the role of unit offsets and reporting-status terms with explicit
   alternative residual definitions. Treat large contribution shifts with
   stable fitted prices as evidence of attribution sensitivity.

A switch to GPU is not a specification fix. The earlier completed CPU/GPU
comparison used a different, sparse-floor model; a low-rank nutpie trial on a
laundry variant was stopped during warmup for runtime and memory cost. Neither
establishes that switching the current expanded model will solve these issues.
See [the sampler reassessment](chelsea-sampler-reassessment-2026-09-18.md).

## Reproduction

Producer: `docs/analysis/scripts/audit_floor_geometry.py`.
Artifact: `data/model/chelsea-floor-geometry-audit-20260919`.
Manifest SHA-256: `f03117baf108e13aca6e95518fbf34367fbbd094d61bdc3f0e45450af21b093b`.
All bundle files were hash-verified after publication, and posterior feature
coordinates were checked against the saved design.

It records source/posterior/design/diagnostic hashes, fixed-feature rank and
correlations, within-group variance fractions, posterior correlations, scale
intervals and retained trajectory-work summaries. It reads completed draws only
and does not modify the sampling graph or main selection.

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m docs.analysis.scripts.audit_floor_geometry \
  --experiment data/model/chelsea-bayesian-label-floor-block-depth14-disk-20260919 \
  --dataset data/model/chelsea-label-floor-analysis-20260919 \
  --reference data/model/chelsea-bayesian-reviewed-elevator-disk-20260919 \
  --output data/model/chelsea-floor-geometry-audit-20260919
```
