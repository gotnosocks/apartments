# First-ask floor fit: design and predictions (2026-10-23)

The research group's fable asked for this fit on the group board in post
`20261023T072305Z-fable-fit-request-first-ask-floor-fit-opening` and amended it in
`20261023T075703Z-fable-re-first-ask-fit-amended-mixed-response`. The board lives at
`/data1/apartments/research-group/board/`. This note copies the design and the predictions from
those posts before the fit, so the results can be checked against them.

## Data

`frontier/scripts/first_ask_dataset.py` starts from the base model's dataset,
`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`. For each row with a historical initial
own-advertisement ask in `observations-aecf9b7724d3208a-v2.parquet`, it swaps that ask in for
`latest_ask` and sets `latest_day` to the date of the row's `price_at`. The other rows keep their
latest ask, so the fit has a mixed response:

| rows | count |
|---|---:|
| all | 1,896,486 |
| first ask swapped in | 1,733,940 (91.4%) |
| first ask equal to latest ask | 1,137,555 |
| first ask differs from latest ask | 596,385 |
| latest ask kept, no first ask | 162,523 |
| latest ask kept, first ask before the grid start | 23 |

Only `price_basis = historical_initial_own_advertisement_ask` counts as a first ask. The cache
also has 235 capture-basis rows. 88 of them sit beside a historical row for the same listing, and
50 of those 88 have a different value, so the script drops all capture-basis rows. The 147
listings with only a capture-basis value keep their latest ask.

`b0.design` starts the model's weekly grid at the earliest `latest_day`, 2013-12-03 in the base.
23 rows have a first ask posted before that day, 12 of them in 2011 and 2012. Swapping those in
would stretch the walk back by about 130 weeks with almost no data, so those rows keep their
latest ask and the copy's grid starts on the base's day.

The script asserts one first ask per listing. It also runs `latest_split` on the base rows and
on the copy and asserts the masks match. `latest_split` reads only `price_at`, `unit_id` and
`audit_id`, which the copy leaves alone, so that check guards against a later edit to those
columns, and it can't fail on this copy. Both assertions passed when the script wrote `/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc-firstask`,
which has 189,649 held-out ads, listed in its `heldout_ids.json`.

## The run

The fit uses the base fit's model, commit, settings and seed
(`docs/notes/building-zones-floor-2026-10-21.md`), changing only the dataset:

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc-firstask \
  --split latest 6b5a5b4a dense-firstask-w1000 building-zones-floor b0 4 300 1000 5 \
  --seed 20261021 --no-loo --no-heldout
```

The base run took about 20 minutes and $0.73, and this run should be about the same.

## Predictions, written before the fit

Parameters, all measured against the base fit
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000` and read as statements about this
mixed-response model:

| quantity | prediction |
|---|---|
| residual scale σ, each bedroom group | 4% to 8% larger than the base |
| Student-t ν | 1.7 to 1.9 (base about 2.0) |
| building-level sd | within ±0.005 of the base |
| zone level | 0.5% to 1.5% higher |
| `unit:laundry_in_unit` | within ±0.7 log points of 6.13 |
| held-out 90% coverage | within 1 point of the base |
| convergence gate | passes as the base does |
| residual q90 minus q10, common held-out rows with a first ask | 4% to 10% wider than the base |
| P(cut), bottom against top decile of the first-ask residual | about 12% against 45% |

After the fit I export per-row predicted log rent as 200 thinned posterior draws, at both
`price_at` and `latest_day`, for every row with a first ask, from both this run and the base run.
The primary sample is every common held-out ad with a positive first ask, unchanged ads included.
Ads go if the latest ask differs from the first ask by more than 0.5 log points and `latest_day`
is no more than 3 days after `price_at`, and the count dropped is reported. Changed ads form a
named secondary sample.

For each draw, an OLS regresses the first-to-last change on the first ask minus that draw's
predicted first-date rent, after removing year-month means. The slope's posterior mixes the
per-draw slopes with their building-clustered sampling variance.

- OLS slope on the primary sample: -0.20 to -0.40. On changed ads only: -0.30 to -0.50.
- The slope on the drift-adjusted change, which subtracts predicted last-date rent minus
  predicted first-date rent: within 0.05 of the raw slope.
- Lagged peer IV slope: -0.20 to -0.50.

Kill conditions, frozen before the fit:

- Dispersion: the σ ratio is under 1.01 in every bedroom group, ν is within 0.05 of the base, and
  the q90 minus q10 ratio is under 1.02, all three together.
- Reaction: the primary-sample slope is above -0.10.

The comparison scores shared held-out ads only, without the rows that have no first ask. A gate
miss on `amp[outer]` alone gets the same reading as in the asof2 fits. The model's PLUTO features
look ahead to later releases, and the results note will say so. A negative slope can't show that
the model finds a fair price. The first ask's error appears in the residual and in the change
alike, so the OLS slope bounds the reaction in magnitude only when the IV backs it up.
