# How well do beds, baths and text predict size? (2026-10-12)

Ben asked for a free check of how well the other unit fields predict a listing's stated size. The
answer decides whether a latent-size term, which treats a missing size as a parameter, is worth
the sampler work. Only free work was used: no fit, no paid compute, no data change. Scripts and
the full numbers are in `size-predictability-2026-10-12/`: `export.py` and `analyze.py`, run on
thelio's CPU, with the results in `results.json`.

**Data.** NB8 on the current rules (`baths-ad-v3, bedrooms-ad-v3, fields-review-v3,
quarantine-v12, unit-labels-v15, unit-reviews-v1, unit-splits-v4`): 214,887 rows, of which 54,835
(25.5%) state a size.

**Method.**
- Target: log stated size.
- Validation: five cross-validation folds grouped by building, so every prediction is for a
  building the model never saw.
- Models: a ridge regression as the linear baseline, and LightGBM.
- Intervals: the brackets are 95% intervals from 300 bootstrap resamples of buildings.
- Error measure: MdAPE is the median absolute percentage error of the predicted size.

## 1. Predictability

Predictors:
- every column of the base feature set `nb8-nostuy-v1` except the two size columns. This covers
  bedrooms, baths, floor, elevator, doorman, laundry, views, labels, PLUTO era, class, floors,
  units, area per unit and FAR, and the area dummies.
- raw bedrooms, baths and floor, and the listing date.
- 19 ad-text word flags: studio, alcove, loft, townhouse, terrace, duplex, renovated, penthouse,
  junior, convertible, walk-in closet, office or den, dining, king, queen, words for large, words
  for small, sunny, and three-bedroom.
- the description's length.
- for (a) and (b), the first square-footage figure stated in the ad text.

| Case | Model | R² | MdAPE |
|---|---|---|---|
| (a) new building, without the text sq ft figure | ridge | 0.852 [0.841, 0.863] | 10.0% [9.6, 10.5] |
| (a) new building, without the text sq ft figure | LightGBM | 0.867 [0.857, 0.876] | 9.3% [8.8, 9.8] |
| (a) new building | ridge | 0.855 [0.844, 0.866] | 10.1% [9.7, 10.5] |
| (a) new building | LightGBM | **0.880** [0.870, 0.889] | **8.7%** [8.2, 9.1] |
| (b) known building, other units' sizes left-unit-out | ridge | 0.886 [0.877, 0.894] | 8.4% [8.0, 8.9] |
| (b) known building, other units' sizes left-unit-out | LightGBM | **0.917** [0.911, 0.922] | **6.5%** [6.2, 6.8] |

In (b), each row gets the mean stated log size of the building's other units, overall and with the
same bedroom count, together with how many units there are. The row's own unit is always left
out.

R² across all rows is flattered by the spread between bedroom counts. The relevant number is
what is left once bedrooms are known. The model above already knows bedrooms, so the question is
how much of the size variation within a bedroom count the other fields explain.

| Bedrooms | Rows | (a) R² | (a) MdAPE | (b) R² | (b) MdAPE |
|---|---|---|---|---|---|
| studio | 11,096 | 0.46 [0.35, 0.56] | 9.8% [9.1, 11.0] | 0.65 [0.57, 0.71] | 6.9% [6.2, 7.7] |
| 1 | 23,533 | 0.59 [0.53, 0.65] | 7.9% [7.2, 8.7] | 0.72 [0.68, 0.75] | 6.2% [5.9, 6.6] |
| 2 | 14,061 | 0.78 [0.75, 0.80] | 8.1% [7.5, 8.9] | 0.84 [0.82, 0.85] | 6.2% [5.8, 6.6] |
| 3 | 4,746 | 0.84 [0.82, 0.86] | 9.2% [8.7, 9.8] | 0.89 [0.87, 0.90] | 7.1% [6.6, 7.8] |
| 4+ | 1,399 | 0.80 [0.74, 0.84] | 11.4% [9.8, 12.9] | 0.85 [0.81, 0.88] | 8.5% [7.4, 9.4] |

These R² values are computed within each bedroom count (LightGBM). Within a bedroom count, the
standard deviation of log size is 0.23 for studios and ones, 0.32 for twos and 0.42–0.45 for
threes and larger. The out-of-fold residual SD for (a) is 0.16–0.23.

| Area | (a) R² | (a) MdAPE | (b) R² | (b) MdAPE | Share with a stated size |
|---|---|---|---|---|---|
| Chelsea | 0.91 | 8.5% | 0.94 | 6.3% | 35% |
| East Village | 0.82 | 10.6% | 0.87 | 8.0% | 14% |
| Flatiron | 0.91 | 7.4% | 0.92 | 5.8% | 34% |
| Gramercy Park | 0.85 | 9.4% | 0.91 | 7.2% | 24% |
| Greenwich Village | 0.88 | 9.9% | 0.91 | 7.8% | 19% |
| NoMad | 0.83 | 11.3% | 0.91 | 6.4% | 59% |
| Stuyvesant Town/PCV | 0.88 | 1.7% | 0.89 | 2.1% | 95% |
| West Village | 0.88 | 9.3% | 0.90 | 7.9% | 18% |

`results.json` has the intervals for every row of these tables. The areas where size is least
often stated (East Village, the Villages) are also the ones where it is hardest to predict, at
10–11% error for a new building.

- **Text figures.** 15.9% of stated rows quote a square-footage figure in their ad, and 73% of
  those figures are within 5% of the stated size. Only 1.9% of unstated rows (2,981 rows) quote
  one, so the text can fill in very few sizes.
- **Known-building coverage.** 73% of rows without a size have another unit in the same building
  that states one, and 57% have one with the same bedroom count.

## 2. Is size missing selectively?

**(i) Within a unit.** 10,832 units state a size in some listings and not in others, over 43,570
rows. Comparing a unit's listings without a size to its listings with one:
- Rent, net of neighbourhood × month: −0.5% [−0.9, −0.1] (mean); the median is −0.6%.
- Date: the listings without a size are 0.4 years later on average [0.03, 0.8], in line with the
  falling share of listings that state a size (section 3).
- Text: they are 5.7 points less likely to quote a square-footage figure [3.8, 7.7], and slightly
  less likely to say "renovated" (−2.8 points [−5.7, −0.4]).
- No difference: description length and the large or small words.

Within a unit, then, a size is missing almost at random.

**(ii) Units that never state a size, against stated units of the same building and bedroom
count.** I compared the (a)-model sizes (LightGBM, without the text figure, out of fold) of the
two groups within the same building × bedroom cell. There are 3,851 such cells.
- **Within a cell:** units that never state a size are predicted 1.5% smaller [1.2, 2.0] on the
  mean, and 0.3% smaller [0.1, 0.5] on the median.
- **Calibration:** in those cells the model over-predicts the stated units' actual size by 1.5% on
  the mean (1.2% on the median). So a within-cell gap of this size is about as large as the
  model's own error.
- **Across all units:** units that never state a size are predicted 16% smaller (63,746 units
  against 28,805). That difference comes from which buildings and bedroom counts they are in,
  not from within a building.

**(iii) The rent gap.** I trained a LightGBM rent model on rows with a stated size, using the same
predictors plus the true log size, with folds by building. I then fed it the predicted size on
every row. If predicted size accounts for the missing sizes, the mean residual should be the same
for stated and unstated rows.

| | Mean residual of log rent |
|---|---|
| Stated rows, true size | +1.9% [0.3, 3.8] |
| Stated rows, predicted size | +1.2% [−0.6, 3.3] |
| Unstated rows, predicted size | −1.5% [−2.2, −0.8] |
| Stated rows, rent model with no size at all | +2.7% [0.8, 4.7] |
| Unstated rows, rent model with no size at all | −0.5% [−1.1, 0.1] |

Unstated rows rent about 2.7% less than their predicted size implies (−1.5% against +1.2%). The
gap is about the same as with no size in the rent model at all (3.2%). It holds for every bedroom
count: −2.8% for studios, −3.6% for ones, −1.8% for twos, −2.0% for threes and −1.2% for 4+.
Predicted size does not explain the gap, because it is built from the same fields the rent model
already uses.

What the gap means is open. It fits the pattern of unstated units being slightly smaller than
their fields suggest, or cheaper for other reasons the data doesn't record. It is small (a few
percent), and the within-unit evidence in (i) says listings don't hide size by price.

## 3. Share of rows with a stated size, by year

| Year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Stated | 41.5% | 40.5% | 34.5% | 35.5% | 31.1% | 29.7% | 28.9% | 26.1% | 26.3% | 25.6% | 24.3% | 23.7% | 25.3% | 23.8% | 21.6% | 21.1% | 20.5% |
| Rows | 698 | 1,075 | 1,276 | 1,913 | 13,794 | 15,082 | 16,238 | 18,784 | 18,482 | 18,098 | 20,698 | 14,169 | 14,275 | 16,556 | 15,859 | 15,181 | 12,709 |

The 2010 figure is confirmed at 41.5%. 2026 is 20.5% on the current rules, below the 24% quoted.
24% matches 2020–2023 instead.

## What this says about a latent-size term

- **Size is fairly predictable.**
  - New building: about 9% median error, with within-bedroom R² of 0.46 for studios and about 0.8
    for twos and larger.
  - Known building: about 6.5% median error.
- **Imputation adds little new information.** Almost all of that predictability comes from fields
  the rent model already has (bedrooms, baths, building fields and text flags) and from the
  building itself, which its building effects already capture. A latent size imputed from the
  same fields would mostly re-express them. What it adds is the spread of size within a building
  and bedroom count, where the residual SD is about 0.16 in log size, and that is the part the
  data cannot pin down.
- **The missingness is close to ignorable.**
  - Within a unit it is nearly at random.
  - Within a building and bedroom count, units that never state a size look 0–1.5% smaller.
  - Unstated rows rent about 3% below what their fields predict, and predicted size does not
    account for that gap.
  - A size-unknown indicator, which the model already has (`sqft_unknown`), absorbs a gap of this
    kind directly.
- **Recommendation:** the expected gain from a latent-size term is small relative to its sampler
  cost. A cheaper alternative is to plug in the (b) prediction as a fixed feature for rows without
  a size, judged rent-blind under the usual rules. That would test the same idea without new
  sampler work, if Modeling wants to try it.
