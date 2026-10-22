# A deeper goal for the apartments project

*Written 2026-10-15 for Ben, from the project instructions, the Oct 14 retrospective, the Oct 15 handoff, the Oct 8 research review and the feature-test record (`dashboard/tests.csv`). Where something is my judgment rather than a checked fact, it says so. Nothing here changes the project instructions; that's your call.*

## Where the project stands, in one paragraph

The current goal asks for a model that explains asking rents from an apartment's qualities. In practice the work has become a contest: add one feature, run one fit, keep it if it predicts held-out asks better. That contest has been won mostly by terms that describe rather than explain: each building's own price level, how much asks scatter by size and year, a smooth seasonal curve. Almost every explanatory feature tried so far (quiet street, parks, subway lines, jobs within reach, retail, orientation, rear windows) came back "no clear effect", and the recorded reason is that the building's own price term soaks up anything that is the same for every apartment in a building. The new-building error has sat at about 12% through every model change since early October. So the project is very good at *predicting* the next ask in a building it already knows, and has learned little about *why* rents are what they are. That gap is what a deeper goal should close.

## 1. What a top professional would do that you aren't asking for

By "top professional" I mean an urban or real-estate economist who estimates what housing qualities are worth (the field is called hedonic pricing), working with a strong applied statistician.

1. **Define the question before scoring answers.** "How rents are composed" can mean two different things. One is prediction: which numbers best forecast an ask. The other is value: how much more a renter pays for an apartment that is identical except for one quality (a park view, two more subway lines, a renovated kitchen). The professional would commit to the second, because it is the one that "explains". The current scoring rule rewards the first, which is why descriptive terms keep winning.
2. **Treat the ask as a move in a market, not as the price.** An asking rent is a landlord's or broker's opening offer. What happens next (the ad sits, gets cut, rents in a week, or is pulled) shows how far the ask was from what a renter would actually pay. The professional would model the price and the time to rent together, so "overpriced" and "fairly priced" mean something measurable.
3. **Replace place labels with a map, then explain the map.** Instead of a price level per neighbourhood or building, they would fit a smooth surface of "location value" across the city and then ask which measurable things (light, transit, parks, noise, schools, history) account for its hills and valleys. What remains unexplained is honestly labelled "this place is fashionable".
4. **Look for natural experiments.** The cleanest evidence about what a quality is worth comes from moments when it changed and little else did: the Second Avenue subway opening (2017), the 7 train reaching Hudson Yards (2015), High Line sections opening, a rezoning, a school-zone line drawn down the middle of a street. Comparing the same kinds of apartments on either side of such a change, before and after, measures the quality's worth far more convincingly than a cross-section can.
5. **Measure apartment quality directly.** The biggest hidden factor in rents is usually condition: renovated or not, light, finishes. It hides inside the building term and makes everything else look weaker or stronger than it is. A professional would score it from the photos and floor plans rather than leave it unobserved.
6. **Prove the method works before trusting its answers.** They would make fake data where they set the true worth of each quality, run the whole pipeline on it, and check it recovers those values. This is the only way to know the factor-by-factor breakdown is right, since no one has the true breakdown for real data.
7. **Make dated forecasts and let the world score them.** Not just held-out tests on old data, but predictions written down for ads that don't exist yet, scored when they appear.

## 2. The rawest material, instead of what has already been digested

What the model reads now is mostly digested twice: brokers and StreetEasy typed it into fields (bedrooms, size, amenity flags, neighbourhood), and the pipeline then summarised it further (subway lines within 8 minutes, "busy street" flags). The professional would go back to:

- **The ad itself, as pixels and words.** Every photo, the floor plan image, and the full description, rather than the coded fields. Size, layout, light, condition and finish are in there, and so are the errors the coded fields carry (the 970 "studios" priced like 3-bedrooms were a symptom of trusting the fields).
- **The ad's whole life.** Every event in its history: first ask, each cut, days on market, rented or withdrawn, and the unit's earlier and later ads. The API collection already returns full price histories, so much of this is in hand; it just isn't used as evidence about the market.
- **The physical city.** The city's LiDAR point cloud and 3-D building models (to compute, per window, how much sky and which park or river it sees), street-level traffic counts and noise sensors, and the actual subway timetables and station entrances, from which travel time to anywhere can be computed rather than summarised as "lines nearby".
- **Records of rents people actually pay, kept by someone else.** The NYC Housing and Vacancy Survey (the Census Bureau's survey of apartments, with the rent each household pays and the unit's condition), the Department of Finance's reported rental income per square foot for rental buildings (published as comparables for condo valuations), the state's lists of rent-stabilised buildings, and Department of Buildings certificates of occupancy (legal unit counts and layouts). These are the only sources of truth about rent that StreetEasy didn't produce.

I haven't checked how much of each is downloadable today or how well it matches our buildings; the first step of a new goal would be to find out, using free checks.

## 3. Methods and tools they would use

- **Hedonic pricing** (Rosen's framework): the price of an apartment is the sum of what renters pay for each of its qualities. This is what the project is already doing in spirit; it supplies the vocabulary and the known pitfalls.
- **Spatial models**: a smooth location surface (a Gaussian process, or the spatial smoothing used in disease mapping, called BYM2) in place of neighbourhood and building labels. Tools: the existing Bayesian stack (Stan or NumPyro on Modal), or R-INLA, which fits such surfaces fast.
- **Boundary and before-and-after designs**: comparing apartments just either side of a school-zone or historic-district line, and difference-in-differences or event studies around a station or park opening.
- **Repeat rents**: comparing the same unit's asks over time, which removes everything fixed about the unit and isolates what changed (a renovation, a new station, the market).
- **Time-to-rent (survival) models** fitted jointly with the price, so the model says both what an apartment asks and how long it would sit at that ask.
- **Computer vision**: image models (for example CLIP-style embeddings, or a small model trained on a few hundred hand-labelled photos) to score condition, light and finish; floor-plan parsing to measure rooms.
- **Ray-casting on LiDAR** (tools like PDAL and Open3D) for light and views per apartment line.
- **Simulation-based calibration**: run the whole fitting pipeline on fake data with known answers and check it gets them back, with honest uncertainty.
- **Double machine learning** where a flexible model handles location and the rest, so the worth of one quality can be estimated without the building term swallowing it.

## 4. What, other than you or me, would show the result is right

1. **The future.** Forecasts, with ranges, for ads posted after the model was frozen, written down before they appear and scored when they do. If the 80% ranges contain about 80% of new asks in buildings the model has never seen, that is evidence neither of us can manufacture.
2. **The market's own reaction.** If the model's price is right, ads priced well above it should sit longer and get cut toward it, and ads priced below it should rent fast. The model never sees time on market when it's fitted, so this is a genuinely independent test.
3. **Other people's rent records.** Agreement, area by area and building by building, with the Housing and Vacancy Survey and the Department of Finance's rental income figures, allowing for the known gap between asks and rents actually paid.
4. **Known answers.** Recovery of the true values from simulated data (see §3). This is what shows the factor-by-factor breakdown can be trusted.
5. **Published estimates.** Natural-experiment results (a new station, a park) landing near what independent researchers have published for similar changes.
6. **An outside expert.** In the end, a write-up a housing economist could read and not find a basic flaw in. This is optional, but it is the field's normal standard.

## 5. Proposed new project goal

> **Find out what each quality of a New York apartment is worth to renters, and show it in ways that don't rest on our own judgment.** "Worth" means the difference in rent between two apartments that are alike except for that quality. Work from the rawest material available: each ad's photos, floor plan, text and full history (how long it sat, whether it was cut, whether it rented); the physical city (building geometry, light and views, transit as it actually runs); and independent records of rents people actually pay. Treat location as a map of value to be explained by things you can measure, not as a label, and use the city's natural experiments (new stations and parks, rezonings, school-zone lines) wherever a quality changed and little else did. A result counts as established only when something outside the model agrees with it: dated forecasts of ads not yet posted, the market's own reaction (overpriced ads sit longer and get cut), independent rent records, and recovery of known answers from simulated data. Prediction accuracy remains a check, not the goal.

## 6. What would change in practice, if you adopt it

This is not more work of the same kind. It replaces some of it.

- **Scoring.** The one-feature-at-a-time prediction contest stops being the main test. A feature is judged by how much of the location map and building differences it explains, and by whether its worth holds up in the independent checks above.
- **First moves (all cheap).** Run the market-reaction test on the served model (free, uses data in hand). Check what the Housing and Vacancy Survey and the Department of Finance income data cover for our buildings (free). Run the fake-data recovery test on the current model (one Modal fit). Start the photo condition score that the Oct 13 plan already ranked highly.
- **What stops.** New "nearby X" features computed from summaries, until the location map exists for them to explain.
- **What doesn't change.** The budgets, the one-hour cap, the data-before-fit rule, corrections needing independent evidence, the scientific record, and serving the best model on the site.
