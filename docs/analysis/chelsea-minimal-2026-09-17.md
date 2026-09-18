# Minimal canonical-unit asking-rent model — September 17, 2026

Fit locally on the Thelio using `chelsea-granular-20260917-canonical-url-v1`.

- Retained **54,800 / 65,350 listing IDs (83.9%)**.
- Modeled **53,899 unit-month observations**, **22,424 units**, **1,141 buildings**.
- Window: January 2010–August 2026. 64.9% of observations have missing size and remain in the model.
- Withheld 2026 median absolute error: **7.1%**, versus **17.8%** for the bedroom-only baseline. **90.8%** are within 20%.
- Entirely withheld units: **8.0%** median error. This tests unseen-unit estimation in observed market periods.
- Adjusted trend: **+6.4%** August 2026 vs August 2025. 2020–21 trough: **-20.2%** vs February 2020 in November 2020.
- Full local fitting pipeline: **23 seconds**.

See [the interactive report](http://thelio.tail3983e0.ts.net:8766/model-report) for charts, exclusions and validation details.

## Method

Robust penalized regression on log initial asking rent, with incremental bedroom thresholds (>0, >1, >2, >3, >4),
bathrooms, optional size, building and unit effects, a smooth monthly trend and
month-of-year seasonality. Six settings combinations were selected using 2025;
2026 prices stayed withheld until final evaluation. A separate 20% unit holdout
uses independent fixed settings and training-only scales.

Each advertisement uses its own first active event and its own attributes.
Repeated source captures count once; duplicate listings within a unit-month become
one median observation. Source data and review decisions are not changed.

## Limits

These are nominal asking prices, not signed rents. Explicit concessions, furnished
and very short-term offers are excluded. Conditions and renovation dates remain
unmodeled beyond reported layout changes. No posterior or uncertainty intervals
were estimated. The temporal test is retrospective with later archived covariates,
not a live as-of-date backtest; it underpredicts 2026 by 3.9% at the median.
New-building performance is not established.

## Reproduce and reuse

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=src .venv/bin/python models/minimal_rent_model.py \
  --dataset /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --output /path/to/new-model-run
.venv/bin/python models/minimal_model_report.py --model /path/to/new-model-run --output /path/to/report
```

Import `load_model(directory)` and `predict(model, dataframe)` from
`models/minimal_rent_model.py` to reuse the saved point estimate. Inputs need
`unit_id`, `building` (canonical building slug), `period` (month-start timestamp),
`bedrooms`, `bathrooms`, and `square_feet` (NaN allowed). `predict` returns log rent;
exponentiate for the predicted median asking rent. Unknown units/buildings receive
zero group offsets; future months hold the final smooth trend flat plus seasonality.

Artifacts are in `/data1/apartments/archive/fits/chelsea-minimal-canonical-20260917-incremental`. Selection audit retains an exclusion reason for every
dropped listing. The final report and parquet tables preserve reproducibility.
