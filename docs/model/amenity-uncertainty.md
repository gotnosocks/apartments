# Amenity estimate stability

The Chelsea amenity model has three distinct limitations to assess: sampling
variation among captured buildings, dependence on modeling assumptions, and errors
or omissions in source evidence. A predictive improvement does not resolve all
three, and none of these checks identifies causal renovation returns or personal
willingness to pay.

## Sensitivity to building and unit assumptions

`models/amenity_sensitivity.py` uses the frozen v4 cohort and centered categorical
encoding. It predeclares ten specifications: building penalties 1, 10 and 100 with
and without unit effects, plus unit penalties 2 and 32 and amenity penalties 2.5
and 40 around the existing defaults. Every specification uses the same training
and test rows. Evaluation covers the 2024 annual holdout and one predeclared
crossed 2024/building holdout. These reused development folds do not select a new
winning penalty or establish superiority across all building folds.

Building and nested unit indicators are exactly collinear. For a common shift
across a building's `n` units, the effective quadratic nuisance penalty is
`building_penalty * n * unit_penalty / (building_penalty + n * unit_penalty)`.
Removing unit effects changes both the available controls and the effective
shrinkage. Results therefore describe joint model/regularization sensitivity,
not an isolated causal effect of adding unit controls.

Centered known-category indicators also sum to zero. Positive ridge regularization
resolves the fitted coefficients; the meaningful category comparison is the
difference between coefficients. An individual coefficient alone is not its
premium relative to the weighted known-category mean.

## Resampling captured buildings

The bootstrap refits the fixed algorithm after drawing whole training buildings
with replacement. All selected units, advertisements and periods stay together.
Each repeated draw of a building receives a separate building ID and separate
unit IDs; merging duplicate copies would change their nuisance penalties. The
encoder, training category proportions and other training-only transformations
are recomputed in each draw. Original source IDs and draw identities remain
auditable.

Resampling entire clusters preserves within-cluster dependence; undefined or
degenerate estimates must not be silently dropped. These principles are discussed
in [Cameron and Miller's cluster-inference guide](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf).
Unequal building sizes also mean different draws have different numbers of rows,
an issue discussed in [MacKinnon, Nielsen and Webb](https://arxiv.org/html/2205.03285v1).
The experiment records each draw's size and keeps absolute penalties fixed to
measure stability of the specified algorithm, rather than silently changing its
regularization convention.

The initial protocol uses 200 seeded draws. Report empirical percentiles, supported
draw counts, failed fits and sign fractions explicitly. A 2.5% tail contains only
about five of 200 draws. These are exploratory **conditional building-resampling
stability percentiles**, not calibrated 95% population confidence intervals.
They omit regularization bias, discovery/survival selection, source classification
errors, historical attribute ambiguity and shared market shocks across buildings.

## Numerical checks

Small change in the total objective need not imply stable rare-feature contrasts.
A separate diagnostic evaluates the exact penalized Huber stationarity gradient,
then refines the same encoder and objective with tighter linear solves and further
IRLS iterations. It compares category contrasts and predictions to the saved fit.
Numerical sensitivity is separate from statistical sampling stability; neither
diagnostic silently replaces a published model.
