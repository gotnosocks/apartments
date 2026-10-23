# Park frontage by line, by floor and against placebo frontages: predictions, 2026-10-23

This test answers objections 8 and 9 on the research board (`20261023T031332Z-conference-open-objections-to-the-building-zones-fl`). The floor model with `bld:park_front` puts a building whose outline lies within 40 m of a park of 5 acres or more at +4.2 points of log rent on the latest split and +3.8 on the whole-building split (`building-zones-floor-parkfront-2026-10-22.md`). Reviewers raise two doubts:

- Objection 8: I code frontage per building, but only some lines of a building look onto the park. If the premium comes from the view, it should sit in those lines.
- Objection 9: the premium may come from the prestige of the housing stock on Central Park West, Fifth Avenue and Prospect Park West. If so, frontage on large open land with no amenity should earn something too, and the premium should not rise with height, as a view premium would.

I wrote these predictions after counting rows and before running any regression or looking at rents in these groups.

## Data

I counted rows with `park-placebo-2026-10-23/counts.py`; its output is `park-placebo-2026-10-23/counts.json`, and every count in this note comes from that file. The rows are those of the frontier dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, without shared-space ads (1,866,262 ads), joined by listing id to the pipeline rows `rows-b3ddebf19af1dc1e`.

Park frontage comes from the snapshot the model reads, `external/building-park-front/20261022-5ddc0e5d`. As controls I take nearby buildings 40 to 200 m from such a park, the same ring as the free check before the first parkfront fit.

| group | ads | buildings | units |
|---|---|---|---|
| park-facing (under 40 m) | 58,888 | 1,118 | 26,178 |
| nearby (40 to 200 m) | 252,085 | 8,131 | 119,831 |

I mark a unit as having a park view in two ways:

1. StreetEasy's structured field `view_exposures.park`, filled on 8,598 park-facing ads.
2. The ad's own text, from the description evidence files joined on source listing id, matched against phrases such as "park views", "overlooks the park" and "facing the park". Text is on file for 46,503 park-facing ads (79%), and 8,312 of them match.

The two sources agree poorly. Of the park-facing ads with either mark, 4,941 carry both, 3,657 only the field and 3,371 only the text, for 11,969 in all. Restricted to ads with text on file, the field-only count drops to 2,657, and the other 1,000 field-only ads have no text to check. I take a unit as having a view when either mark is set, which gives those 11,969 park-facing ads and 13,772 ads in nearby buildings. I loaded text for the nearby rings of every placebo kind as well, expressways included.

For the unit's line I parse the label at the end of the ad's page URL: `4d` gives floor 4 and line D. This works for 34,635 park-facing ads, in 574 buildings with two or more lines. Another 4,347 labels name a front or rear unit (`3f`, `3r`). The floor comes from `listed_floor`, or from the label where that is missing, and is known for 46,761 park-facing ads (79%). StreetEasy's window exposure field is filled on only 8,193 park-facing ads, too few for a geometric test of which side faces the park, so I leave it out.

Inside park-facing buildings, 660 buildings hold both view and non-view ads (51,040 ads). At the level of lines, I call a line a view line when at least half its ads carry a view mark. Then 311 buildings hold both kinds of line: 1,006 view lines with 6,504 ads and 1,430 other lines with 13,054 ads. Of the 2,765 park-facing lines with two or more ads, 49% have mixed marks, so the mark is noisy at the ad level, and I expect that noise to pull the ad-level coefficient toward zero.

For placebo frontages I take lot polygons from MapPLUTO 26v2, fetched from City Planning's ArcGIS feature service (`MAPPLUTO/FeatureServer/0`; lots of 2 acres or more in Manhattan, Brooklyn and Queens with land use 07, 10 or 11 or building class Z or U; 852 lots). Of those I keep 70 cemetery lots and 169 rail lots:

- cemeteries, building class Z8;
- rail land: lots with building area under a tenth of lot area, owned by the MTA, the LIRR, NYC Transit or Amtrak, or of class U6.

I merge touching lots of a kind into one tract, keep tracts of 5 acres or more, and measure each building with the same code as the park snapshot (`building_park_front.table`). I also trace expressway centerlines (`rw_type` 2 in the basemap) the same way. Park-facing buildings are left out of every placebo group.

| placebo | front ads | front buildings | nearby ads (40 to 200 m) | nearby buildings |
|---|---|---|---|---|
| cemetery | 553 | 29 | 3,946 | 333 |
| rail | 2,030 | 39 | 21,872 | 807 |
| expressway | 26,678 | 628 | 141,586 | 4,349 |

The cemetery group is all on the Bushwick edge of the Evergreens and Most Holy Trinity cemeteries, and two buildings hold 421 of its 553 ads. Green-Wood and Trinity cemeteries have no dataset building within 40 m. The rail group sits mostly along the Vanderbilt Yard in Prospect Heights and the LIRR's Atlantic Branch along Dean Street in Crown Heights, with 100 ads at 35 Hudson Yards beside the West Side Yard. An expressway is a source of noise as well as open land, so I treat it as a check on direction more than as a clean placebo.

## Design

I fit ordinary least squares regressions on log latest ask, with no Bayesian model and no Modal time. Every fit has fixed effects for calendar month of the latest-ask day and for bedrooms by full baths. Standard errors are clustered two ways, by building and by week of the latest-ask day.

1. Lines, within buildings (objection 8). On park-facing ads I add a building fixed effect and the view mark, so the coefficient compares view and non-view units in the same building. I fit it twice: with the ad-level mark, and with the line-level mark on the 311 buildings with both kinds of line. A floor term (floor bins of 0 to 2, 3 to 5, 6 to 10, 11 to 20 and 21 up) enters as a control, since the view mark varies with floor: 29% of park-facing ads on floors 0 to 2 carry it, and 15% on floors 21 and up. Ads repeat by unit, so the permutation null moves marks a unit at a time: in each of 200 draws I shuffle unit ids within the building, and each ad takes a mark drawn with replacement from the ads of the unit its own unit maps to. For the line version I shuffle the line marks among lines of the same building.
2. View units in nearby buildings. The same within-building fit on the nearby ring tells whether a park view from 40 to 200 m away earns a premium of its own.
3. Non-view units across buildings. I compare non-view ads in park-facing buildings with non-view ads in nearby buildings, using a fixed effect for the 150 m cell in place of the building effect and keeping only cells that hold both kinds of building. This gap is the part of the building premium that no view mark explains.
4. Floor (objection 9). On park-facing and nearby ads together, with building fixed effects, I interact the park-facing flag with the floor bins, with floors 0 to 2 as the base. The building effect absorbs the flag itself, so the interactions measure how the premium changes with height against the floor gradient of nearby buildings. I pool the top two bins into "11 and up" as the average of the 11 to 20 and 21 up interactions, weighted by park-facing ads in each (10,765 and 5,704), and its difference from the base is that average. Within park-facing buildings I also interact the view mark with the floor bins and pool them the same way, so the view mark's rise is its 11 and up interaction against floors 0 to 2.
5. Prestige (objection 9). I split the between-building gap of fit 3, computed for all ads, into buildings on Central Park West, Central Park South, Manhattan's Fifth Avenue, Riverside Drive and Prospect Park West (210 buildings, 7,876 ads) and the other 908 park-facing buildings (51,012 ads). The list of avenues is fixed in `counts.py`, with Fifth Avenue matched only in Manhattan.
6. Placebo frontages (objection 9). For each placebo kind I compare front buildings with nearby buildings in the same 150 m cells, as in fit 3, for all ads. The permutation null for fits 3, 5 and 6 shuffles the front flag among buildings of the same cell 200 times.

## Predictions

On 2026-10-23, after review and before any rent regression, I corrected the overlap counts and the floor sentence, moved the permutations to the unit, and added the implied view share in fit 3, the pooling rule in fit 4, the criterion in fit 5 and the threshold in the closing paragraph. The predicted ranges are unchanged.

- Fit 1: within park-facing buildings, view ads sit 2% to 6% above non-view ads on the same floor bin, with a 95% interval excluding 0 and the coefficient beyond the null's 95th percentile. The line-level coefficient is larger than the ad-level one, at 3% to 9%.
- Fit 2: in nearby buildings, view ads sit 1% to 5% above non-view ads in the same building, and below the fit 1 coefficient.
- Fit 3: non-view ads in park-facing buildings still sit 1% to 3.5% above non-view ads in nearby buildings of the same cell. Against a building premium of 3.8 to 4.2 points, that gap leaves the view between 8% and 76% of the premium. I score the gap, and the share follows from it.
- Fit 4: the park-facing premium on floors 11 and up exceeds that on floors 0 to 2 by 1 to 5 points, with 11 and up pooled as in the design, and the view mark's 11 and up interaction is positive. The difference has a 95% interval excluding 0 for the building flag; for the view mark it may not.
- Fit 5: the gap for the prestige avenues is 4% to 9%, and for the other park-facing buildings 1.5% to 4.5%, still positive with an interval excluding 0. The prestige avenues are park frontages too, so their gap alone can't separate prestige from the park. I'll count the result against prestige if the other park-facing buildings keep at least half of the avenue gap, and for it if they keep less than a quarter.
- Fit 6: the rail frontage gap falls between -4% and +2%, with an interval including 0. The cemetery gap falls between -6% and +3%, but with two buildings holding most ads its SE will be near 3 points and I won't read it as a test. The expressway gap falls between -4% and -0.5%, below 0 and below the park gap by more than 2 SE.

If the line-level coefficient comes out near zero, meaning under 1% with a 95% interval including 0, while the non-view gap holds the whole building premium, I'll record that the park premium in this data is a building trait, not a view, and add it to the paper's limits.
