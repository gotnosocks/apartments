The floor curve is the most convincing thing here. With building intercepts, comparing floors inside the same building is close to an experiment. Here are some notes from someone who fits these models for a living and pays a Brooklyn landlord.

"Two reasonable models disagree slightly, and the truth is most likely in between" is not an uncertainty statement. You told us yourselves that the per-feature intervals came out too narrow in the fake-data runs. So the gap between two point estimates is a model-sensitivity spread, not an interval, and the truth can sit outside it. Inflate the intervals by whatever your simulation says they're short by, and show the model spread separately.

The doorman figure moving between 11% and 15% depending on unit mix is the textbook case of building intercepts being correlated with building-level covariates. Add building means of the unit covariates (Mundlak) and the "same mix" version becomes the main model, not a robustness check. Also, with 67,977 buildings and 1.9M ads, how many buildings have a single ad? For those, the "building price level" is mostly prior plus map.

In Brooklyn, floor 1 of a walk-up is two different products: a garden unit under the stoop, or a parlor floor with 12-foot ceilings. I'd bet the walk-up curve isn't a steady −0.2% per flight but parlor > upper floors > garden. Fit floors 1 and 2 freely before claiming a slope.

On park-facing: you tried subway, park distance, water, waterfront and facing-a-park, and kept the one that survived. That's fine as exploration, but call it exploration. Two cheap checks:
(a) a placebo with the open view but no amenity, such as facing Green-Wood Cemetery or a rail yard;
(b) interact it with floor. If it's the view, the premium grows with height. If it's flat, you're probably picking up the prestige of Prospect Park West and Central Park West, which a 1 km map can't separate from the next avenue over.

90% coverage overall is a marginal number. Show it by segment (walk-ups, penthouses, ads with no square footage, condos), because offsetting misses hide in an average.

Last one: how many of the 1.9M ads are relists of the same overpriced unit? Units that sit get re-advertised, so the sample over-weights the asks the market turned down.
