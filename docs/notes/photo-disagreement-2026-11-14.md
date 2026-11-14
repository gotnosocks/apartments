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
