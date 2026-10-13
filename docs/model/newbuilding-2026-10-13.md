# New-building score (2026-10-13)

This is Ben's step 1 of 2026-10-13. It is computed by `python -m rentfrontier.newbuilding` (#700) on
the fits' kept draws, with results in `/data1/apartments/frontier/newbuilding/<run>-0f93b1e/`. Each
training row is scored in two ways:

- **New building:** the building's terms (level, walk, bedroom premium, feature slopes, trend) are
  drawn from their population distributions. This tells what the model would quote for a building it
  has never seen.
- **New unit, in-sample:** only the unit's terms are drawn; the building keeps the terms the fit
  learned, including from the row's own asks. That makes this rung **in-sample** for the building,
  and it reads better than out-of-sample. The honest new-unit figure is the row split's held-out
  rows from units the fit never saw (`summary.new_unit_coverage`, #688). For the served C that is
  **67% / 89%** coverage over 964 rows.

The miss is the median absolute % miss of the predictive median. Coverage is the share of asks
inside the central 80% and 95% predictive intervals.

## C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` / `nb8-nostuy-v1`, rows)

| Rows | n | New building: miss | 80% | 95% | New unit (in-sample): miss | 80% | 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 193,376 | 11.9% | 90.7 | 98.1 | 3.7% | 86.1 | 96.9 |
| size stated | 70,977 | 11.8% | 90.6 | 97.9 | 3.6% | 88.1 | 97.7 |
| size unknown | 122,399 | 12.0% | 90.7 | 98.3 | 3.7% | 84.9 | 96.4 |
| building rows 1–5 | 4,128 | 17.3% | 77.8 | 92.3 | 2.5% | 95.0 | 98.2 |
| building rows 6–20 | 17,451 | 14.3% | 85.9 | 96.5 | 3.3% | 90.4 | 96.9 |
| building rows 21–100 | 85,450 | 11.5% | 91.9 | 98.5 | 3.5% | 87.3 | 96.9 |
| building rows 101+ | 86,347 | 11.7% | 91.1 | 98.3 | 4.0% | 83.6 | 96.7 |
| held-out lots' buildings | 20,023 | 12.1% | 91.4 | 98.2 | 3.7% | 86.2 | 96.8 |

Out-of-sample new unit (row split's held-out rows from unseen units, #688): 67% / 89% over 964 rows.

The new-building coverage of 91/98 looks over-wide. One possible reason is that the score draws the
building level and its walk independently, while their posterior trades one against the other. This
is an inference, not yet tested or fixed. Buildings with 1–5 training rows are the exception: their
intervals are too narrow (78/92).

## Other fits (all rows)

| Fit | New building: miss | 80% | 95% | New unit (in-sample): miss | 80% | 95% |
|---|---:|---:|---:|---:|---:|---:|
| C + areatime (`e76570bb`) | 11.9% | 90.6 | 98.1 | 3.7% | 86.1 | 96.9 |
| C on `nb8-nostuy-lines-v1` (`306d7299`) | 12.0% | 90.8 | 98.2 | 3.7% | 86.1 | 96.9 |
| C − floorslope (`306d7299`) | 12.0% | 90.5 | 98.1 | 3.7% | 85.9 | 96.9 |

All four fits' draws are on thelio.

## Descriptive share of C

`python -m rentfrontier.variance` (#700), with building slopes counted as descriptive:

- market and time 8.0%;
- features 67.2%;
- building 10.2%;
- building over time 5.6%;
- **building slopes 4.1%**;
- unit 2.8%;
- residual 2.2%.

The **descriptive share is 26.1%** (90% interval 25.4–26.8%).
