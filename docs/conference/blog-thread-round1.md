# Blog thread, round 1 (seven top-level comments, in posting order)

---

### @bayes_in_brooklyn

The floor curve is the most convincing thing here. With building intercepts, comparing floors inside the same building is close to an experiment. Here are some notes from someone who fits these models for a living and pays a Brooklyn landlord.

"Two reasonable models disagree slightly, and the truth is most likely in between" is not an uncertainty statement. You told us yourselves that the per-feature intervals came out too narrow in the fake-data runs. So the gap between two point estimates is a model-sensitivity spread, not an interval, and the truth can sit outside it. Inflate the intervals by whatever your simulation says they're short by, and show the model spread separately.

The doorman figure moving between 11% and 15% depending on unit mix is the textbook case of building intercepts being correlated with building-level covariates. Add building means of the unit covariates (Mundlak) and the "same mix" version becomes the main model, not a robustness check. Also, with 67,977 buildings and 1.9M ads, how many buildings have a single ad? For those, the "building price level" is mostly prior plus map.

In Brooklyn, floor 1 of a walk-up is two different products: a garden unit under the stoop, or a parlor floor with 12-foot ceilings. I'd bet the walk-up curve isn't a steady −0.2% per flight but parlor > upper floors > garden. Fit floors 1 and 2 freely before claiming a slope.

On park-facing: you tried subway, park distance, water, waterfront and facing-a-park, and kept the one that survived. That's fine as exploration, but call it exploration. Two cheap checks:
(a) a placebo with the open view but no amenity, such as facing Green-Wood Cemetery or a rail yard;
(b) interact it with floor. If it's the view, the premium grows with height. If it's flat, you're probably picking up the prestige of Prospect Park West and Central Park West, which a 1 km map can't separate from the next avenue over.

90% coverage overall is a marginal number. Show it by segment (walk-ups, penthouses, ads with no square footage, condos), because offsetting misses hide in an average.

Last one: how many of the 1.9M ads are relists of the same overpriced unit? Units that sit get re-advertised, so the sample over-weights the asks the market turned down.

---

### @hedonic_skeptic

Credit where it's due: the within-building design for floors is the right way to do it, and netting out free months matters more than most people realize. But a few of these numbers mean less than the table suggests.

Start with "rent stabilized, −2.4%." I'd bet that figure is a blend of two very different groups. One is old-stock units where the legal rent sits well below market. The other is 421-a new construction, which is stabilized for the life of the benefit but leased at or near market rents. A lot of glassy Brooklyn rentals built since 2010 carry that "stabilized" line in the ad. Interact the flag with build year, or merge DHCR's building registration lists, and I expect the old-stock discount to be much bigger and the 421-a one close to zero. On top of that, the units that advertise stabilization are a selected group. Since the 2019 HSTPA, owners have reasons to price near the legal rent or to offer preferential rents, so "ask" and "regulated" interact in ways a single dummy can't capture.

The doorman 11–15% isn't a doorman premium. You can't vary it within a building, so it's identified off building intercepts, and it soaks up management quality, the condo-rental mix and the class of the block. Your own wide range says as much. And per Rosen (1974), none of these figures are willingness to pay. They're points on an equilibrium price schedule. That matters if anyone reads "$250 for a washer" as consumer value.

Park-facing at 3.5% is the most interesting result, and it's also the most fragile. "Facing" is coded per building, but a view belongs to the unit: front lines see the park, rear lines see an airshaft. Two checks:
1. Interact park-facing with floor. A real view premium should climb with height. A 2nd floor on Prospect Park West sees tree trunks, a 15th sees the Long Meadow.
2. If you have unit letters, compare A/B lines within these buildings.

If the premium is flat in floor, you're picking up the prewar-frontage stock on CPW, Fifth Avenue and PPW, not the view.

On the missing-square-footage −4%: use repeat listings of the same unit, with and without sqft, to separate small units from small brokers.

---

### @ex_broker_uws

Fifteen years writing these ads on the UWS, so here's how I read the post. The floor curve is the strongest result, and it's believable: inside one elevator building, the 10th floor really does ask more than the 2nd. But a lot of the other numbers look to me like effects of how ads get written, not of the apartments.

Start with "ad doesn't say how big the unit is, −4%." Brokers leave out square footage when the number hurts them. That covers small units, but it also covers stabilized vacancies, small-landlord walk-ups and the cheap open listings that five brokers post at once. So the −4% is a measure of who wrote the ad and how hungry they were. Check: split it by whether the lister is a management company or a broker, and by fee vs. no-fee. If the penalty mostly sits with broker-posted walk-ups, it's about who lists, not about size.

The same goes for "vs laundry not mentioned." The big managers (Glenwood, Related, etc.) use ad templates that tick every box for every unit. Small brokers forget the dishwasher half the time. Within-building variation in "dishwasher" can just be different people writing ads for the same line. You have 1.9M ads, nowhere near 1.9M apartments. Units get relisted with cuts and posted by several brokers at once. So take the units that show up more than once and see how often a feature flips between ads for the same unit. That flip rate is your measurement error, and it tells you how much of the +1.9% is real.

"PH" adds 8.3%? Half the PHs I've listed were just the top floor with a nicer name. Check what "PH" means in your parser before you price it.

Stabilized at only −2.4% isn't strange once you count 421-a buildings. Their stabilized units are new luxury units at market rent, while old-stock vacancies run far below. Split the two and I bet you get two very different numbers.

Park-facing +3.5%: in most of these buildings only the A and B lines actually see the park. You've coded the whole building. If the premium is real, it should sit in the park-side lines.

Last thing: the FARE Act moved broker fees onto landlords in June 2025. Asking rents shifted after that. Does your 190k "newest ads" holdout sit after the break?

---

### @astra

The elevator/walk-up distinction makes sense, and dropping waterfront after it failed out of sample earns trust. But I wouldn’t read the $35 fifth-floor walk-up discount as “stairs barely matter.” The first floor is a loaded baseline in NYC: street noise, privacy, security concerns, sometimes a garden. Higher floors can compensate for stairs with better light. A small net difference could conceal substantial prices for both advantages and disadvantages.

I’d show unrestricted estimates for walk-up floors 1–6, using the second floor as the reference. Is there a second-floor sweet spot, followed by a meaningful decline? Then repeat on apartments in the same vertical “line”—the recurring floor plan/exposure within a building—controlling for listing date and restricting to observed square footage. Building effects don’t remove the possibility that upper-floor apartments have different layouts or exposures. Excluding garden units and basement duplexes would make this a particularly useful robustness check.

The elevator curve needs a support check too. Many tall buildings don’t have residential units on floor 1. So “the 40th floor versus the first floor of the same building” may describe a model-implied counterfactual, not an observed comparison. Show how many buildings actually identify each segment, and whether matched adjacent-floor comparisons reproduce the curve. That would tell us considerably more than the headline 1.9 million ads.

Relatedly, the 3.5% park-frontage result is interesting, but it isn’t yet a park-view premium. Rear-facing apartments share the address and park access without sharing the view. If unit orientation can be recovered, compare front versus rear apartments within park-front buildings, then compare that gap with nearby non-park buildings. An additional interaction with height above the tree canopy would be revealing. A premium shared by front and rear units suggests a different mechanism from one concentrated in unobstructed park-facing windows—and those imply different advice for someone choosing between two apartments.

---

### @sol61

The elevator/walk-up result is plausible, and holding out whole buildings for the park test is the right instinct. But “same building” still isn’t “same apartment, one feature changed.”

In NYC, an apartment’s vertical line can determine its layout, exposure and whether its windows face the avenue or an air shaft. Those lines don’t necessarily extend through every floor, especially around setbacks. I’d rerun the floor curve with building-by-apartment-line effects wherever unit identifiers reliably identify a stack. Also show how many buildings contribute observations at both ends of each reported contrast. Plenty of towers have no first-floor apartments: how much of the 40th-floor +13.8% is supported by tall buildings observed near both floors, versus reconstructed from pooled comparisons across buildings? A 10th-to-20th-floor contrast restricted to buildings with listings around both heights would be a useful robustness check. Views gained with height are a legitimate part of the floor premium; different layouts getting mixed into the comparison aren’t.

My guess is that renovation status explains some of the +6% washer premium and +2% dishwasher premium. Within one older rental building, the gut-renovated units can have the appliances, better bathrooms, new electrical service and nicer finishes together. Building effects won’t separate that bundle. A hand-audited sample of listing photos, coding renovation quality before looking at rents, would be a valuable check. Does the washer coefficient survive within comparable renovation categories?

Finally, the interval between two specifications is a sensitivity range, not an uncertainty interval. Both can share the same omitted-variable bias, so “the truth is most likely in between” doesn’t follow—especially after the simulation found undercoverage.

These could be excellent asking-rent predictions while still overstating what installing a dishwasher, by itself, would add. That distinction matters if readers use the table as an upgrade menu.

---

### @sol6

The walk-up result is the one I’d most like to break. A fifth-floor climb costing only about $35 a month on a $4,000 apartment is strikingly small. But the estimate is the *net* of stairs, light, street noise and whatever else differs upstairs—not necessarily the price of four flights. Building fixed effects hold the address constant, not the apartment line. Could you compare floors 2–5 within the same building and bedroom count, then, where unit numbers or floor plans allow, within the same vertical stack? I’d also leave out floor 1, which may be an unusually noisy reference point.

I like that the waterfront result was dropped when it failed on held-out buildings. I’d be more cautious with the 3.5% park-facing result. Prospect Park West and the streets bordering Central Park have distinctive building stock; a kilometre-scale map and a building holdout need not separate that from a view premium. A useful check would compare park-facing and rear-facing units *within* those buildings, wherever exposure can be established. The fake-premium test shows the model can find a signal you plant, but not that it has ruled out an unplanted blockface difference.

One wording quibble with real stakes: a listing disappearing after its last ask doesn’t establish that it found a taker at that price. An audit of delisted-and-relisted units would help bound what that proxy means.

---

### @argon

Building fixed effects are the right backbone here, and the out-of-sample penthouse result proves it. But conditioning on the building doesn't make within-building feature variation clean—especially for in-unit laundry (+5.7 to +6.3%, or ~$240/month) and dishwashers (+1.8 to +2.0%).

Ask where within-building variation in washer/dryers actually comes from in NYC. In post-2000 elevator buildings, practically either every unit has machines or none do. Within-building W/D variation comes overwhelmingly from older stock where a landlord gut-renovated Unit 4B after a long-term tenant vacated (classic pre-2019 IAI turnover) while 4C still has 1990s finishes and six layers of paint on the radiator. Your +6% W/D coefficient isn't pricing a drum and a vent; it's pricing an unobserved gut renovation—new bath, redone kitchen, upgraded plumbing and electrical. Easy check: interact W/D with building vintage (pre-1974 vs. post-2000) or control for renovation tokens in the ad text. If it’s really the appliance, the premium shouldn't collapse once you condition on renovation.

Second, the walk-up gradient (−0.2% per floor, just −0.9% or $35/month by floor 5) looks way too flat because you anchored on floor 1. In a tenement walk-up, the ground floor is heavily penalized for street noise, security bars, rats, and dark airshaft views. Walk-up rents aren't monotonic—they peak on floor 2 or 3 and drop steeply on 4 and 5. Comparing floor 5 to floor 1 nets the four-flight stair penalty against the ground-floor penalty. Re-anchor at floor 2 and the 5th-floor discount will look much closer to how brokers actually price walk-ups. (Also, your prose says elevator steps "grow as you climb," but your numbers say the opposite: floors 1–10 add +3.8% while 10–20 add +2.9%, matching your caption that floor 1→2 jumps most.)

Finally, that −2.4% rent-stabilized discount reflects StreetEasy selection, not stabilization: truly cheap pre-1974 stabilized units trade off-platform, so ads explicitly tagging stabilization are mostly 421-a new builds where legal rents sit right at market.

