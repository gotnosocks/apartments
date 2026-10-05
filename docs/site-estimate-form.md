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

The scoring is the same as for a held-out row of an apartment the fit never saw. Per posterior draw it uses the terms
of `explain.log_terms` at the fit's last month, a unit level from the unit prior (`summary.new_unit_levels`,
clipped to `loo`'s ±40 unit scales), and Student-t noise.

The site has no numpy or JAX, so `rentfrontier.kit` (PR #228) writes a **prediction kit** per run to
`/data1/apartments/frontier/kits/<run>-<commit>/`. The kit names its summary bundle by sha256. From 250 thinned
draws it holds:

- `kit.json`, per draw:
  - market without the season: offset, intercept and trend at the last month;
  - the season coefficients (daily Fourier or monthly);
  - beta;
  - the bedroom curve at the last month;
  - sigma per bedroom group, nu, unit scale and unit ν;
  - the feature names, groups and slope columns, and the bedroom rule.
- `buildings.parquet`, per building and per draw:
  - its level plus its walk at the last month;
  - its bedroom slope;
  - its feature slopes.

The site build (`estimate_build`) copies the kit into `site.sqlite` once it passes two checks. If either fails, the
form says it is unavailable, and the build itself goes ahead.

1. **Scoring.** The bundle's rows of the last month whose apartment has only that row in the fit (k < 0.5) are
   rescored from their own inputs. The median of kit / bundle − 1 must be within 2% for the median estimate and both
   80% bounds. The bundle's values are leave-one-out and the kit uses the full posterior, so single rows differ by a
   few percent; a wrong term would shift them all. On the served run: −0.4%, −0.3% and −0.3% over 93 rows.
2. **Encoding.** The form's encoder, run on each once-listed apartment's recorded fields, must reproduce the model's
   inputs, group by group, on at least 95% of listings. On the served run every group agrees on 99.7% or more of
   15,696 listings.

Per request, in pure Python: the building's own columns come from its newest listing's `inputs`. The apartment's
columns come from the form, with "not stated" levels for blanks, a first listing, a current ask and a description.
The sqft median per bedroom count is recovered from the bundle's rows. The season is taken at today's date.
80 simulated asks per draw (20,000 in all, about 0.06 s) give:

- **Typical rent:** the median of the latent rent of a new apartment like this, and its 95% interval;
- **Likely ask range:** the 10–90% and 2.5–97.5% quantiles of the simulated asks;
- **Your ask:** the share of simulated asks below it. The listing pages' price band applies: below 10%, above 90%.

A form URL is deterministic: the seed is the building, the date and the inputs. A run with a feature group the
encoder does not know gets no form. So does a design without a kit (line effects, unit drift), or an older build.

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
