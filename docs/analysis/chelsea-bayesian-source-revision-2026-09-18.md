# Bayesian residual and group review: source revision

The accepted Bayesian fit's residuals and extreme group effects led to 12
advertisement-specific decisions. The new research projection contains 52,704
observations and retains all 13 refreshed current listings. The first matched
PyMC refit completed but failed the parameter convergence gate; the longer retry was killed by the operating system for memory exhaustion
after sampling, before writing a posterior checkpoint. The disk-backed retry saved
its posterior and passed both diagnostic gates, but was killed during residual
reporting. Report-only recovery has now completed and the verified source
comparison is available. The main analysis selection remains unchanged.

## Refit status, September 18

`chelsea-bayesian-source-shared-20260918` completed with four chains, 2,000 warmup
steps and 4,000 retained draws per chain. The maximum parameter R-hat is
**1.01039094**, on `beta[elevator.unknown]`, above the unchanged threshold of
1.01. Minimum bulk/tail ESS are 638/1,179; there are no divergences. Derived
checks pass (maximum R-hat 1.00453), but do not override the parameter failure.
The verified report correctly refuses this diagnostic-only fit. No coefficient
or residual comparison from it is treated as an accepted result.

The failed retry is `chelsea-bayesian-source-shared-long-20260918`, with the same cohort,
feature/noise specification and priors, four chains, **4,000 warmup and 6,000
retained draws per chain**, seed 20260922. It uses the existing PyMC graph and
compiled nutpie NUTS. More sampling is a computational change, not a relaxed
diagnostic gate. The currently selected 52,711-row baseline remains unchanged.

At 23:20:09 UTC, the kernel recorded a global out-of-memory kill of its Python
process (exit 137; approximately 11 GiB resident memory). The final progress file
records all four chains at 10,000 total steps with zero divergences. There is no
`posterior.nc`, posterior checkpoint or completion manifest, so there are no
usable uncertainty diagnostics from this attempt. The previous failed fit remains
preserved. Result-storage memory must be addressed before another large run;
the prepared floor fit is also held for this fix.

Historical invocation (do not blindly repeat the memory failure):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --frozen --no-sync python \
  -m models.bayesian_feature_experiment_v3 \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --output data/model/chelsea-bayesian-source-shared-long-20260918 \
  --spec full_half_balance --chains 4 --tune 4000 --draws 6000 \
  --seed 20260922 --target-accept .93 --adaptation diag \
  --residual-scale shared --residual-parameterization centered \
  --graph-validation data/model/chelsea-bayesian-v3-centered-shared-parity-20260918
```

| Action | Advertisement IDs | Evidence |
| --- | --- | --- |
| Quarantine nonresidential offers | 1572189, 1150734, 859915, 1466532 | Gallery, former restaurant, storefront and retail/pop-up descriptions |
| Quarantine unresolved location conflicts | 2903770, 3050643, 2926333 | Uptown location wording conflicts with Chelsea structured addresses |
| Mask disputed bathroom composition | 1406103, 2936893, 3516319 | Explicit full/half wording contradicts structured counts |
| Mask shared bathroom composition | 2391038, 2573882 | Bathrooms are described as external/shared access |

These decisions cover 21 captures. Each is bound to the exact analytical row,
capture identities, original body and raw-listing hashes, description text and
literal spans, source clocks and review time. Recovered descriptions were checked
against their original response bodies. Location conflicts remain unresolved;
the overlay does not invent corrected addresses.

The seven quarantined observations remain available in `quarantined.jsonl`.
For the five masks, all reported counts, scalar bathroom totals, prices and other
analytical fields remain unchanged. A review flag makes bathroom composition
unknown to the research model. Earlier source review metadata remains intact.
Neither capture dates nor these review dates establish physical renovation dates.

The low-price income-restricted offers, ambiguous extreme prices, potential unit
aliases and furnished/flexible lease products remain unresolved research cases.
A residual alone does not establish a source error. The selected reviews do not
estimate the prevalence of errors in the rest of the cohort.

## Reproduce

```bash
.venv/bin/python -m models.research_scope_overlay \
  --projection data/model/chelsea-reviewed-bathroom-projection-20260918 \
  --decisions data/model/chelsea-bayesian-source-decisions-20260918 \
  --audit data/model/chelsea-bathroom-evidence-20260918 \
  --output data/model/chelsea-reviewed-scope-composition-projection-20260918
```

Publication and an identical replay both passed. Twelve focused tests cover
source/decision binding, evidence spans and clocks, immutable replay, retained
values and the guard against removing current captures. This guard applies to
this historical cleanup policy; a future correction to a current listing would
need an explicit policy revision.

The immutable decision bundle contains the frozen publisher and full source
review. The projection contains its frozen implementation, copied decisions,
change records, quarantined original observations and completion hashes.

Related evidence: [accepted model](chelsea-bayesian-bathrooms-2026-09-18.md),
[extreme groups](chelsea-bayesian-extreme-groups-2026-09-18.md), and
[within-unit bathroom changes](chelsea-bathroom-within-unit-review-2026-09-18.md).

## Matched comparison ready for the refit

`models.bayesian_source_sensitivity` compares the accepted original fit with a
converged shared-residual-scale fit of this revision. It rechecks each decision
against the source evidence, retained rows and original quarantines. Both fits
must preserve the mean specification, feature/group priors and numerical
environment. Bedroom-dependent noise is a separate experiment.

The source change can alter feature centering, scaling and support. The comparator
therefore reconstructs each design from its own exact source using dependencies
whose hashes match the archived fit, then compares all saved JSON values and
named numerical arrays, including shapes and dtypes. The original 52,711-row
design reconstructed exactly; the immutable proof is
`data/model/chelsea-bayesian-source-design-verification-20260918`.

Comparisons use the same physical bathroom scenarios and the same retained
observations. They report changed support and removed observations separately;
raw standardized coefficients are not treated as equivalent across designs.
Current-apartment movement and the largest distinct-unit fitted changes are
included, without pairing posterior draws from independently fitted models.
The source, noise-comparison and overlay suites pass 120 focused tests, including
explicit handling of the equivalent residual-hierarchy parameterizations. No
source-sensitivity result is claimed until the revised fit passes both diagnostic
gates.

## Disk-backed retry

`chelsea-bayesian-source-shared-disk-long-20260918` was launched after the adapter
parity, full-sized synthetic export-memory and short full-graph checks passed.
It preserves the failed long run's cohort, seed, all model/prior settings and
4-chain, 4,000-warmup/6,000-retained schedule. Only the storage execution changes.
The immutable readiness bundle `chelsea-source-disk-readiness-20260918` verifies
those equalities and compatibility with the baseline source-comparison protocol.

The command uses `uv run --frozen --no-sync python -m models.bayesian_disk_experiment`.
Raw sampling has its own hashed completion marker; export writes bounded blocks,
and reports recover from the exported posterior checkpoint. No intervals or
source-effect conclusions are available from this retry until all diagnostic
gates pass. See the [storage investigation](../operations/2026-09-18-bayesian-storage-investigation.md).

At 01:06:56 UTC on September 19 (September 18 locally), the disk retry completed
its parameter diagnostics: maximum R-hat **1.004954**, minimum bulk/tail ESS
**1,002 / 1,903**, no divergences or maximum-depth events, and minimum BFMI
**0.439**. All 23,415 parameter diagnostics pass. All 22,188 derived diagnostics
also pass: maximum R-hat **1.001585**, minimum bulk/tail ESS **1,223 / 2,165**.

At 01:13:18 UTC, the kernel killed process 437977 for global memory exhaustion
during subsequent reporting (exit 137, maximum measured RSS 12,096,988 KiB).
The posterior checkpoint, raw trace and both completed diagnostic tables survive.
At that point there was no completed fit manifest. Unlike the earlier extraction
failure, this did not require another sampling run.

`models.recover_bayesian_reports` verifies the original posterior, dataset, design,
scientific implementation and completed diagnostic tables, then finishes the
original report formulas through a disk-backed unit-draw accessor. The recovery
plan explicitly records reuse of completed diagnostics and the reporting override;
final readers verify those bindings. A parity test produces byte-identical
diagnostic, coefficient, group-effect, contrast and residual products. Recovery
completed at 01:30:51 UTC, in **3:10**, with peak RSS **5,524,376 KiB**. The final
fit is `exploratory_converged`; its reader verifies the explicit recovery metadata
and unchanged posterior/diagnostic hashes. The cache is on the workspace disk.

## Completed source comparison

`data/model/chelsea-bayesian-source-sensitivity-20260918` compares both accepted
fits on the same 52,704 retained observations. Median absolute log residual is
**0.035191 → 0.035189**; median absolute fitted-rent movement is **$1.08**. Each of
the 13 current fitted rents changes by less than **$4**. Bathroom contribution
contrasts are similarly stable: for two bedrooms, the one-to-two-full-bath contrast
is **+23.74% [22.95%, 24.55%]**, versus **+23.72% [22.91%, 24.54%]** previously.
These are conditional associations and separate-fit sensitivity summaries.

The largest historical movement is advertisement **4892020**, 344 West 22nd
Street: fitted rent falls from **$31,136 to $29,239**, against an unchanged $42,500
ask. It was not one of the seven quarantined rows. This townhouse already appears
in the [outdoor source review](chelsea-outdoor-model-2026-09-18.md) for garden/luxury
evidence; its localized sensitivity remains a review case, not an automatic price
correction or proof of an omitted-feature effect.

Exact design reconstruction requires the fit's single-thread BLAS setting. An
initial comparison without that setting correctly refused a differing time-design
reconstruction; rerunning with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` passed
without relaxing any comparison or diagnostic gate.

The matched floor-increment experiment is now running on this same corrected
cohort. Its revised readiness bundle is `chelsea-floor-disk-readiness-20260918-v2`;
both the 512-parameter storage chunks and bounded unit reporting are enabled.
