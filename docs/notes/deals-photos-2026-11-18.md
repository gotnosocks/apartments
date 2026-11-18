# Photos and floor plans of the low outliers, 2026-11-18

The broker reads of this week worked from ad text and coded fields. This read gives readers
the images of the ads priced far below the model, across the whole dataset, to look for a
trait a renter would notice in the pictures and the model has no term for. The read of
2026-11-14 (`docs/notes/photo-disagreement-2026-11-14.md`) did the same for 300 ads and
found no fault category that set the cheap ads apart. This read is about 10 times larger,
adds the floor plan's own bedroom count and layout, and adds low ads from the training rows.

## The draw

`deals-photos-2026-11-18/keys.py` draws the ads and writes the readers' batches.

Low ads, with the lowest ad of each building taken once:

- `b9`: held-out ads of the base model's latest-split fit
  (`drift-building-b0-latest-67d14e17-b9`) with a predictive probability under 0.01 of an ask
  this low, and no income flag. 1,064 ads with stored photos, 333 of them with a plan,
  first listed from 2014 to 2026.
- `backtest` and `market`: ads of the Deals model's two runs with no caution and a
  `below_share` under 0.02. 96 and 84 ads.
- `insample`: units of the b9 fit's training rows. `deals-photos-2026-11-18/insample.py`
  rebuilds the fit's design and gives each training ad its distance from the model's level
  for the building, the date and the coded features, with the unit's own level left out.
  The fit did not keep the building's quarterly path, so the script estimates it again at
  the posterior-mean scales. On the held-out ads its levels differ from the fit's by 0.022
  log points (root mean square). Among the 191,435 units with 3 or more training ads and no
  income flag, the low units are the lowest 1% by mean distance (0.18 log points or more
  below the model). `keys_insample.py` takes each one's latest ad with stored photos, one
  unit a building, outside the buildings already drawn: 1,108 units, of which a random 900
  are read (381 with a plan). Their controls are 239 units from the middle half, matched in
  the same way, one for every 3 low units.

Controls: for every 2 low ads of `b9`, an ad of the same fit from the middle half of the
predictive distribution, in the same borough, with the same bedroom count (3 and more
together) and listed within a year. 474 ads.

Each ad gives up to 6 photos, evenly spaced through its gallery, and its first floor plan.
`fetch.py` fetches each image once from the listing site's image CDN at 1 request a second
and stores the originals in the archive by listing id. Readers get JPEG copies under blind
labels, in batches of 15 in random order within each stage of the draw. 90 ads appear
twice under different labels. In all: 2,144 low ads, 713 controls, 15,865 images, 197
batches.

## The read

Each reader is a subagent given `deals-photos-2026-11-18/READER.md`, a batch file with each
label's bedrooms, baths and borough, and the image folders. A reader knows neither the ask
nor the group. The brief keeps the 10 fault categories and the condition and light grades
of the Nov 14 read, and adds:

- 5 categories: a room in a share, an unfinished unit, a cluttered occupied unit, stairs,
  and few or poor photos;
- plan fields: the bedrooms the plan labels, bedrooms with no window, a flex or converted
  bedroom, a bedroom reached through another, the number of levels, the floor named on the
  plan;
- a short guess at the reason a broker would expect a low ask.

A pilot of 6 batches is read twice, by a small model and by a mid-size one. The small model
reads the rest if its category marks agree with the mid-size model's on at least 85% of
ad-category pairs and its grades are within 1 point on at least 85% of ads.

## The bar

For each category and plan field, compare its share among low ads with its share among
controls, with standard errors clustered by building. A trait is flagged when all of these
hold:

1. at least 20 low ads carry it;
2. its share among low ads is at least 1.5 times its share among controls;
3. the difference is more than 3 standard errors;
4. the two reads of the repeated ads agree on it for at least 80% of those ads.

A grade is flagged when the low ads' mean differs from the controls' by more than 3
standard errors. With 21 traits and 2 grades, shuffling the group labels 5,000 times gives
the number of flags expected by chance, reported beside the count found.

A flagged trait is then handled under `docs/expert-reads.md`: look for a coded field or a
text pattern that stands in for it, count it among ordinary ads, and run the free check
before any fit. A trait visible only in images needs a costed plan for reading images at
scale before it can be a term.

## Predictions

Written before any image was read.

1. Condition and light: no flag in the direction of worse low ads. The Nov 14 read found
   the cheap ads slightly better kept, because they sit in newer and larger buildings, and
   the same is expected here: the low ads' mean condition is at or above the controls'.
2. Plan bedrooms: among ads with a plan and 1 or more coded bedrooms, the plan labels fewer
   bedrooms than the record in about 12% of low ads and about 4% of controls, and
   `plan_flex` is flagged. The broker read of the Deals table found 18 of 30 beds-up ads
   with a bedroom the text did not support.
3. `other_unit_or_renderings` and `few_or_poor_photos` are each more common among low ads,
   and one of them passes the bar.
4. `room_only`: under 20 low ads, so no flag.
5. `ground_or_basement`: more common among low ads (about 6% against 3%) and short of the
   bar. The text patterns for basement and garden units were tested on 2026-11-18 and
   dropped.
6. No more than 3 traits flagged in all, against about 0.3 by chance.

## Results

The fetch brought back all 15,865 images with no failure, 14,009 of them at 1 request a
second and the last 1,856 at 4 a second. No OxyLabs request and no Modal time was used.

### Pilot

Batches 01 to 06 (90 ads) were read by Haiku and by Sonnet (`pilot.py`). The two marked
94.1% of ad-category pairs alike. Condition and light were within 1 point on every ad
(equal on 67.5% and 65.3%). On the 29 plans both read, the plan fields agreed on 90% to
100%. Haiku passed the rule and read the other 191 batches through a headless runner
(`read_all.sh`, `read_batch.sh`; `valid.py` drops reply lines that are not JSON).
Haiku marks dark rooms less often than Sonnet (3 ads against 10, 1 in common) and clutter
less often (8 against 17), so the counts below for those two categories are low.

### Shares among low ads and controls

`score.py haiku`, on 2,857 ads (2,144 low, 713 controls, 963 with a plan read). Agreement is
between the two reads of the 90 repeated ads.

| Trait | Low ads | Share | Controls | Share | Ratio | SEs | Agreement | Bar |
|---|---|---|---|---|---|---|---|---|
| `plan_levels` (2 or more levels) | 96 | 12.4% | 8 | 4.3% | 2.87 | +4.2 | 100% | passed |
| `walkup_or_stairs` | 182 | 8.5% | 33 | 4.6% | 1.83 | +3.9 | 96% | passed |
| `ground_or_basement` | 190 | 8.9% | 38 | 5.3% | 1.66 | +3.4 | 94% | passed |
| `few_or_poor_photos` | 667 | 31.1% | 176 | 24.7% | 1.26 | +3.3 | 92% | ratio under 1.5 |
| `tiny_or_windowless_bedroom` | 41 | 1.9% | 7 | 1.0% | 1.95 | +2.0 | 99% | under 3 SEs |
| `low_ceiling` | 31 | 1.4% | 5 | 0.7% | 2.06 | +1.8 | 100% | under 3 SEs |
| `other_unit_or_renderings` | 233 | 10.9% | 62 | 8.7% | 1.25 | +1.7 | 98% | no |
| `plan_fewer_beds` | 63 | 11.2% | 12 | 8.3% | 1.34 | +1.1 | 100% | no |
| `dark_or_shaft` | 182 | 8.5% | 56 | 7.9% | 1.08 | +0.5 | 89% | no |
| `plan_windowless` | 25 | 3.2% | 5 | 2.7% | 1.20 | +0.4 | 100% | no |
| `kitchen_poor` | 564 | 26.3% | 191 | 26.8% | 0.98 | -0.3 | 87% | no |
| `plan_flex` | 23 | 3.0% | 8 | 4.3% | 0.69 | -0.8 | 100% | no |
| `bath_poor` | 348 | 16.2% | 138 | 19.4% | 0.84 | -1.9 | 94% | no |
| `occupied_clutter` | 109 | 5.1% | 59 | 8.3% | 0.61 | -2.8 | 97% | no |

The other 7 traits are within 1 SE or on fewer than 20 low ads (`room_only` 5, `unfinished`
9, `worn_finishes` 19, `street_noise_cues` 11). Mean condition is 3.11 among low ads and
3.02 among controls (+2.2 SEs), and mean light 3.19 and 3.16 (+0.9 SEs). The shuffles give
0.09 flags by chance, and 3 or more in 0.06% of them.

The reader wrote a reason for a low ask on 49.2% of low ads and on 47.8% of controls, so a
reader who sees only the images cannot tell the two groups apart by a stated reason.

### The flagged traits

Stairs and levels are mostly the same apartments. Of the 215 ads with stairs in the photos,
139 also have a plan on 2 or more levels or the dataset's text mark `duplex`
(`rentfrontier.b0duplex`). Stairs without either sign are on 2.8% of low ads and 2.2% of
controls. The samples read are duplexes with a spiral or open stair, and studios with a
sleeping loft up a ladder.

The text mark is on 8.8% of low ads and 3.8% of controls (`duplex.py`). It misses many: of
the 97 ads whose plan draws 2 or more levels and whose row is in the duplex dataset, the
text marks 55.
A plan level, stairs in the photos or the text mark is on 13.7% of low ads and 6.6% of
controls.

On the base model's held-out ads the text mark sits in both tails. Without income ads, it
is on 7.7% of the 1,290 ads below the 1% point of the predictive distribution, 4.7% of the
middle half and 13.7% of the 1,428 above the 99% point. That matches the screen S7 of
2026-11-13, which found duplex asks about 35% more scattered than the model expects and
right on average. A wider predictive interval for marked ads would move duplexes away from
both ends of the Deals ranking.

Ground and basement units outside those duplexes are on 6.2% of low ads and 4.1% of
controls. The notes read are barred street-level windows, sidewalk-level and areaway
windows, and cellar rooms. The model has a curve over the unit's floor and a level for an
unknown floor, and the text patterns for basement and garden units were tested on
2026-11-18 and dropped. The difference left is 2 points.

By pool, the in-sample low units differ from their controls most on `plan_fewer_beds`
(13.4% against 2.5%, on 40 control plans), `ground_or_basement` (10.0% against 3.3%),
`walkup_or_stairs` (9.7% against 3.8%) and `plan_levels` (11.7% against 1.8%). The 180 low
ads of the Deals backtest and market runs show renderings or another unit in 22% to 24%
and few or poor photos in 40% to 49%, and grade 3.8 to 4.0 on condition: they are mostly
new or renovated units in large buildings.

### Predictions scored

1. Hit. No flag on condition or light, and the low ads' mean condition is above the
   controls'.
2. Missed. Plans label fewer bedrooms than the record on 11.2% of low ads and 8.3% of
   controls (+1.1 SEs), and `plan_flex` is less common among low ads. Among the in-sample
   units alone the shares are 13.4% and 2.5%.
3. Hit in part. Both traits are more common among low ads. Neither passed:
   `few_or_poor_photos` is beyond 3 SEs with a ratio of 1.26.
4. Hit. 5 low ads.
5. Missed. The shares were 8.9% and 5.3% against the 6% and 3% predicted, and the trait
   passed the bar. A third of its low ads are the duplexes above.
6. Hit on the count (3 flags). The chance count was 0.09, under the 0.3 predicted.

### What follows

- Duplexes are the trait to act on, as a noise factor on marked rows (the design D1,
  `docs/notes/duplex-factor-2026-11-13.md`, written for an older base and never fit). The
  text mark stands in for the plan and photo signs on a little over half of them.
- A plan showing 2 or more levels is a field worth extracting at scale only if the text
  mark's factor helps: the images of the whole market cost a fetch of about 6 per ad and a
  Haiku read.
- No trait of condition, light, kitchens or baths passes the bar. The low
  asks are not explained by worse apartments in the photos.
