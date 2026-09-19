# Controlled refit after the reviewed price-basis quarantine

The production-length refit is running on **52,653 observations, 22,155 units
and 1,129 buildings**, preserving all 172 current listings. It removes the 209
reviewed advertisements with unresolved gross-price basis and the one explicit
short-term advertisement. The selected main model has not changed; this fit must
complete numerical checks and contribution/residual comparison before selection.

The source is `chelsea-reviewed-price-basis-complete-analysis-20260919`, whose
hashed sidecar reconstructs the exact ordered 52,863-row parent. The integrated
readers verify that inverse before fitting, reporting or attaching descriptions.
After merging the previously isolated reader branch, **248 focused tests pass**
and the actual full-data verification reproduces its previous artifact exactly:
71,813 surviving description captures remain identical, 252 are excluded, and
all 172 current observations remain unchanged.

The numerical graph proof for this exact revised source remains valid after
integration: the implementation hashes match. It compares the full/reference
and compressed PyMC log density and all 23,425 gradient parameters at three
points; maximum absolute errors are 1.46e-11 and 3.68e-10 respectively. This is
graph equivalence evidence, not a sampling benchmark.

## Controlled protocol

The fit uses the selected floor-increment/full-half-bathroom-balance model,
shared Student-t residual scale, nutpie/Numba diagonal adaptation, four chains,
4,000 warmup and 6,000 retained draws per chain, target acceptance .93 and seed
20260924. Feature-prior multiplier is 1; building, unit and observed-floor
increment scales are .35, .25 and .15. Spatial features, laundry v4 and alternate
floor priors are not part of this comparison.

The actual published protocol passes `quarantine_fit_comparison.check_protocols`
against the selected reference. Only the expected source-sensitive fields and
the reader/lineage implementations differ; all sampler and declared mathematical
and prior settings match. The protocol-comparison artifact records this check.
The source-dependent centering and normalization changes remain explicit:
elevator log-prior SD per raw unit decreases about .199%, and the three-bedroom
size reference changes from 1,978 to 1,979 square feet. Equal coefficient scales
do not establish identical induced joint priors after changing the cohort.

Run: `chelsea-bayesian-reviewed-price-basis-complete-disk-20260919`.
Live session at launch: **23264**, host PID **573616**. Log:
`/tmp/chelsea-bayesian-reviewed-price-basis-complete-fit.log`.
Compilation completed and the sampling callback began at **09:16:34 UTC**.
Source-reader integration was saved as **637e91ea** before launching the fit.
Keep its mathematical, loader, sampling and report-cache dependencies frozen
until this process reaches a terminal state.

## Required comparison before promotion

Require complete posterior/trace manifests and all parameter, derived-contribution
and joint-floor convergence gates. Generate category contrasts using all retained
joint draws. Then run `models.quarantine_fit_comparison` against the selected
reference and its existing category artifact. This compares residuals on exactly
the common observations, including the unchanged current set; reports removed
groups; and centers building effects against the same shared building population
within each posterior. Draws from different fits are not paired.

Review the largest current residual/contribution movements, building effects and
bedroom/bathroom/floor contrasts. Repeat the spatial diagnostic after source
refitting before evaluating any spatial extension. Do not promote solely because
the fit passes diagnostics or training residuals shrink. The explicit price-basis
quarantines remove uncertain targets; they do not prove historical concession
terms or repair them with later quoted prices.

The optional laundry low-rank trial was deliberately stopped for high operational
cost before this run. Its partial trace is preserved and cannot support posterior
inference. See the [laundry experiment record](chelsea-laundry-floor-experiment-2026-09-19.md).

Supporting artifacts under `data/model/`:

- `chelsea-reviewed-price-basis-complete-reader-verification-20260919`
- `chelsea-reviewed-price-basis-complete-graph-parity-20260919`
- `chelsea-reviewed-price-basis-complete-protocol-comparison-20260919`
- Reference: `chelsea-bayesian-reviewed-corrections-floor-disk-20260919`
- Reference categories: `chelsea-corrected-main-category-contrasts-20260919`

## Follow-up tooling checkpoint

Sampling reached trace export at 09:36:38 UTC on September 19. The original
host process remained live during export; its growing `posterior.nc.partial`
is not a completed posterior and must not be used for inference.

The spatial diagnostic now accepts either the exact fitted source or its bound
direct revision, recording which relationship was used. This permits the
existing location evidence on the revised cohort to be analyzed against its new
posterior without inventing another source revision. The previous warning about
excluded targets remaining in the posterior applies only to the direct-revision
case. Twenty-three spatial tests pass, including equal-source acceptance and
rejection of unrelated or incompletely covered cohorts. After numerical checks,
create a separate candidate selection file for this diagnostic; leave the main
selection unchanged until the contribution/residual review is complete.

At 09:39:04 UTC, all four chains' 6,000 retained draws had been exported to
`fit/posterior.nc`; warmup is excluded. The posterior checkpoint SHA is
`1f3c38774098488eb3f99526e4ca1a19362cdb204e469c7ba998dabaa117140b`.
Final diagnostics and reports remain required before interpretation.

Follow-up session **20395** runs `/tmp/chelsea-reviewed-refit-followup.py`, logging
to `/tmp/chelsea-reviewed-refit-followup.log`. It watches the verified original
host PID/start time, waits for completed reports, and refuses failed diagnostic
gates. It does not restart sampling or change `config/main-analysis.json`. On
success it generates, sequentially:

- `chelsea-reviewed-price-basis-complete-category-contrasts-20260919`
- `chelsea-reviewed-price-basis-complete-fit-comparison-20260919`

A timeout is only an observation deadline, not a terminal sampling event.
Inspect the live process and artifacts before deciding whether work stopped.
The existing movement-review tool now accepts this verified quarantine comparison
and selects its largest current movements across distinct units. Its output
records that scope explicitly; independent fits' draws are never paired.
Forty-six movement/comparison tests pass. Run it after the comparison, inspect
its contribution changes and source captures, then regenerate the eight existing
current source-review cases if their identities and literal evidence still match.
