# Best-apartment score from the rent model: pros and cons

Draft for Ben, 2026-10-06. The coefficients come from the served three-neighbourhood fit (m7 + noise by year). They are in log points, which is roughly %.

**A coefficient is a price, not a utility.** Its sign says whether the market pays for something. Whether that thing is a pro for you is a separate call. So each feature gets a class, not just a sign. For example:
- an elevator raises rent and is a pro;
- a concession lowers rent and is also a pro;
- a strongly negative building effect lowers rent and is probably a con.

## A. Real qualities: pro, and the market pays for them
- **Space:**
  - square feet vs the bedroom median: +0.245 per log unit
  - bathrooms: 2 is +26%, 3 is +53%
  - half bath: +9%
  - extra rooms: 3 is +1.1%, 4+ is +2.2%
  - duplex: +2.9%
- **Height and light:**
  - floor: above 6 is +4.4% and above 15 is +8.8% per log floor
  - penthouse: +12%
  - west windows: +0.8%
  - courtyard or rear facing: +0.4%
- **Outdoor space:** private outdoor +2.6%, roof deck +2.1%, patio +1.6%, terrace +1.4%.
- **In-unit features:** laundry +1.5%, dishwasher +0.8%, renovated +1.2%, fireplace +0.6%.
- **Building:**
  - elevator: no elevator is −0.7%, and higher floors in a walk-up are −0.5% per log floor
  - part-time doorman: +1.2%
  - large average unit size: +0.196 per log unit (a luxury-building signal)
  - condo, class R: +9.6%
  - newer building: 1990–2009 is +14%, 2010+ is +16%

Building-wide amenities (elevator, doorman, gym, era) look small because the per-building effect absorbs most of their value. They should get your weight, not just their coefficient.

## B. Real negatives: con, and the market discounts them
- Lower level: −8.6%.
- Avenue or wide-street frontage on floors 1–4: −0.2% and −0.9% (noise).
- Walk-up class C: −10%.
- Class S, mixed use with retail below: −12% (noise, smells, deliveries).
- Dense lot (high built FAR): −0.074 per log unit.
- Ad claims fewer bedrooms than coded: −4.8% (usually a flex or converted room).

## C. Deal terms: lower rent, but a pro for a renter
- Concession: −1.0%.
- No fee.
- Rent stabilized: −1.9%. Legal protection and capped increases make this a strong pro.
- Income restricted: −32%. A pro only if you qualify.
- Furnished and short-term are taste: neutral, or a con for most.

These improve value for money. The score credits them instead of reading them as low quality.

## D. Location and taste: your weight, no fixed sign
- Neighbourhood: West Village +11.7%, Greenwich Village +7.8%, both against Chelsea.
- Era: pre-war vs new construction.
- Historic district, landmark, views, pets policy, exposed brick, high ceilings.

The market barely prices most of these (under 1%), so your weight should dominate.

## E. Hidden quality: the residual effects
- **Building effect** (sd about 16%): what a building rents for beyond its features. A strongly negative one usually reflects something we don't measure, such as condition, management, noise or layout.
- **Unit effect** (sd about 3.4%, stable across relistings): the same signal for a single apartment.
- **Building trend:** a building drifting down against the market is a soft con.

The model alone can't tell hidden inferiority from underpricing. An effect that persists across many units and years points to inferiority.

## F. Excluded from scoring (artefacts)
- All unknown or missing flags.
- Missing description, price basis, relisting timing.
- "States more bedrooms than coded" (a coding mismatch).
- Gym (−0.5%) and water view (−0.2%) are confounded.

## How the score works, with no new model
For each listing and each posterior draw:
- **Quality** = the A features − the B features + your weights × the D features + a share of the building and unit effects.
- **Value** = quality − log(asking rent) + credit for the C terms.

Ranking listings by value, with uncertainty from the draws, gives "best apartment for my preferences". A listing page can show its top three pros and cons from the same sums.
