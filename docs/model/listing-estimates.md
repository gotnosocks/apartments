# Per-listing estimates (`rentfrontier.summary`)

`rentfrontier.summary` turns a recorded run's kept joint draws into page-ready estimates for every
row of the dataset. The listings site reads them. It never fits: a summary takes a few minutes on
thelio, like `rentfrontier.loo`.

```sh
cd frontier
TMPDIR=/data1/apartments/tmp/<you> XLA_PYTHON_CLIENT_PREALLOCATE=false \
  /data1/apartments/serve/master/ops/job gpu -m 5G -- uv run --extra gpu python -m rentfrontier.summary <run>
```

It writes `/data1/apartments/frontier/summaries/<run>-<commit>/`. The module docstring has the full
column list. The summary refuses:
- a dirty tree;
- a run that fails the convergence gate (`--allow-failing` for experiments);
- a dataset, held-out row set, or unit and building index that differs from the run's record;
- a feature source whose file, as the feature set reads it now (`run.feature_sources`), differs from
  the run's record;
- unit-split runs, whose unseen units would lose their unit prior (row-split and `all` runs are
  accepted);
- unit-drift designs, whose drift the leave-own-row-out step does not integrate.

## What an estimate is

The **estimate** is the row's latent rent exp(μ): the median ask of this apartment, in this
building, that month. It is conditioned on every other row in the fit but **not the row's own ask**
(leave-own-row-out), as the brief requires for the app's residuals. The in-sample fit is pulled
toward the ask.
- **Held-out rows** (the run's row split, 5,264 rows) were not in the fit, so their posterior is
  used as is.
- **Rows in the fit.** For each draw, the unit level is integrated given the unit's other rows,
  exactly as in `rentfrontier.loo`. A level is drawn from that conditional (on `loo`'s grid, uniform
  within a cell), and the draws are reweighted by Pareto-smoothed importance weights
  1 / p(yᵢ | θ, y_{u,−i}). A unit listed once in the fit gets a draw from the unit prior, so its
  estimate rests on the building, the features and the market only.

Each row also gets:
- the weighted mean, median and 95% interval of the estimate;
- the ask less the estimate, in dollars and percent;
- **pit**, where the ask falls in the leave-own-row-out predictive distribution (Student-t noise
  included);
- the in-sample fitted rent, as a review signal;
- **dollar contributions** of the estimate (the LMDI decomposition of `explain`, per draw, against
  a reference apartment in an average building that month). Their weighted means add up to the
  estimate.

## Checks on the published run

Run: `m5-nocurves-unitdescpluto-v3-rows-faa8c78-gibbs-2060-3600-ul1`.
- It is the app's design with the building facts from NYC MapPLUTO: era, size, class, landmark and
  historic district, and an alteration since 2000. The 2015 flood-zone flag is left out.
- It was fit with the custom Gibbs sampler: PSIS-LOO 52,439.6, 1,376 s on the RTX 2060.
- Ben chose it as the app's model on 2026-09-29, for interpretability at equal accuracy. It scores
  +8.2 ± 18.3 against the previous selection on identical rows.
- The anonymous building level falls from 29% to 8% of the variance. On a listing page the building
  facts show as named rows (building era, size, class and status). In 70% of buildings they outweigh
  the building's own level.
- `config/main-analysis.json` selects its summary at commit 90aa695: 1,200 draws, 226 s on the RTX
  2060, 2.9 GB peak. The listings site publishes that summary.

Earlier selections:
- 2026-09-26: the NumPyro fit `m0q-btrend-unitdesc-v1-rows-df5dacb-nuts-c8-w250d550-svi2k-ul1-2060`.
- Earlier on 2026-09-29: the Gibbs fit `m5-nocurves-unitdesc-v1-rows-ab2a7df-gibbs-2060-3600-ul1`.

Checks:
- Contributions add up to the estimate within 7.3e-11 dollars on every row.
- Pareto k per row equals `rentfrontier.loo`'s pointwise k for this run within 2e-13. The weights
  are the board's PSIS-LOO weights.
- With 1,200 draws the reliability threshold is 0.675 (`loo.k_threshold`). 396 rows (0.84%) are
  above it, and the site flags them as less reliable. 344 rows are above 0.7, against 374 for the
  previous selection.
- Calibration, from the ask's position in its leave-own-row-out predictive distribution:

| Rows | n | In 95% range | In 80% range | Median \|ask − estimate\| | In-sample median |
|---|---:|---:|---:|---:|---:|
| Held out (not in the fit) | 5,264 | 94.7% | 79.2% | 4.0% | 4.0% |
| In the fit, unit has other rows | 36,746 | 95.1% | 79.7% | 4.0% | 2.0% |
| In the fit, unit listed once | 10,628 | 91.4% | 76.9% | 6.0% | 1.5% |

The calibration and the median gaps are the same as for the previous selection. The median gaps
are smaller than for the NumPyro fit of 2026-09-26, which had 4.7% on held-out rows and 7.1% for
units listed once.

Rows in the fit whose unit has other rows behave like genuinely held-out rows. The in-sample
residuals are half as large, which is the pull toward the ask that leave-own-row-out removes.

Units listed once are less well calibrated. Their PIT is U-shaped, with 12–19% more mass than
uniform in the outer deciles, so the Normal unit prior is too light-tailed for them. The site
reports this rather than widening their intervals.

The design's building walks give each building its own path over time, which the listing pages
show as "Building over time". The buildings table has no yearly trend for a walk design, so building
pages show the level only.
