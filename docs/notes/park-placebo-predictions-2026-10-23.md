# Park frontage by line, by floor and against placebo frontages: predictions, 2026-10-23

This test answers objections 8 and 9 on the research board (`20261023T031332Z-conference-open-objections-to-the-building-zones-fl`). The floor model with `bld:park_front` puts a building whose outline lies within 40 m of a park of 5 acres or more at +4.2 points of log rent on the latest split and +3.8 on the whole-building split (`building-zones-floor-parkfront-2026-10-22.md`). Reviewers raise two doubts:

- Objection 8: I code frontage per building, but only some lines of a building look onto the park. If the premium comes from the view, it should sit in those lines.
- Objection 9: the premium may come from the prestige of the housing stock on Central Park West, Fifth Avenue and Prospect Park West. If so, frontage on large open land with no amenity should earn something too, and the premium should not rise with height, as a view premium would.

I wrote these predictions after counting rows and before running any regression or looking at rents in these groups.

## Data

I counted rows with `park-placebo-2026-10-23/counts.py`; its output is `park-placebo-2026-10-23/counts.json`. The rows are those of the frontier dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, without shared-space ads (1,866,262 ads), joined by listing id to the pipeline rows `rows-b3ddebf19af1dc1e`.

Park frontage comes from the snapshot the model reads, `external/building-park-front/20261022-5ddc0e5d`. As controls I take nearby buildings 40 to 200 m from such a park, the same ring as the free check before the first parkfront fit.

| group | ads | buildings | units |
|---|---|---|---|
| park-facing (under 40 m) | 58,888 | 1,118 | 26,178 |
| nearby (40 to 200 m) | 252,085 | 8,131 | 119,831 |

I mark a unit as having a park view in two ways:

1. StreetEasy's structured field `view_exposures.park`, filled on 8,598 park-facing ads.
2. The ad's own text, from the description evidence files joined on source listing id, matched against phrases such as "park views", "overlooks the park" and "facing the park". Text is on file for 46,503 park-facing ads (79%), and 8,312 of them match.

The two sources agree poorly. Among park-facing ads with text, 4,941 carry both marks, 3,371 only the field and 2,657 only the text. I take a unit as having a view when either mark is set, which gives 11,969 park-facing ads, and 13,772 ads in nearby buildings.

For the unit's line I parse the label at the end of the ad's page URL: `4d` gives floor 4 and line D. This works for 34,635 park-facing ads, in 574 buildings with two or more lines. Another 4,347 labels name a front or rear unit (`3f`, `3r`). The floor comes from `listed_floor`, or from the label where that is missing, and is known for 46,761 park-facing ads (79%). StreetEasy's window exposure field is filled on only 8,193 park-facing ads, too few for a geometric test of which side faces the park, so I leave it out.

Inside park-facing buildings, 660 buildings hold both view and non-view ads (51,040 ads). At the level of lines, I call a line a view line when at least half its ads carry a view mark. Then 311 buildings hold both kinds of line: 1,006 view lines with 6,504 ads and 1,430 other lines with 13,054 ads. Half of the lines with two or more ads have mixed marks, so the mark is noisy at the ad level, and I expect that noise to pull the ad-level coefficient toward zero.

For placebo frontages I take lot polygons from MapPLUTO 26v2, fetched from City Planning's ArcGIS feature service (`MAPPLUTO/FeatureServer/0`; lots of 2 acres or more in Manhattan, Brooklyn and Queens with land use 07, 10 or 11 or building class Z or U; 852 lots). I keep two kinds of open land:

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

1. Lines, within buildings (objection 8). On park-facing ads I add a building fixed effect and the view mark, so the coefficient compares view and non-view units in the same building. I fit it twice: with the ad-level mark, and with the line-level mark on the 311 buildings with both kinds of line. A floor term (floor bins of 0 to 2, 3 to 5, 6 to 10, 11 to 20 and 21 up) enters as a control, since view units sit higher. The permutation null shuffles the mark among ads of the same building, or among lines of the same building for the line version, 200 times.
2. View units in nearby buildings. The same within-building fit on the nearby ring tells whether a park view from 40 to 200 m away earns a premium of its own.
3. Non-view units across buildings. I compare non-view ads in park-facing buildings with non-view ads in nearby buildings, using a fixed effect for the 150 m cell in place of the building effect and keeping only cells that hold both kinds of building. This gap is the part of the building premium that no view mark explains.
4. Floor (objection 9). On park-facing and nearby ads together, with building fixed effects, I interact the park-facing flag with the floor bins. The building effect absorbs the flag itself, so the interactions measure how the premium changes with height against the floor gradient of nearby buildings. Within park-facing buildings I also interact the view mark with the floor bins.
5. Prestige (objection 9). I split the between-building gap of fit 3, computed for all ads, into buildings on Central Park West, Central Park South, Fifth Avenue, Prospect Park West and Riverside Drive (about 220 buildings, 8,200 ads) and the rest.
6. Placebo frontages (objection 9). For each placebo kind I compare front buildings with nearby buildings in the same 150 m cells, as in fit 3, for all ads. The permutation null for fits 3, 5 and 6 shuffles the front flag among buildings of the same cell 200 times.

## Predictions

- Fit 1: within park-facing buildings, view ads sit 2% to 6% above non-view ads on the same floor bin, with a 95% interval excluding 0 and the coefficient beyond the null's 95th percentile. The line-level coefficient is larger than the ad-level one, at 3% to 9%.
- Fit 2: in nearby buildings, view ads sit 1% to 5% above non-view ads in the same building, and below the fit 1 coefficient.
- Fit 3: non-view ads in park-facing buildings still sit 1% to 3.5% above non-view ads in nearby buildings of the same cell. So I expect the view to carry a third to a half of the building premium, and the rest to stay with the building.
- Fit 4: the park-facing premium on floors 11 and up exceeds that on floors 0 to 2 by 1 to 5 points, and the view mark's premium rises with floor in the same direction. The difference has a 95% interval excluding 0 for the building flag; for the view mark it may not.
- Fit 5: the gap for the prestige avenues is 4% to 9%, and for the other park-facing buildings 1.5% to 4.5%, still positive with an interval excluding 0.
- Fit 6: the rail frontage gap falls between -4% and +2%, with an interval including 0. The cemetery gap falls between -6% and +3%, but with two buildings holding most ads its SE will be near 3 points and I won't read it as a test. The expressway gap falls between -4% and -0.5%, below 0 and below the park gap by more than 2 SE.

If the line-level coefficient comes out near zero while the non-view gap holds the whole building premium, I'll record that the park premium in this data is a building trait, not a view, and add it to the paper's limits.
