# Chelsea Bayesian modeling study — September 18, 2026

The local Bayesian model converges and provides posterior uncertainty for the
adjusted rent trend and attribute associations. **It does not replace the robust
point model for prediction:** on the separate January–August 2026 test, median
absolute percentage error was **9.41% versus 7.10%**. Its nominal 80% and 95%
prediction intervals covered 75.29% and 92.79% of observations. The report presents
this limitation prominently rather than treating convergence as predictive success.

## Data and model

The unchanged frozen input has 53,899 unit-month observations, representing
54,800 listing IDs, 22,424 canonical units, and 1,141 buildings. It retains 83.9%
of eligible listing IDs. Missing square footage is retained in 64.9% of rows.
Canonical identity comes from the new transform's canonical-unit URL association.
Review annotations are not used. Source data and annotation stores were unchanged.

The model uses log asking rent, cumulative bedroom indicators (`>0`, `>1`, `>2`,
`>3`, `>4`), bathrooms, optional relative log area and missing-area indicator,
a smooth time trend, annual seasonality, and partially pooled building/unit
intercepts. Student-t residuals (five degrees of freedom) reduce the influence
of unusual price deviations. A Normal(0.03, 0.05) annual log-growth prior supports
extrapolation; nonlinear trend directions are orthogonal to linear time under
training-row weights. See [model documentation](../model/bayesian-local.md).

Initial parameterizations mixed poorly. Centered zero-sum building effects,
removal of duplicate seasonal/linear directions, and training-weighted rotation
made four-chain local sampling practical. The orthogonal drift formulation also
changes the nonlinear trend prior; it is not merely a computational rewrite.
Failed explorations are retained but excluded from substantive inference.

## Model choice on 2025

All rows through 2024 trained these models; all 3,785 retained 2025 rows evaluated
them. Six full-cohort Bayesian candidates passed diagnostics, including two
without an explicit growth term. The four growth-term variants were:

| Variant | Median error | Mean log predictive density | 80% coverage |
|---|---:|---:|---:|
| Units + available size + Student-t | 6.77% | 0.688 | 85.31% |
| Building effects, no unit effects | 7.02% | 0.645 | 87.24% |
| Unit effects, no size | 6.86% | 0.673 | 83.96% |
| Unit effects + size, normal residuals | 7.22% | 0.535 | 86.90% |

The robust point model had 7.99% median error on this same validation year.
Mean log predictive density is measured on log rent; higher is better. No
predictive density was fabricated for the point model.

Paired bootstrap resampling of whole buildings supported the selected model's
log-score improvements: +0.043 over building-only (95% interval 0.014–0.070),
+0.014 over no-size (0.006–0.024), and +0.153 over normal residuals (0.053–0.326).
The small point-error difference from building-only was not decisive. These
intervals describe this validation-year comparison, not future-year guarantees.

Selection was locked at **05:57:07 UTC before running or inspecting the 2026
test**. No choices were subsequently retuned against that test.

## Separate 2026 evaluation

Training used 51,098 rows through December 2025. The final test has 2,801 rows
across 523 buildings. The Bayesian model's median error exceeded the point model
by 2.31 percentage points; a paired building-bootstrap 95% interval was
1.47–3.23 points. Median signed error was -8.39% (underprediction), compared with
-3.89% for the point model.

Bayesian error was 9.08% for previously seen units and 11.01% for unseen units.
Signed bias worsened from -3.09% in January to -14.15% in August. Missing-size
and larger-bedroom groups fared worse. Extrapolation is a clear priority to
investigate, but these diagnostics alone do not establish the cause.

This is retrospective date validation, not a strict historical as-of-date
forecast: the source archive includes capture-time attributes and identities.
The outcomes are asking prices, not signed leases or achieved rents.

## Full-data descriptive fit

The final fit uses all 53,899 retained observations. Four chains, 2,000 tuning
iterations and 3,000 retained draws each passed the predeclared diagnostic gate:
maximum R-hat 1.0064, minimum bulk ESS 626, tail ESS 1,024, zero divergences, and
minimum E-BFMI 0.421. Runtime was about 12 minutes on the local Thelio.

The adjusted market trend increased **6.09%** from August 2025 to August 2026
(95% model-based credible interval **4.92–7.25%**), **14.36%** over two years
(13.12–15.64%), and **35.97%** over five years (34.42–37.50%). These are fitted
changes over observed dates, not predictions.

Incremental bedroom associations were approximately +27.2%, +22.6%, +25.5%,
+11.1%, and +10.0% for each successive threshold. They multiply on the rent
scale. Because size is relative to a bedroom group's reference area, these are
not fixed-area causal values of adding a bedroom. Persistent unit effects also
do not identify renovation dates or prove that all recorded attributes are right.

## Exploratory whole-unit check

A deterministic 20% of units had their complete histories withheld. The accepted
fit achieved **7.04% median error** over 11,060 observations, +0.31% median bias,
82.57% coverage for nominal 80% intervals, and 93.98% coverage for 95% intervals.
Maximum R-hat was 1.0081, minimum bulk ESS 775, minimum tail ESS 674, with zero
divergences. All test units were unseen in that fit.

This evaluates new homes in market periods learned from other homes. It is
exploratory because the earlier model-selection year may include the same units;
it is not another independent model-selection test. Together with worsening
future-date bias, it motivates investigating the time extrapolation separately
from the attribute/identity structure.

## Repository maintenance

The maintenance branch extracts transform finalization into named, tested
helpers. Completion now validates the expected shard/checkpoint inventory,
implementation hashes, row counts, derived-table inventory, uniqueness and
reference coverage before writing the completion marker. Regression tests cover
missing files, unexpected zero-row files, corrupt checkpoints/counts, and recovery.
The same finalizer supports local and Modal paths; local operation is documented
first. Existing datasets were not rewritten to satisfy the stricter checks.

Modeling and maintenance were developed on separate Jujutsu bookmarks and merged
in an isolated integration workspace. The combined suite passed **347 tests,
with two intentional skips**. Installed packages were not synchronized or changed;
the lockfile records the dependencies used by the new modeling code.

## Artifacts and next steps

- Frozen input: `/data1/apartments/archive/fits/chelsea-minimal-canonical-20260917-incremental/model_data.parquet`.
- Input SHA256: `53921470380bd8f716c024721bdca3fbd57c8b011ec3177da13de6c9eb0c760c`.
- Accepted validation batch: `/data1/apartments/archive/fits/chelsea-bayesian-20260918-orthogonal`.
- Selection, final test, full fit, and whole-unit check: `/data1/apartments/archive/fits/chelsea-bayesian-20260918-final`.
- Additional diagnostics: `/data1/apartments/archive/fits/chelsea-bayesian-20260918-analysis`.

Retain the point-model predictions. Next modeling work should compare alternative
extrapolation priors with multiple earlier rolling-origin validation windows,
then reserve a genuinely new period for confirmation. A separate attribute-shift
review can distinguish changing homes from source errors without unmerging valid
identities. About 1,684 retained units have recorded bedroom/bathroom changes;
that is a diagnostic population, not an automatic exclusion list.
