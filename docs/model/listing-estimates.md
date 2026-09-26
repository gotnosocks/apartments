# Per-listing estimates (`rentfrontier.summary`)

`rentfrontier.summary` turns a recorded run's kept joint draws into page-ready estimates for every
row of the dataset. The listings site reads them. It never fits: a summary takes a few minutes on
thelio, like `rentfrontier.loo`.

```sh
cd frontier
flock /data1/apartments/tmp/heavy.lock systemd-run --user --scope -p MemoryMax=5G \
  --setenv=TMPDIR=/data1/apartments/tmp/<you> --setenv=XLA_PYTHON_CLIENT_PREALLOCATE=false \
  uv run --extra gpu python -m rentfrontier.summary <run>
```

It writes `/data1/apartments/frontier/summaries/<run>-<commit>/`. The module docstring has the full
column list. The summary refuses:
- a dirty tree;
- a run that fails the convergence gate (`--allow-failing` for experiments);
- a dataset, feature source, held-out row set, or unit and building index that differs from the
  run's record;
- unit-drift designs, whose drift the leave-own-row-out step does not integrate.

## What an estimate is

The **estimate** is the row's latent rent exp(μ): the median ask of this apartment, in this
building, that month. It is conditioned on every other row but **not the row's own ask**
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

Run: `m0q-btrend-unitdesc-v1-rows-df5dacb-nuts-c8-w250d550-svi2k-ul1-2060`, the best gate-passing
library fit (PSIS-LOO 45,815.1, 745 s on the RTX 2060). The summary is at commit 30c1ee0: 2,200
draws, 425 s on the RTX 2060.

- Contributions add up to the estimate within 1.2e-10 dollars on every row.
- Pareto k per row equals `rentfrontier.loo`'s pointwise k for this run within 1e-12. The weights
  are the board's PSIS-LOO weights. 112 rows (0.24%) have k > 0.7, and the site flags them as less
  reliable.
- Calibration, from the ask's position in its leave-own-row-out predictive distribution:

| Rows | n | In 95% range | In 80% range | Median \|ask − estimate\| | In-sample median |
|---|---:|---:|---:|---:|---:|
| Held out (not in the fit) | 5,264 | 95.6% | 79.4% | 4.7% | 4.7% |
| In the fit, unit has other rows | 36,746 | 95.1% | 80.1% | 4.7% | 3.0% |
| In the fit, unit listed once | 10,628 | 91.5% | 77.0% | 7.1% | 2.3% |

Rows in the fit whose unit has other rows behave like genuinely held-out rows. The in-sample
residuals are a third smaller, which is the pull toward the ask that leave-own-row-out removes.
Units listed once are less well calibrated: their PIT is U-shaped (15% more mass than uniform in each
outer decile), so the Normal unit prior is too light-tailed for them. The site reports this rather
than widening their intervals.
