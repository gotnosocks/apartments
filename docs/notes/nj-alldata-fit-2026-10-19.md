# The normal walk on all data, NJ included, 2026-10-19

Ben asked for a fit of the last design that converged, on a new "all data" dataset with the
Hoboken and Jersey City rows, fit only, outside the Modal budget. The last converged design is
the normal walk of #1156 (`normal-walk-b0-latest-98a9fe44-dense-w1500`, max R-hat 1.009). The
two-zone fits after it did not converge.

## The design

I run the #1156 design unchanged. Its mean holds a weekly trend, the bedroom ladder, the bath
steps, the season and the description flags, and no borough, zone or neighbourhood term
(`b0.design`). So no term exists for NJ to get its own level in. The NJ rows enter as more rows,
and the walk, ladder and noise scale pool over them with the NYC rows. I measure the NJ offset
afterwards from the saved draws, as the median residual of the NJ rows against the NYC rows.

## The data

1. `python -m rentfrontier.b0data` on pipeline build `rows-30b3edae310c2fae` (ads
   `ads-aee67cf5178acc34`), with the off-market dating of the #1156 dataset, into
   `/data1/apartments/frontier/datasets/b0-30b3edae310c2fae-alldata`.
2. I set aside the 197 NJ listings that quarantine-v36 (draft #1168,
   `config/reviews/quarantine-v36-20261019.jsonl`) adds over v35, into
   `b0-30b3edae310c2fae-alldata-v36`. The pipeline already drops v35's rows. The manifest's
   `quarantine` entry gives the rule file, its SHA-256 and the count. The step is
   `docs/notes/nj-alldata-setaside-v36.py SRC OUT V36 V35`.
3. `python -m rentfrontier.b0trim` into `b0-30b3edae310c2fae-alldata-v36-dense`.

The fit reads no registry, so snapshot `20261019-bcfbb52-extend` stays as it is and registry-nj
goes unused. The NYC rows come from the same pipeline code as #1156's, from a later build.

## The fit

    ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-30b3edae310c2fae-alldata-v36-dense --split latest ea4bcbd6 dense-w1500 normal-walk b0 16 1500 500 12 --max-leapfrog-steps 64 --seed 20261019 --no-loo --no-heldout

#1156 took 20 minutes and cost $0.83 on 1,896,486 rows. The datasets came out at 1,969,299 rows
from b0data, 1,969,102 after the v36 set-aside and 1,969,084 after the trim (dense start
2013-12-02, 18 rows set aside, as in #1156), 3.8% more than #1156. cap.py estimated $0.83 with a
balance of $2.87, and the fit started at 18:49 ET as `normal-walk-b0-latest-ea4bcbd6-dense-w1500`.

## Predictions (written before the fit)

Convergence:

| Prediction | #1156 | Expected |
|---|---|---|
| max R-hat over all traced quantities | 1.009 (tau) | under 1.02 |
| min bulk ESS | 1,678 (tau) | over 800 |
| divergences while sampling | 0 | 0 |
| wall time | 20 min | 30 min or less |

Estimates, against #1156's own values from its saved draws (the scorecard of
`normal_walk.scorecard`, each a posterior median):

| # | Prediction |
|---|---|
| 1 | The bedroom and bath contrasts of scorecard items 1 to 4 each move by under 2 percentage points. |
| 2 | tau moves by under 10%. |
| 3 | The 2020 trough moves by under 1.5 points, since NJ rows begin in 2013 too and make up 4% of rows. |
| 4 | g moves by under 0.5 points a year. |
| 5 | The season peak stays in the same month. |
| 6 | Each of the four noise scales sigma[0..3] rises by 0.5% to 3%, since the NJ rows add location spread the mean leaves unexplained, and nu (the Student-t degrees of freedom) moves by under 10%. |
| 7 | The NJ rows' median residual lies between -0.15 and +0.05 log points: below Manhattan, above much of Brooklyn, and the two average to slightly below the pooled mean. |
| 8 | The NYC rows' median residual moves by under 0.01 log points. |
