# Baseline backlog and wish list

*Started 2026-10-18 from the baseline-model thread. These are tests and ideas raised while designing B0 (`modeling/baseline-model-proposal-2026-10-18.md`) that are not part of B0 itself. Each runs as its own fit after B0 unless marked free. Costs are scaled from stage records, not timed. Citations are from memory.*

## 1. Checks on B0's trend (first after B0)

| Fit | What changes | Question it answers |
|---|---|---|
| B0-free | a free value at each weekly knot, linearly interpolated, in place of trend and season (the continuous form of the literature's time dummies; Ben rejected calendar-month dummies) | the shape B0's trend plus season must match; B0 should tie it on paired LOO and win on forecasts |
| B0-RW | the served quarterly first-order random walk in place of B0's trend | does the new trend beat the incumbent, on paired LOO and the latest time split |

About $1 to $2 each.

## 2. The ladder after B0

| Rung | Adds | What it measures |
|---|---|---|
| B1 | log size relative to the bedroom median | the value of space; turns bedroom steps into within-size premiums |
| B2 | location: a smooth spatial surface, or NTA labels as a descriptive stand-in | how much rent variation is "where"; the gap explanatory features must close |
| B3 | the served building level, building walk and unit effects | already the served model, no new fit |

- **Size in B1 must handle missing sizes.** About 25% of rows state a size, 35% get one from sizefill, and 40% have none, and the gaps aren't random. Use the latent-size design (`modeling/missing-size-imputation-vs-latent.md`): each unit's unknown size is a parameter with a prior from its bedrooms, baths, building and line, pinned by any stated size or floor plan. Check by refitting B1 on stated-size rows only.
- **Predictions for the ladder:** in B1 the 2-bed step falls below +15% and the 2nd-bath step to less than half its B0 value; B0's and B2's trends differ by more than 3% somewhere (the mix effect).
- **Trend mix check:** B2's trend, which controls location, is the reference for whether B0's large growth shocks are market or listing mix.

## 3. Bedroom × bath interaction (Ben asked for this note)

Bath steps (φ_2, φ_3 and the half bath) by bedroom group (studio and 1 / 2 / 3+), keeping only cells with enough rows. Run on both B0 and B1. If it wins in B0 but not B1, the interaction was a second bath standing in for floor area. Kept only if it beats the additive form by more than 2 SE.

## 4. Season

- **Free check on thelio:** draw the served fit's season curve (peak, trough, amplitude with intervals) and average its residuals by week of year. Structure left in the weekly means is what would justify four harmonics.
- **Four harmonics,** if that check shows a sharper peak than two can draw.
- **Quasi-periodic season:** the four season coefficients drift slowly year to year (about 68 numbers), for years like 2020 when the season collapsed. Kept if it beats the fixed season by more than 2 SE.
- **Season amplitude by bedroom group,** since families and students move on the school calendar.

## 5. Other trend forms (in reserve)

B0's trend contains fixed compounding growth, the undamped second-order walk and a heavy-tailed first-order walk as special cases, so its posterior answers those without fits. Kept for reference:

- **Matérn 3/2 Gaussian process around a growth line**, weekly grid, lengthscale prior with about 1% below 6 months. Guarantees the same smoothing window everywhere but rounds off sharp shocks and needs new dense-covariance code.
- **Normal (not heavy-tailed) second-order walk.** One hyperparameter, banded, but has no way to absorb a shock without letting calm years wiggle.

## 6. Data and checks

- **Count the 5+ bedroom rows** (thelio). If only a few hundred, revisit pooling the bedroom steps.
- **Check which date the served design uses** for trend and season: the latest price's date or the ad's first day.
- **Cluster-aware intervals** for B0 to B2 from a building-cluster bootstrap of a 10% subsample (free on thelio).
- **Simulated recovery:** simulate rents from B0's posterior, refit, and check the steps, trend and season come back within their intervals. B0 is cheap enough to build the project's simulation harness on.
- **Outside agreement:** compare B0's and B2's trends with StreetEasy's and Zillow's NYC rent indexes and BLS CPI rent for the New York metro (allowing for CPI's lag of about a year), and bedroom medians with the 2023 Housing and Vacancy Survey.

## 7. Wish list from the literature and NYC

- **Repeat-rent trend** from the same unit's successive asks (Ambrose, Coulson and Yoshida 2015; Zillow's ZORI method), a constant-quality reference.
- **FARE Act (effective June 11, 2025):** landlords who hire brokers now pay the fee. The change in asks between fee and no-fee listings across that date is a natural experiment, and the "no fee" flag changes meaning there.
- **Rent-stabilized asks** with their own trend pinned to Rent Guidelines Board increases, a known answer the model should recover.
- **Ask versus rent paid:** days on market and price cuts as the market's verdict on each ask.
- **Spatial correlation** of residuals (Basu and Thibodeau 1998): grouped building holdouts for any model without location.

## References

- Ambrose, Coulson and Yoshida (2015), "The repeat rent index", *Review of Economics and Statistics*.
- Basu and Thibodeau (1998), "Analysis of spatial autocorrelation in house prices", *Journal of Real Estate Finance and Economics*.
- Hill (2013), "Hedonic price indexes for residential housing: a survey", *Journal of Economic Surveys*.
- Malpezzi (2003), "Hedonic pricing models: a selective and applied review", in *Housing Economics and Public Policy*.
- Sirmans, Macpherson and Zietz (2005), "The composition of hedonic pricing models", *Journal of Real Estate Literature*.
