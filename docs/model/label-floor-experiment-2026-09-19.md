# Expanded advertised-floor measurement experiment

This experiment tests whether source-bound unit-label floors add useful,
interpretable floor contributions and explain building/unit residual structure.
It keeps the analytical observations, asking prices, non-floor attributes,
time construction and group priors fixed. The Thomas Eddy bedroom correction
is recorded separately and is not mixed into this floor comparison.

The reference is `chelsea-bayesian-reviewed-elevator-disk-20260919`, fitted on
`chelsea-reviewed-elevator-analysis-20260919`. The candidate source is
`chelsea-label-floor-analysis-20260919`. Original source fields, label-derived
candidates, inference decisions and exact capture provenance remain separate.
The inference's knowledge date is not a physical renovation date.

The measurement reads each own capture's structured `displayUnit`, accepts a
positive one- or two-digit prefix followed by one letter, and requires agreement
across that observation's captures. Explicit floors take precedence. Inference
is withheld in the 18 buildings from the earlier numbering-conflict review.
Candidates above any captured building `floorCount` are withheld; two-digit
candidates also require a known building count. This is a conservative
compatibility check, not a conversion from physical stories to advertised labels:
valid labels in buildings that skip numbers may remain unknown.

The floor term remains cumulative observed-level increments:

`floor_effect(F) = sum_k beta_k * 1(F > k)`

Unknown floors have a separate indicator. Adjacent increments have independent
Normal(0, 0.15) log-rent priors and unconstrained signs. Adding supported floor
levels increases the cumulative prior variance over the full range; report that
range prior and avoid interpreting unsupported individual intermediate levels.

First fit the expanded floors with the existing v4 specification. Then test the
existing pooled floor/elevator interaction on the same expanded dataset. That
interaction covers label changes 2→5 and saturates above 5; it does not establish
a distinct elevator premium at every high floor. Testing wider or separate
interactions requires a separately documented support check and comparison.

Use PyMC with the exact compressed graph, nutpie/Numba and durable posterior
storage: four chains, 4,000 warmup and 6,000 retained draws per chain, target
acceptance 0.93, diagonal adaptation, seed 20260924. These match the reference.
Verify compiled log-density and gradient parity before fitting. These are model
experiments, not a new sampler speed benchmark.

Evaluate:

- Sampling diagnostics for parameters and joint floor contrasts: R-hat below
  1.01, bulk/tail ESS at least 400, divergences, tree-depth saturation and BFMI.
- Posterior floor increments, joint cumulative contrasts and uncertainty,
  including sparse endpoint support and sensitivity to building/unit offsets.
- Residual changes on all observations, captured ACTIVE listings, newly inferred
  floors, previously explicit floors, and still-unknown floors. These are
  in-sample diagnostic comparisons, not independent predictive accuracy.
- Largest distinct unit residual movements and building/unit offset movements,
  followed by source review for bad numbering or other omitted attributes.
- The fixed eight-case development panel as a regression check, separately
  from any newly selected residual outliers.

A smaller residual alone does not earn the feature a place in the main model.
The decision must consider source plausibility, posterior stability, uncertainty
and whether floor effects are interpretable with the available building overlap.
Keep the selected main fit explicit until these checks are complete.

Floor labels are largely constant within a unit. With unit offsets in the model,
their contribution is therefore identified mainly by comparisons across units
and the hierarchical prior on those offsets, rather than by observing a unit
move floors. A narrower interval is conditional on that structure and the
measured covariates; it does not establish a causal price effect of moving an
otherwise identical apartment. Review contribution reallocation between floors,
units and buildings even when total fitted prices change little.

## Completed source projection

The final interpretation is dated `2026-09-19T15:55:47.145088+00:00`.
It covers every one of 71,813 attached captures: 71,645 verified raw-hash label
reuses and 168 new parses of frozen refreshed bodies. It adds 29,558 inferred
floor observations (10,791 units / 755 buildings) while retaining all 349
explicit observations. Model coverage is 29,907/52,653 rows; 95/172 capture-time
ACTIVE rows have floors. Accepted model labels range from 1 to 52.

The compatibility filter withholds 694 above-count candidates and 217 two-digit
candidates lacking a building count. The 18 reviewed conflict buildings account
for another 1,567 withheld rows; 20,268 rows have unresolved or conflicting
capture labels. These categories explain all 22,746 still-unknown rows.

Source manifest SHA-256:
`5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605`.
Observation SHA-256:
`f32280906454687da145f3904aeb7ea70cdbd7b8c44ad32328c1ace404ddb974`.
Full source-lineage inversion and description binding passed for all observations
and captures. The integrated regression checks passed 316 tests. Implementation
checkpoint: `9ab8608a`.

Support inspection of the complete projected cohort found known no-elevator
observations only on labels 1–6: respectively 132, 289, 321, 315, 272 and 17 rows.
The floor-6 cell contains nine units in six buildings. There are no observed
known-no-elevator endpoints above 6, so access-specific plotted curves are
withheld there. High-floor coverage is concentrated: labels 30, 40, 50 and 52
appear in eight, two, one and one buildings, respectively. This limits how broadly
their conditional floor contributions can be interpreted even with precise
Monte Carlo diagnostics.

Canonical model-floor coverage spans 10,980 distinct units in 786 buildings,
compared with 276 units in 141 buildings under explicit floors alone. The
number of buildings with at least two observed floor levels increases from
40 to 621. Those 621 buildings contain 10,765 of the 10,980 known-floor units;
the remaining 215 units are in buildings with only one observed known level.
These are source-support counts, not effective sample sizes. Repeated listing
observations do not create independent apartments, and missing floors need not
be random. Annual row coverage ranges from about 51% to 62% over 2010–2026.

One unit has two different accepted explicit source floors: 115 West 23rd #63
(advertisements 4582906 and 4930926, source claims 4 and 6). This pre-existing
contradiction was already recorded in the floor conflict review; its building
is excluded from new label inference. It is not evidence that a unit physically
moved floors. The label projection does not silently adjudicate old explicit
claims, so this remains an unresolved source limitation of both fits.

## Reproducing the source projection

From the repository root, the completed source can be reproduced into a fresh
output directory with the frozen input bundles and the same knowledge date:

```sh
uv run --frozen --no-sync python -m models.project_label_floors \
  --dataset data/model/chelsea-reviewed-elevator-analysis-20260919 \
  --evidence data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --audit data/model/chelsea-unit-label-floor-audit-20260918 \
  --review data/model/chelsea-floor-label-conflict-review-20260918 \
  --refresh data/probes/chelsea-candidate-refresh-20260918 \
  --refresh data/probes/chelsea-discovery-details-20260918 \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --as-of 2026-09-19T15:55:47.145088+00:00 \
  --output data/model/chelsea-label-floor-analysis-replay
```

The producer verifies the parent source, description archive, historical label
audit, conflict review, and exact building snapshot inventory. Refreshed captures
are parsed from their hash-bound archived bodies. A new collection requires
updated input bundles and an actual interpretation date; an uncached historical
capture fails explicitly until its label audit is refreshed. This command reads
local captures only. Subsequent scraping must continue through Oxylabs.

The output includes unchanged raw-source values, the inferred `listed_floor`,
`floor_label_provenance`, and `floor-label-projection.jsonl`, whose inverse
restores the exact parent observations. The full producer has already passed a
byte-identical replay. Fit against the new projection explicitly; producing it
does not silently change `config/main-analysis.json`.

## Sampling launches

Both full-cohort compiled graph checks passed at three parameter points:
floor-only maximum absolute log-density/gradient differences were
`4.37e-11` / `2.56e-9`; the interaction maximum gradient difference was `3.78e-9`.
The designs contain 93 and 94 feature columns, respectively.

Full fits launched September 19 around 15:58–16:01 UTC:

- `chelsea-bayesian-label-floor-disk-20260919`: floor-only v4, terminal session
  38023, log `/tmp/chelsea-bayesian-label-floor-fit.log`.
- `chelsea-bayesian-label-floor-elevator-disk-20260919`: pooled v5, terminal
  session 15813, log `/tmp/chelsea-bayesian-label-floor-elevator-fit.log`.

They use the production-length settings above. The runs overlap on the same
machine, so elapsed times are not a controlled backend speed comparison.
Each root contains a frozen protocol, progress record, durable trace and fit
completion manifest. Do not change their archived implementation dependencies
while sampling/reporting is active. Compare only completed, diagnostic-checked
posterior products; a running process is not a model result.

At **16:10:09 UTC**, the interaction sampler (PID 623457, process start identity
24333989) was paused with SIGSTOP to prioritize the primary floor fit and reduce
CPU/memory contention. Its chain state and trace are retained; resume this same
process with SIGCONT after the floor-only run (PID 622652) finishes. The exact
pause record is `/tmp/chelsea-floor-interaction-pause.json`. A stale interaction
progress timestamp during this intentional pause is not a failure. No model or
sampler parameters changed.

An identity-checked watcher (`/tmp/chelsea-resume-floor-interaction.py`, terminal
session 21718) resumes the paused process automatically after the exact primary
process terminates, including its report-writing phase. Its log and the pause
record retain the actual resumption time. This is runtime scheduling only.

## First full fit: tree-depth rejection

The floor-only run completed all four chains (4,000 warmup and 6,000 retained
draws each) at 17:39 UTC. Its parameter diagnostics have maximum R-hat
1.002995, minimum bulk ESS 1,997.70, minimum tail ESS 2,719.07, minimum BFMI
0.42345, and zero divergences/nonfinite diagnostics. However, **1,392 of 24,000
retained transitions (5.8%) reached nutpie's default maximum depth of 10**.
This fails the predeclared zero-depth-saturation gate. Preserve the fit as a
diagnostic artifact; do not promote it or use the gated comparison to present
accepted contribution intervals.

The automatic resumer was disabled at 17:52:01 UTC. The still-paused interaction
run was cancelled at 17:54:35 UTC, with its original protocol, incomplete trace,
and a `cancelled.json` record preserved. It never produced retained draws.
The earlier instruction to resume that exact process is superseded.

The replacement experiments will explicitly bind maximum depth **14** in both
the sampler protocol and trace identity. This raises the ceiling; NUTS still
stops trajectories on its usual U-turn criterion. All statistical terms, priors,
source rows, four chains, 4,000 warmup/6,000 retained draws, target acceptance
0.93 and seed 20260924 remain fixed. An independently compressed floor-block
graph is being tested for full-cohort density/gradient equality and actual
nutpie joint-callback cost before adoption. It changes deterministic arithmetic
sharing only. Keep the existing acceptance rule, including zero depth-limit
hits; do not relax the gate after seeing the first result.

Both block-graph proofs subsequently passed on the full source and freshly
reconstructed saved designs. Maximum gradient differences were 2.68e-9 for
floors and 3.84e-9 for pooled floor/elevator. Each actual nutpie C joint-callback
timing used 3,600 warmed calls per graph in alternating batches across three
parameter points. Median costs were 3.075→1.760 ms (floors) and 2.770→1.992 ms
(pooled interaction). These are callback-cost reductions of 42.8% and 28.1%,
not measured end-to-end sampling speedups.

Proof bundles are `chelsea-label-floor-block-development-parity-20260919` and
`chelsea-label-floor-elevator-block-development-parity-20260919`. Despite the
development names, they contain completed full-cohort numerical checks and
immutable source, design and mathematical implementation bindings. Each new
fit archives the proof and its original manifest in its own protocol bundle.
The legacy disk verifier is unchanged so existing completed fits remain usable.
Both the reference report's continued acceptance and the failed-depth fit's
continued rejection were checked against the real saved artifacts.

## Replacement launches

Checkpoint `04a3b0a6` contains the recovery implementation; 198 focused and
regression checks passed. The floor-only replacement launched around 18:06 UTC:
`chelsea-bayesian-label-floor-block-depth14-disk-20260919` (terminal session
28002, Python PID641012, process start identity25086289). Its log is
`/tmp/chelsea-bayesian-label-floor-block-depth14-fit.log`.

The matched pooled replacement is
`chelsea-bayesian-label-floor-elevator-block-depth14-disk-20260919`.
An identity-checked queue, `/tmp/chelsea-floor-recovery-queue.py` (session34513),
starts it only after the exact primary process ends, publishes a completed fit
with `exploratory_converged` status, and retains matching frozen implementations.
Otherwise the queue records why it withheld the interaction run. Queue state is
`/tmp/chelsea-floor-recovery-queue-state.json`; the interaction log will be
`/tmp/chelsea-bayesian-label-floor-elevator-block-depth14-fit.log`.
These replace the earlier failed-depth/cancelled attempts; none is yet selected
as the main model. Source data and statistical priors remain unchanged.

The replacement primary subsequently completed sampling at 19:24:46 UTC and
published its accepted fit at 19:43:54 UTC. Both parameter and joint-floor gates
pass, including zero divergences and zero depth-limit hits. Maximum parameter
R-hat is 1.004052 and minimum bulk ESS is 2,075.06. The gated queue launched the
matched interaction at 19:44:04 UTC (uv PID 650240, Python PID 650243); sampling
began at 19:45:42 UTC. The primary comparison, 33-case manual source review and
fixed eight-case regression review are complete. See
[the results and source findings](../analysis/chelsea-expanded-floor-results-2026-09-19.md).


### Superseded specification follow-up

The expanded-increment/elevator fit completed on September 19 at 21:37:44 UTC
with accepted diagnostics. It remains a research result. Following the user's
request for a different floor specification, the same extracted floor dataset
has completed a full fit with the [regularized spline](floor-spline-experiment-2026-09-19.md),
with accepted diagnostics and a completed matched comparison.
This retains the extraction work rather than returning to sparse explicit floors.
