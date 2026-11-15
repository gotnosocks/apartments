# Expert read of L2's worst held-out misses, 2026-11-15

This note records the first read of a fit's worst misses under `docs/expert-reads.md`. The fit is
L2, `drift-building-phase-unitkn-level` on the latest split
(`/data1/apartments/frontier/runs/drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn`).
No fit ran for this note. Every script and intermediate file is in
`/data1/apartments/tmp/expert-reads-2026-11-15/`.

## Drawing the sets

I took the held-out cdf of each ad's ask from L2's `pred_scores.npz` (189,647 held-out ads) and
lined it up with `rows.parquet` row by row, checking listing, building and log ask.

Before drawing anything I split the 36,207 held-out buildings in half at random, with seed
20261115 (`sample.py`):

- the read half has 18,103 buildings and 94,111 ads, listed in `buildings_read_half.txt`;
- the unread half is in `buildings_unread_half.txt`. Nobody has looked at its ads, so it stays
  free for checking candidates later.

Within the read half I dropped 118 income-restricted ads and sorted the rest into three sets.
`docs/expert-reads.md` sets net-effective asks aside before reading, but this read kept them in,
so they show up below as a trait counted in every set.

| set | rule | eligible ads | buildings |
|---|---|---|---|
| ask far above | cdf > 0.99 | 871 | 745 |
| ask far below | cdf < 0.01 | 1,066 | 872 |
| control | 0.25 <= cdf <= 0.75 | 48,951 | |

From each set I drew 120 ads after shuffling, keeping one ad per unit and at most two per
building.

## Reading

I mixed the ads into 18 blind groups of 19 to 21. Groups 0 to 8 each held 13 or 14 ads from the
far-above set and 6 or 7 control ads. Groups 9 to 17 did the same with the far-below set. Each
packet (`groups/gNN.json`) carried the ad's full text, its coded fields, amenities, features,
lease terms, source and photo count. I stripped every price and replaced dollar amounts in the
text with `$[amount]`. Floor plans linked from the stored pages were fetched under the standing
approval from 2026-10-15, 145 images for 137 ads, 10 seconds apart, into
`/data1/apartments/archive/floor-plans/`. Photos are not stored, so readers saw only their count.

Nine Sonnet readers took two groups each, with the brief in `READER.md`: read the whole ad and any
plan as a broker would, list the traits that matter to the price, mark the ones the coded fields
miss, and flag data errors on their own line. The 360 answers are in `answers/`, and `join.py`
attaches each one to its set.

## Counting traits

Readers write free text, so `tally.py` codes each candidate trait with a regular expression over
their traits, notes and summary, then counts it in each set with a Wilson 95% interval and a
Fisher test against control. The output is `candidates.csv`. A regex over reader prose misses some
mentions and catches some negations, so these counts are rough, and they are counts of what readers
noticed, not of what the ads hold.

The traits more common among the far-above ads than in control:

| trait | far above | control | Fisher p |
|---|---|---|---|
| duplex or triplex | 15% (10-22) | 4% (2-9) | 0.007 |
| garden-level unit or garden duplex | 14% (9-22) | 4% (2-9) | 0.012 |
| flex room, office or den beyond the coded bedrooms | 21% (15-29) | 9% (5-16) | 0.018 |
| private yard or garden | 19% (13-27) | 9% (5-16) | 0.04 |
| extra baths, en-suite bath per bedroom | 13% (8-21) | 5% (2-10) | 0.04 |
| gut or brand-new renovation | 25% (18-33) | 14% (9-22) | 0.05 |
| brownstone or townhouse | 12% (8-20) | 5% (2-10) | 0.07 |
| loft or live/work space | 10% (6-17) | 3% (1-8) | 0.07 |
| thin or empty ad text | 11% (6-18) | 4% (2-9) | 0.08 |

Among the far-below ads:

| trait | far below | control | Fisher p |
|---|---|---|---|
| low or ground floor | 20% (14-28) | 10% (6-17) | 0.05 |
| rent stabilized or other regulated ask | 8% (4-14) | 2% (0-6) | 0.06 |
| garden or courtyard outlook | 12% (7-19) | 5% (2-10) | 0.10 |
| photos of another unit, staged or AI | 12% (8-20) | 6% (3-12) | 0.12 |
| luxury doorman or amenity tower | 16% (10-23) | 31% (23-40) | 0.009 (less common) |

Low floors turn up twice as often in both miss sets (19% far above, 20% far below), so readers
spotted them as a source of spread. Several
themes I expected from the summaries came out flat against control once counted: net effective
asks and months free (9 to 12% in every set), walkups, co-op or condo units rented by their owners,
roommate layouts, high ceilings and views. With 120 ads a set, none of these p values survives a
correction for the 68 tests (34 traits, each against both miss sets), so the tables rank candidates for a check on the unread half
and do not establish any of them.

## Candidates and how to code them without the rent

Each candidate below can be coded from fields or ad text alone. L2 already has terms for
private gardens, patios and terraces, `garden` and `lower` floor flags, `penthouse`, `loft`,
`extra_rooms` and the bedroom and bath steps, so the question for each is whether the trait carries
price beyond those terms.

1. Multi-level units. A regex on the description and unit fields for duplex, triplex, two levels,
   lower level, or a basement inside the unit, plus a floor-plan count above one. L2 has no
   multi-level term. A garden duplex combines this with the existing garden flag, so an
   interaction is the natural second test.
2. Rooms beyond the coded bedrooms. Flag ads whose text names a home office, flex room, den,
   nursery or a convertible room, or whose title gives more bedrooms than the coded field. L2's
   `extra_rooms` comes from structured fields, so I would first check how often these ads already
   carry it.
3. Bath per bedroom. Coded baths divided by bedrooms, or full baths at least equal to bedrooms
   from two bedrooms up, from fields only. L2 has separate bed and bath steps without their ratio.
4. Renovation level. A regex for gut renovated, brand new, newly renovated, never lived in. The
   text has no counterpart in L2, and the control rate of 14% shows how common the phrase is, so
   the term would need a gut or brand-new subset to separate.
5. Brownstone or townhouse. Derived from the building rather than the ad: PLUTO building class
   for one-to-four family houses or a low height with a narrow lot, joined with the text words
   brownstone, townhouse and parlor floor.
6. Thin ads. Character count of the description after stripping boilerplate, coded as a short-text
   flag. The far-above set leans toward thin ads (11% against 4% control, p 0.08). The far-below
   set, at 8% (p 0.29), may differ from control by chance alone.
7. Regulated asks. A regex for rent stabilized, preferential rent, HPD and income limits, on ads
   with `rent_stabilized` false and `income_restricted` false. Two HPD ads in the far-below set
   escaped the income flag, which is a data fix before it is a feature.
8. Interior outlook. A regex for courtyard, rear-facing, garden-facing or interior views, which L2
   now codes as a garden view and so rewards.

## Data errors

Readers flagged something in most ads, much of it minor (thin text, staged photos, doubtful tags).
I kept the serious categories in `serious_errors.jsonl`: 35 far-above ads, 35 far-below ads and 16
control ads, 86 in all. Most are bedroom counts that disagree with the text or plan (19 far above,
13 far below, 6 control), bath counts that disagree (8 far above, 1 far below, 1 control) and text describing
another unit, or several units at once (3 far above, 11 far below, 6 control). Smaller groups are
lease assignments and short remaining leases (1 far above, 4 far below), a room in a share or co-living ad (2 far
below), commercial or raw space (2 far above), floor coding (10 across sets) and a sale listing
(1 far above). Bedroom undercounts in the far-above set and multi-unit ads in the far-below set
are fixes for the data thread before they are features.

## Next step

Code candidates 1 to 3 and 7 from fields and text on all ads, then count them on the unread half
of held-out buildings among the cdf > 0.99, cdf < 0.01 and control ads, without reading any of
those ads. A candidate goes forward only when the free check in `docs/expert-reads.md` passes on
that half, with `explained` above the 95th percentile of a shuffled-label null. It then gets a
single-term fit with its predictions written here first, and the fit's elpd for it is scored on
the unread half only.
