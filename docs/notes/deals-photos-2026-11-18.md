# Photos and floor plans of the low outliers, 2026-11-18

The broker reads of this week worked from ad text and coded fields. This read gives readers
the images of the ads priced far below the model, across the whole dataset, to look for a
trait a renter would notice in the pictures and the model has no term for. The read of
2026-11-14 (`docs/notes/photo-disagreement-2026-11-14.md`) did the same for 300 ads and
found no fault category that set the cheap ads apart. This read is about 6 times larger,
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
- `insample`: training ads of the b9 fit far below the model's level for the building, the
  date and the coded features, with the unit's own level left out. Defined below once the
  residual table exists.

Controls: for every 2 low ads of `b9`, an ad of the same fit from the middle half of the
predictive distribution, in the same borough, with the same bedroom count (3 and more
together) and listed within a year. 474 ads.

Each ad gives up to 6 photos, evenly spaced through its gallery, and its first floor plan.
`fetch.py` fetches each image once from the listing site's image CDN at 1 request a second
and stores the originals in the archive by listing id. Readers get JPEG copies under blind
labels, in batches of 15 in random order. 60 ads appear twice under different labels.

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

To come.
