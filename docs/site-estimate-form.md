# Estimate an unlisted apartment (site design)

A form on the listings site that gives the served model's estimate for an apartment that is not in the data: a
renter checking an ad, or a landlord pricing a unit. The page is held for Ben's approval: it is built on its own
branch, and it is merged and deployed only once he approves.

## What a visitor enters

The form uses GET, so a result has a URL that can be shared. It needs no script, so it is CSP-safe.

| Field | Form control | Model inputs |
|---|---|---|
| Building | search over the site's buildings (name or address) | the building's own terms, below |
| Bedrooms | studio, 1, 2, 3, 4, 5+ | `bedrooms=*`, the bedroom group, `beds_centered` |
| Full baths, half baths | 1–4+, 0–2+ | `bathrooms=*`, `bathrooms=half=*` |
| Size (ft²) | optional number | `log_sqft_vs_bedroom_median`, or `sqft_unknown` |
| Floor | optional number | `log_floor`, `log_floor_above_6/15`, `log_floor_x_no_elevator`, or `floor_unknown` |
| Laundry, outdoor space, unit label | selects: in unit / in building or none / not stated; terrace, roof deck, ...; penthouse, garden, lower level | the matching indicators |
| Listed extras | checkboxes for the advertisement flags the model codes (renovated, dishwasher, furnished, no fee, ...) | `text:*`; ticking none means an advertisement without those words, not a missing description |
| Your ask (optional) | number | scored against the likely ask range |

Fields left blank take the model's "not stated" level, which is a real level with its own estimate. Some inputs
belong to the building and come from its records: era, size, class, landmark status, neighbourhood, elevator and
doorman. They come from the building's newest row in the bundle and are shown on the result, not asked for. A
building with no rows cannot be chosen. Relisting is fixed at "first listing of the apartment". The price basis is
fixed at "a current ask". The month is the bundle's last month, and the result names it.

## How it is scored against the served fit

It uses the same equation as every estimate on the site: `explain.log_terms` per posterior draw, with the
new-apartment unit level `summary.new_unit_levels` uses for held-out rows of units the fit never saw. The site
has no numpy or JAX, so the summary bundle gains a small prediction kit. It is written by `rentfrontier.summary`
(or a sibling module) from the run's kept draws, thinned to 250 draws:

- per draw:
  - `beta` (every feature column);
  - the market term at the last month (offset, intercept, trend and season);
  - `bedroom_time` at the last month per bedroom group;
  - `sigma` per bedroom group, `nu`, `unit_scale`, `unit_nu`;
- per building, per draw: the building level plus its walk at the last month, `bedroom_slope`, and `fslope` for the
  feature-slope columns;
- encoder constants: the bedroom-median square feet `log_sqft_vs_bedroom_median` is measured against, and the
  feature names in column order.

The kit is stored as `kit.parquet` and `kit-buildings.parquet` (list columns, read with DuckDB like the rest of the
bundle) and is listed in `complete.json`. It is about 10 MB.

Per request, in pure Python, for each draw s:

    total_s = market_s + beta_s · x + bedroom_time_s[g] + building_s[b] + bedroom_slope_s[b] · beds_centered + fslope_s[b] · x_slopes
    level_s ~ unit_scale_s · t(unit_nu_s)        (several per draw)
    log ask ~ total_s + level_s + sigma_s[g] · t(nu_s)

- **Typical rent:** the mean of exp(total_s + level_s), with its 95% interval: the latent rent of a new apartment
  like this. This is the same quantity as a held-out row's estimate.
- **Likely ask range:** the 80% (and 95%) quantiles of the simulated asks, the same quantity as
  `estimate_pred_*` on listing pages. The site uses a fixed seed per input, so a URL always gives the same numbers.
  20,000 simulated asks keep Monte Carlo error under about 0.5% at the 80% bounds.
- **Your ask:** its percentile among the simulated asks, and the listing pages' price band (below / typical /
  above at 0.10 / 0.90).

Two checks guard against drift from the model, so the site keeps the one model definition:

1. When the site is built, every held-out row of an unseen unit is rescored with the kit from the row's own
   `inputs`. The build fails unless the estimate and the 80% bounds match the bundle's within Monte Carlo
   tolerance. This tests the kit math against `summary.py` on every publish.
2. The form's encoder (form fields → feature columns) is run on every bundle row's own observation fields, for the
   fields the form asks. It must reproduce those columns of the row's `inputs` exactly. This tests the encoder
   against `features.build`.

A design without a kit (an older bundle, a line-effects or unit-drift design) shows the form as unavailable rather
than estimating approximately.

## How the result is shown

```
An apartment like this at 1 Jane Street, September 2026
  Typical rent       $4,680   (95% range for the typical rent $4,120–$5,300)
  Likely ask range   $4,050–$5,420   (80% of asks for an apartment like this would fall here)
  Your ask $5,600    is above the likely range: higher than 92% of simulated asks
```

- Below that, "What makes up the estimate", in the same format and wording as listing pages: the reference
  apartment, then each term as a percentage, with the building's own level and trend last. It links to the
  glossary.
- A "Building facts used" line lists era, size, class, neighbourhood, elevator and doorman, from the building's
  records.
- Caveats, in plain words:
  - a new apartment has no history in this building, so the range is wider than for a listed one;
  - a building with fewer than 5 fit listings is flagged, as on building pages;
  - extras the model does not code are not counted.
- Links: the building page, and listings in that building with the same bedroom count.
