# Photos and floor plans of the market disagreement draw (2026-11-14)

The market disagreement screen (`market-disagreement-2026-11-14.md`) drew 100 held-out ads
with an ask far under L1's median, 90 days on the market and a price cut (group A). Blind
readers of the ad text and the coded fields found no cause in 47 of them. A renter looks at
the photos and the floor plan before the text, so in this check I ask whether those 100 ads
show faults in their images, compared with the screen's agreement group B (cheap by L1 and
rented at once) and its random controls R.

Nothing is fit and nothing goes to Modal or the GPU. The scripts are in
`docs/notes/photo-disagreement-2026-11-14/` and write to
`/data1/apartments/tmp/photo-disagreement-2026-11-14/`.

## Permission and budget

Ben lifted every earlier hold on research directions and data collection in the project
owner's thread on 2026-11-14 at about 4:00 PM ET, with expenses counted against the sprint's
$100. S12's photo pilot (`amenity-signs-2026-11-13.md`) had stopped on Nov 13 waiting for that
message. This check has a cap of $5 of OxyLabs spending. `docs/data/graphql-collection.md`
puts the Realtime API at about $1.14 per 1,000 requests, so the cap is 4,380 requests. I set
the fetch script's own ceiling at 3,500 OxyLabs requests ($3.99).

## Design, fixed before any image was fetched

### The ads and their images

I take all 300 ads of groups A, B and R from the screen's frozen `draw.parquet` (SHA-256
`3014d134...57b376`). Group C, dear and fast, is left out.

`f1_keys.py` reads each ad's stored records from the pipeline's records file, as S12's
`p_sample.py` did, and takes the photo and floor plan keys of the latest record with photos.
From a gallery of n photos it keeps 8: all of them when n is at most 8, otherwise the photos
at 8 evenly spaced places from the first to the last, so that a bath near the end of a long
gallery has the same chance as a living room at its start. It keeps the first floor plan.
That comes to at most 2,700 images.

`f2_fetch.py` fetches each image from `https://photos.zillowstatic.com/fp/<key>-p_e.webp`.
It first asks the CDN directly, at 1 request a second, as the floor plan reviews of October
did. When a direct request fails it sends the same URL through the OxyLabs Realtime API with
S12's `p_fetch.py` code, holding `crawls/oxylabs.lock` at 55 requests a minute, with no
retry. It stores the original file under `archive/photos/<listing id>/` or
`archive/floor-plans/<listing id>/`, and a JPEG copy of at most 768 pixels (1,280 for a plan)
under the ad's blind label for the readers.

### The readers

`f1_keys.py` gives each ad a random label and deals the 300 labels into 20 batches of 15. It
draws 60 of the ads with at least one photo at random, gives them new labels, and deals them
into 4 more batches, so that those 60 ads get a second reader who cannot tell them from first
reads. Sonnet subagents read the batches, 4 at a time. A reader gets `READER.md`, the image
folders, and for each label the bedrooms, the baths and the borough. It gets no ask, no ask
history, no group, no ad text and no address.

For each ad the reader marks every category that applies, from this fixed list:

| Category | Marked when |
|---|---|
| `dark_or_shaft` | the rooms are dim in daylight photos, or a window faces a shaft, a wall or a court a few feet away |
| `low_ceiling` | the ceiling is visibly low, under about 8 feet, or beams and soffits cut the height |
| `awkward_layout` | the plan or the photos show a railroad layout, rooms entered through other rooms, a long dark hall, odd angles, or a bed in the living room of a unit sold as having a bedroom |
| `tiny_or_windowless_bedroom` | a bedroom holds little beyond the bed, or has no window, or only an interior window |
| `kitchen_poor` | the kitchen is worn or dated, or is a kitchenette along a wall of the living room with small appliances |
| `bath_poor` | the bath is worn or dated: old tile, stained grout, an old tub or vanity |
| `worn_finishes` | floors, walls, doors or windows are worn or damaged over the whole unit |
| `ground_or_basement` | the photos or the plan show a unit at or below the street: bars on windows, sidewalk-level views, window wells, a cellar level |
| `street_noise_cues` | windows give on an avenue, a highway, an elevated train, a bar front or a construction site |
| `other_unit_or_renderings` | the images are renderings, a model unit, photos marked as another unit, or building and amenity shots with no photo of the unit |
| `few_photos` | the ad's gallery holds 3 photos or fewer, counted by `f1_keys.py` from the record |
| `nothing_wrong` | the reader marks none of the other reader categories |

`few_photos` comes from the record, and the other 11 from the reader. The reader also gives a
condition grade and a light grade, each from 1 to 5:

- condition: 1 worn or damaged, 2 dated, 3 ordinary and sound, 4 renovated, 5 new or high end;
- light: 1 dark, 2 dim, 3 ordinary, 4 bright, 5 very bright with large windows or open sky.

A grade stays empty when the images cannot support it, as with renderings alone.

### The score and the bar

`f3_score.py` joins the reads to the draw and computes:

1. each category's share in A, B and R with a building-clustered SE, and A less B and A less
   R with clustered SEs;
2. the mean of each grade in each group and the same two differences;
3. both again with A cut down to the 47 ads the text readers labeled `none_apparent`
   (A47), against all of B and R;
4. on the 60 ads read twice, Cohen's kappa for each reader category and the Pearson and
   Spearman correlation of each grade. Group shares and means use the first read alone.

The bar, set here:

- a category is flagged when it has at least 8 reads in A and its share in A is at least
  twice its share in B and at least twice its share in R (a control share of zero passes);
- a grade is flagged when A's mean differs from B's or from R's by more than 3 SEs.

That makes 14 tests: 12 categories and 2 grades. For the 4 grade comparisons, chance alone
passes 3 SEs about 0.01 times in all. For the categories, `f3_score.py` shuffles the group
labels over the buildings of the 300 ads 5,000 times and counts the flags of each shuffle, so
the note can report the mean number of flags from chance and the share of shuffles with at
least one. For A47 the same bar applies, with the same shuffle on 47, 100 and 100 ads.

For each flagged category or grade I then check the coded fields and the text for a column
already holding it, cost out a column over the whole dataset, and give the arrow the column
would add to the model: level, time path or noise.

## Predictions, written before any image was fetched

When I wrote these I had read the screen's note and S12's pilot design. I had seen none of
the 300 ads' images, and had not counted their photos or floor plans.

1. **Fetching.** The CDN answers at least 90% of the direct requests with an image (75%),
   and OxyLabs spending stays under $1 (80%).
2. **Coverage.** At least 85% of the 300 ads get at least one photo (70%). Between 35% and
   65% of the ads have a floor plan (60%).
3. **Nothing wrong.** `nothing_wrong` is the most common category in each of A, B and R
   (80%). Its share in A is at least 5 points under its share in both B and R (40%).
4. **Flags.** At least one category is flagged in A (30%). If one is, it is `dark_or_shaft`
   or `worn_finishes` (50% given a flag).
5. **Grades.** A's mean condition is 0.1 to 0.5 under R's (45%). A grade is flagged on
   condition (12%) or on light (8%).
6. **A47.** No category is flagged in A47 (75%), since 8 reads there take a share of 17%.
7. **Chance.** The shuffles give a mean under 0.5 flags (65%).
8. **Agreement.** The two condition grades of an ad correlate at 0.5 to 0.8 (60%), and the
   two light grades at 0.3 to 0.6 (50%). Among reader categories marked at least 5 times by
   either reader, the median kappa is between 0.2 and 0.5 (55%). Kappa for `nothing_wrong`
   is over 0.3 (55%).
9. **The agreement group.** The text readers found walk-ups and railroad layouts in B. B's
   mean condition is under A's (55%), and `awkward_layout` has a larger share in B than in A
   (55%).
10. **Renderings.** `other_unit_or_renderings` has a larger share in A than in R (55%),
    since a new building's lease-up shows model units and stays on the market; it is
    flagged (12%).
11. **Few photos.** `few_photos` has a larger share in B than in A (60%), since an ad opened
    and marked rented on a single day is often a thin record.

## The fetch

`f1_keys.py` found 2,056 image keys for the 300 ads: 1,927 photos and 129 floor plans.

| Group | Ads | With a photo | With a floor plan | Gallery of 3 or fewer | Median gallery |
|---|---|---|---|---|---|
| A, cheap and slow | 100 | 98 | 58 | 7 | 12 |
| B, cheap and fast | 100 | 94 | 33 | 18 | 7 |
| R, random | 100 | 95 | 38 | 14 | 8 |

`f2_fetch.py` ran from 4:04 PM to 4:42 PM ET and saved all 2,056 images from direct requests
to the CDN. It sent no request through OxyLabs, so the check spent $0.00 of its $5.

The `-p_e` rendition is a 596 by 446 crop, and it cuts the edges off a floor plan. I added
`f2b_plans.py`, outside the committed design, to fetch each plan again directly in the
`uncropped_scaled_within_1536_1152` rendition (129 of 129 saved) and to replace the readers'
`plan.jpg` with it before any reader started. The photos stayed in the cropped rendition.

## The reads

24 Sonnet readers ran 4 at a time and each wrote 15 lines: 300 first reads and 60 second
reads. Every line used category names from the list, and every label has a read. A reader
took about 130,000 tokens and 75 seconds for its 15 ads, and read 7.1, 5.7 and 6.5 photos an
ad on average in A, B and R.

`f3_score.py` takes as its base the ads with at least one photo read (98, 94 and 96 in A, B
and R, and 45 of the 47 in A47) for the reader categories and the grades, and all ads for
`few_photos`. R's 96th ad has an empty gallery and a photo of a room stored as its floor
plan, which its reader counted as a photo. Counts by group, with the share and its
building-clustered SE in points:

| Category | A | A47 | B | R |
|---|---|---|---|---|
| `nothing_wrong` | 63, 64.3 (4.9) | 35, 77.8 (6.2) | 47, 50.0 (5.2) | 41, 42.7 (5.0) |
| `kitchen_poor` | 14, 14.3 (3.6) | 4, 8.9 (4.3) | 22, 23.4 (4.4) | 16, 16.7 (3.8) |
| `other_unit_or_renderings` | 11, 11.2 (3.1) | 5, 11.1 (4.6) | 8, 8.5 (2.9) | 8, 8.3 (2.8) |
| `tiny_or_windowless_bedroom` | 8, 8.2 (2.8) | 1, 2.2 (2.2) | 6, 6.4 (2.5) | 8, 8.3 (2.8) |
| `awkward_layout` | 7, 7.1 (2.6) | 1, 2.2 (2.2) | 9, 9.6 (3.0) | 11, 11.5 (3.3) |
| `few_photos` | 7, 7.0 (2.6) | 4, 8.5 (4.1) | 18, 18.0 (3.8) | 14, 14.0 (3.4) |
| `ground_or_basement` | 6, 6.1 (2.4) | 1, 2.2 (2.2) | 6, 6.4 (2.5) | 10, 10.4 (3.1) |
| `dark_or_shaft` | 5, 5.1 (2.2) | 1, 2.2 (2.2) | 15, 16.0 (3.8) | 12, 12.5 (3.4) |
| `bath_poor` | 5, 5.1 (2.2) | 2, 4.4 (3.1) | 21, 22.3 (4.3) | 13, 13.5 (3.5) |
| `low_ceiling` | 3, 3.1 (1.7) | 1, 2.2 (2.2) | 2, 2.1 (1.5) | 1, 1.0 (1.0) |
| `worn_finishes` | 2, 2.0 (1.4) | 0 | 5, 5.3 (2.3) | 3, 3.1 (1.8) |
| `street_noise_cues` | 1, 1.0 (1.0) | 0 | 0 | 8, 8.3 (2.8) |

No category passes the bar in A or in A47. The fault categories run the other way. A has
fewer marks than both B and R in 6 of the 10 reader categories, and its `nothing_wrong` share
is 14.3 points over B's (SE 7.1) and 21.6 points over R's (SE 7.0). In A47 the difference
grows to 27.8 points (SE 8.0) and 35.1 points (SE 8.0). The largest contrasts are `bath_poor`
(A less B: -17.2 points, SE 4.9) and `dark_or_shaft` (A less B: -10.9 points, SE 4.4).

Mean grades, with clustered SEs:

| Grade | A | A47 | B | R | A less B | A less R |
|---|---|---|---|---|---|---|
| Condition | 3.83 (0.10) | 3.98 (0.15) | 3.25 (0.10) | 3.28 (0.08) | +0.58 (0.14) | +0.55 (0.13) |
| Light | 3.84 (0.09) | 3.93 (0.11) | 3.33 (0.10) | 3.28 (0.08) | +0.51 (0.13) | +0.56 (0.12) |

Both grades pass the bar of 3 SEs, at 4.0 to 4.6 SEs for A and for A47, with the sign
opposite to a fault. The ads in A, cheap by L1 and still open at 90 days, look better kept
and brighter in their photos than the agreement group and the random controls.

### Chance

The shuffles of the group labels over buildings flag 0.08 categories on average for A (a
flag in 7.6% of the shuffles) and 0.085 for A47 (8.0%). The 2 grades against 2 control groups
in A and in A47 make 8 comparisons, and a difference beyond 3 SEs has a chance of about 0.3%
in each, so the grade differences are well outside chance.

### Agreement on the 60 ads read twice

| Category | First reader | Second reader | Both | Kappa |
|---|---|---|---|---|
| `nothing_wrong` | 30 | 33 | 28 | 0.77 |
| `other_unit_or_renderings` | 9 | 9 | 8 | 0.87 |
| `dark_or_shaft` | 7 | 4 | 3 | 0.50 |
| `kitchen_poor` | 6 | 8 | 4 | 0.52 |
| `ground_or_basement` | 6 | 5 | 5 | 0.90 |
| `bath_poor` | 5 | 6 | 3 | 0.50 |
| `awkward_layout` | 4 | 2 | 2 | 0.65 |
| `tiny_or_windowless_bedroom` | 4 | 4 | 4 | 1.00 |
| `low_ceiling` | 3 | 3 | 3 | 1.00 |
| `street_noise_cues` | 2 | 2 | 2 | 1.00 |
| `worn_finishes` | 1 | 1 | 1 | 1.00 |

The condition grades of the 54 ads graded twice correlate at 0.90 (83% equal, all within a
point), and the light grades of 52 ads at 0.91 (85% equal). Both readers of an ad are the
same model with the same instructions, so these numbers measure how well a read repeats. A
person might grade differently.

## The grades against the fields L1 already reads

`f4_pattern.py` joins each graded ad to its building's fields and to L1's own median for it.
The groups differ before any photo is opened:

| Group | Median first ask | L1's median | Median year built | Built 2000 or later | 100 or more units |
|---|---|---|---|---|---|
| A | $4,248 | $4,709 | 1969 | 32.7% | 46.9% |
| B | $3,047 | $3,409 | 1920 | 13.8% | 33.0% |
| R | $3,897 | $3,842 | 1926 | 11.5% | 21.9% |

A's ads come from dearer, newer and larger buildings. Over the 3 groups the condition grade
correlates at 0.47 with L1's median and 0.46 with a building of 2000 or later, and the light
grade at 0.45 with L1's median and 0.44 with a building of 100 or more units. A least-squares
fit of each grade on L1's median, bedrooms, Manhattan, the building's era, its units and a
doorman takes up 42% of the grade's variance. With those fields in the fit, A's difference
from R falls from +0.55 (SE 0.13) to +0.07 (SE 0.11) on condition and from +0.56 (SE 0.12)
to +0.09 (SE 0.11) on light. Adding the group to the fields raises the share of variance by
0.1 points. So the flagged grades come from group A's mix of buildings and price levels, and
L1 already reads that mix through the building, its era and its size.

Within the groups a point of condition goes with a gap 0.008 higher (SE 0.006) and a point
of light with a gap 0.015 higher (SE 0.008). Neither grade moves the market score D (0.034
with SE 0.031, and 0.000 with SE 0.035). Inside R alone, 90 ads, the slopes of the gap are
-0.018 (SE 0.011) and -0.011 (SE 0.012).

## Candidates and their arrows

The check finds no fault in photos or plans known to the market and missing from L1. The
leads from it, in order of support:

1. **Lease-up and large-building pricing.** Arrow: time path. A's ads are concentrated in
   post-2000 buildings of 100 or more units, look good in photos, stay open for 90 days and
   are cut. That fits an owner of many units posting a high opening ask and lowering it in
   steps, while L1 learns the building's level from those opening asks. No photo column is
   needed. The data is already in the table: the building's count of open ads on the day, its
   era and size, and the share of its past asks later cut. The sprint's L2 phase term is the
   place to test it.
2. **Faults already priced into fast, cheap ads.** Arrow: level. B has `bath_poor` in 22.3%
   of its ads against 5.1% in A, and `dark_or_shaft` in 16.0% against 5.1%, which agrees with
   the text readers' `unit_fault` count in B. These asks closed at once, so the discount is
   in the ask and missing from L1's median. A column would be the condition grade, and the
   fields above explain 42% of it. The other 58% costs a photo read: 9 images of an ad are
   about 7,000 input tokens, near $0.02 an ad on Sonnet through the API and under $0.01 on
   Haiku, and the 9 direct CDN requests are free. 100,000 ads would cost about $2,000 on
   Sonnet and 10 days of fetching at 1 request a second. The slope of the gap on condition
   within groups is 0.008 a point, so I would not pay for the column on this evidence. A
   renovation match on the text and the alteration year from DOB filings are the proxies to
   try first.
3. **Light.** Arrow: level. The within-group slope of the gap on the light grade is 0.015 a
   point (1.9 SEs), the largest in the check. Proxies without photos: the unit's floor
   against the heights of the neighboring lots in PLUTO, and the coded exposures.
4. **Street noise.** `street_noise_cues` has 8 marks in R and 1 in A and B together. The
   design had no test for it, and these groups give it no arrow.

## Predictions, scored

1. All 2,056 direct requests returned an image and OxyLabs cost $0: both parts hit.
2. 287 of the 300 ads have a photo (95.7%) and 129 have a floor plan (43%): both parts hit.
3. `nothing_wrong` leads each group: hit. Its share in A is 14 and 22 points over B's and
   R's, and I had given 40% to at least 5 points under: miss.
4. No category is flagged in A. I had given a flag 30%.
5. A's mean condition is 0.55 over R's, and I predicted 0.1 to 0.5 under: miss. Both grades
   pass the 3 SE bar, events I gave 12% and 8%, with the sign I did not expect.
6. No category is flagged in A47: hit.
7. The shuffles give a mean of 0.08 flags: hit.
8. The grade correlations are 0.90 and 0.91, over both ranges: both miss. The median kappa of
   the 5 categories marked at least 5 times by either reader is 0.52, just over the range:
   miss. Kappa for `nothing_wrong` is 0.77: hit.
9. B's mean condition is under A's, and `awkward_layout` has a larger share in B: both hit.
10. `other_unit_or_renderings` has 11.2% in A against 8.3% in R: hit. It is not flagged.
11. `few_photos` has 18% in B against 7% in A: hit.

I expected group A to hold units with hidden faults. It holds well-kept units in large new
buildings, and that explains the misses on 3 and 5.

## Weaknesses of the design

- Group A's galleries are longer (median 12 photos against 7 and 8) and more of its ads have
  a plan (58 against 33 and 38), so its readers had more images. More images give more
  chances to mark a fault, which works against the direction found.
- An ad's agent chooses its photos. A fault left out of the gallery is invisible here and
  visible at a showing, so the check covers faults in the images and says less about faults
  known to the market.
- The scored table has a single reader for each ad, and both readers of the 60 repeats are
  the same model. No person graded any ad.
- The photos are 596 by 446 crops, and at most 8 of a gallery were read.
- 78% of B's ads were marked rented on the day they opened. Their galleries are thin records
  of deals made elsewhere, and B's faults may partly reflect the kind of agent posting them.
- The groups differ in building era and price level, so every raw contrast between them
  mixes the photos with the building. The fit with fields handles this for the grades only.
- The bar counted a grade difference in either direction, and the flag it raised is for
  better photos. The design had no prediction for that sign.
