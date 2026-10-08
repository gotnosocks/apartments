# Website backlog (on hold)

Ben put website features on hold on 2026-10-05 (18:22 UTC). Playtests go on with the
`best-1bed` persona only, one per round, and their findings are logged here, unbuilt.
Fixes for things that are broken or wrong on the live site still ship.

Each round adds a section at the top, ranked by how much the finding gets in the way of
finding the best one-bedroom. Reports are in `/data1/apartments/tmp/playtests/<round>/`.

## Story round 3 (story-reader, economist), 2026-10-08

Reports in `/data1/apartments/tmp/playtests/2026-10-08-story3/`. The story fixes shipped in #505.
The economist's findings outside the story are logged here, unbuilt (coordinator, 2026-10-08
10:33 UTC: the feature hold applies):

1. **Rent map: observed median ask and counts.** Draw the median ask per year on the same chart
   as the typical-rent line, show how many listings back each cell, and link a cell to its
   listings. West Village 1 BR 2019→2026 reads +41% on the map against +49% in median asks.
2. **Versioned citation.** A "cite this" with the served run id and data snapshot id, or URLs
   that carry them, so a cited figure doesn't move with each refit.
3. **Calibration breakdowns.** Coverage by neighbourhood, bedroom count, price band and building
   size, not only overall and by year.
4. **Home "Available now (… only)".** Say why current listings cover three of the five
   neighbourhoods.
5. **Methods and data note.** One page to cite: source, crawl frequency, re-lists, how unit
   identity is inferred, thin early years (692 listings in 2010), and a data dictionary for
   listings.csv (which also lacks the 95% bounds).
6. **The served fit's "servable: no" row** (fit with quarantine-v6, current rules v10) read as a
   stale fit; passed to Modeling.

## Round 11 (best-1bed, /best after the commute, bed-size and low-floor pills), 2026-10-06

One persona, starting at `/best?beds=1` (`/data1/apartments/tmp/playtests/2026-10-06-r11/`).
It shortlisted three in about 9 page loads but ignored the ranking:

1. **The ranking is someone else's sheet.** ben-v1's commute, high floors and "rents above similar
   buildings" are not this persona's wishes, and it can't change them. Let a visitor pick or edit
   a sheet, or say plainly that the page ranks for Ben.
2. **No feature filters on /best.** Laundry, elevator, doorman, floor range, neighbourhood, size
   and facing are on /listings but not /best, so it scanned 100 rows by eye.
3. **Size, floor and elevator as columns** on /best, and Views (garden, skyline).
4. **A compare view** for two or three units side by side.
5. **Explain the marks**: Fit, the `*`, and "(ad)" on the bed-size pill. Say why a cheap ask may
   be cheap (what the model can't see, how wide the range is).
6. **Unanswerable wishes**: floor-through, bedroom facing, garden and a quiet block are still not
   shown (Data improvements has quiet-street, garden and floor-through tables in `wishes/`).

Fixed (a wrong page, not a feature): a listing whose ad gives no size showed "Size: not stated"
while the model used the size from the unit's earlier ad, so /best said "more space than usual".
The listing page now shows that size and says it came from the unit's earlier ad.

## Ratings, removed 2026-10-06

Ben asked for the "My ratings" view and its form to come off the site (21:02 UTC); the feature
can come back later. It was a "Your rating" card on listing pages (1–5 stars, plus and minus
tags, a note), a star in listing tables, and `/ratings` with CSV and JSON downloads, kept in a
local SQLite file. No rating was ever saved, so nothing was stored. The code is in git at
`archive/pr-285` and in the commit that removed it; bring it back from there, and consider feeding
saved ratings into the Best for you sheet.

## Ben on /best, 2026-10-06

Ben went through the Best for you shortlist listing by listing (16:45 UTC, relayed). Some of these
came from the default sort ("Fits you, at a good price"), some from "Fits you"; he didn't say which.
The ranks in brackets are for 1 BR on the live build at 16:50 UTC, as (at a good price / fits you).
His filters weren't recorded, so his own ranks may differ. Data improvements is taking the new
location features. Website adds the site-side parts (a "fronts a big street" minus, a transit or
commute pill) once those fields exist.

Location misses, all from big streets or poor transit, which the model doesn't price yet:

- **3 Eleven 2105** (28 / 13): unfavourable street and location. 30th St is a large crosstown
  traffic street, with weak street-level amenities; like 507 West Chelsea, north-west Chelsea
  with bad transit.
- **Ohm 26A** (20 / 18): the same 30th St. Ben commutes to midtown, and the subway access is bad
  (a J train trip with transfers is unappealing).
- **507 West Chelsea 12D** (62 / 27): north-west Chelsea, bad transit.
- **Ava High Line 844** (25 / 36): appears to front 28th St; the same transit issue.
- **225 West 14th St 5F** (43 / 59): a **missing minus**. It overlooks 14th St, a large, loud
  street.
- **777 6th Avenue 22D** (40 / 17): a pretty good match, and a candidate for reading exposure
  and floor plan from photos. The building's website (equityapartments.com) lists
  exposures: mainly east with some north, so it overlooks 6th Avenue, which should be a **minus**
  (a wide, noisy street).

Good finds:

- **The Chelsea 12C** (44 / 37): looks pretty good. Courtyard-facing matches the photos and
  Street View. (Note from Website, not Ben: the label comes from StreetEasy's window-exposure
  field, east, plus the building's east side facing no street; its line C agrees.)
- **Ten23 04E** (22 / 35): looks good. From the photos it may front 10th Avenue or 23rd St; it
  appears to face north or east.
- **225 West 28th St 6G** (8 / 43): a good find. Some amenities are past his point of
  diminishing returns.
- **249 West 29th St 3E** (21 / 48): a good find.
- **30 Horatio St** (the one current listing, 2C; 17 / 67): pretty good, but the photos show radiator heat and an older,
  less good A/C unit.
- **52 Barrow St 2W** (50 / 75): a good find, but the windows and light look poor.

Feature ideas (location, mostly for Data improvements):

1. **Fronts a big street** as a minus: crosstown traffic streets (14th, 30th) and avenues (6th).
   (Website's note: ideally by the side the apartment faces, not only the building's address.)
2. **Transit and commute:** subway travel-time isochrones (traveltime.com or similar) to work and
   amenities, graded as a plus; a poor commute (a J train trip with transfers) as a minus.
3. **Nearby places:** Madison Square Garden, public housing complexes, homeless shelters and
   similar; parks for dog walking (he liked Carl Schurz Park from 401 E 88th St); hospitals,
   especially ambulance routes.

Website's notes, drawn from his comments rather than stated as ideas: photos could give exposure,
floor plan, heating (radiators), A/C and light; building websites can give exposures (777 6th
Avenue's does).

## Finding the best, not reproducing asks (from rounds 9 and 10, 2026-10-06)

The model prices what it can see. Wishes it can't see (quiet, garden view, floor-through) end up
in the residual and in the building and unit effects, so "below estimate" can mean "missing
something good". Ben asked (14:54 UTC) what would help. Items 1 and 2 went to Data improvements
and Modeling as proposals; items 3 to 5 are Website's, for when the hold lifts.

1. **Wishes as model inputs** (Data improvements, Modeling): quiet street (avenue vs side
   street from `street_kind`, traffic or bus routes), floor-through likelihood from building
   shape (PLUTO lot depth and frontage, units per floor, the line's window directions), garden
   view (rear facing plus a rear yard). Each wish then has a price.
2. **Wish-probability side model** (Modeling): per-unit probabilities ("likely, 70%") for
   floor-through, bedroom over a garden, quiet street, and unstated elevator or laundry, from
   the unit's other listings, its line, building shape and ad text. LLM extraction from ad text
   needs Ben's costed OK first and adds fields only, never overriding coded ones.
3. **Premiums as a quality signal** (Website): a large building or unit effect means the market
   pays for something unmeasured; for a "best" search, show it as evidence of quality, not only
   as cost.
4. **Rank by wish match × value** (Website): the probability of matching the wishes, weighted by
   the ask against the estimate given them; "4 of 6, these unknown".
5. **Unstated elevator or laundry** (Website): estimate it from the building (e.g. building
   class for an elevator) instead of filtering the listing out.

## Round 10, 2026-10-06 (best-1bed)

First round on the three-neighbourhood model (#318). Goal reached in about 12 clicks
(1 BR, elevator, in-unit laundry, then Faces = rear: 12 listings). The persona saw that Greenwich
Village has no current listings, which the page explains. It liked "What the model makes of it"
and the dollar breakdown. Report: `2026-10-06-r10/`.

1. **No ranking by wishes** (again; round 9 item 2): the bargain-first default sort puts a
   $9,995 studio, a 2BR and a walk-up on top.
2. **Floor-through, bedroom orientation and quiet unknowable** (again; round 9 item 1); rear
   facing is the only proxy.
3. **Size "not stated" yet priced:** 110 Horatio #120 shows "Size: not stated" while Size adds
   +$167 and the summary says "more space than usual". Not a bug: with the unit-size rule the
   model uses the median size from the unit's other listings (`features.py`, `unit_size`). The page
   should say "from its other listings" and show that size.
4. **Unreliable-estimate marker cryptic:** "Pareto k" jargon and a small `*`, with no advice; a
   wide range on one-listing units makes "Typical" nearly meaningless.
5. **Filters shrink to tiny sets:** in-unit laundry + elevator is nearly all Chelsea towers. They
   want a relaxed or "closest matches" mode. 1 BR also includes 1,241 ft² penthouses.

## Round 9, 2026-10-06 (best-1bed)

All goals reached on the Chelsea + West Village build (Greenwich Village not served yet). The
shortlist was 110 Horatio #120, The Chelsea #12C and 277 W 11th #6F. The value pick was 277 W
11th, 3rd percentile and $571 under the estimate, if six flights are acceptable. The persona
liked the plain "where the ask sits" sentence and the unit's own past asks. Report:
`2026-10-06-r9c/` (r9 and r9b stalled behind a full fit; see #313).

1. **Four of six wishes unanswerable:** floor-through, bedroom over a garden, and quiet street
   are unknown, and "rear or courtyard" isn't read as a garden. They want "likely" tags and a
   rear-bedroom filter. The bedroom labels and evidence in item 11 would cover part of this.
2. **Discount-first defaults:** the home page and the "available now" sort lead with the
   biggest discount, and "Below typical" reads as "good". The top rows are studios and a 2BR,
   not 1BRs with the wanted features. They asked for a wish-match sort ("4 of 6, which unknown").
3. **Estimate parts too dense** (again; round 7): large offsetting lines (building +$1,166, change
   over time +$1,028, this unit −$403) are hard to trust. They want a one-line summary on top.
4. **"Not stated" filtered out silently** (again; carried over): elevator = yes dropped 277 W
   11th, whose elevator isn't stated.
5. **No compare view**; also photos or the StreetEasy link on list rows, avenue-vs-side-street
   and transit distance, and grouping by building.

## Round 8, 2026-10-05 (best-1bed)

All three goals reached: a shortlist (110 Horatio #120, 277 W 11th #6F, 43 Charles #2), wishes
met or missed, and a verdict on each ask. It liked the listing page's candour about what the model
doesn't know, and the unit's history. Report: `/data1/apartments/tmp/playtests/2026-10-05-r8/`.

1. **No way to search for floor-through, garden or a quiet street** (major). "Faces" has no single
   "front and rear" choice. The broker's "Views: garden" shows only on the listing page, with no
   filter and no tag in the list. "Looks onto: a side street" is known but not shown in the list.
   This overlaps carried-over items 1 and 11.
2. **The default sort favours bargains** (major). Available now opens sorted by ask against
   estimate, lowest first. It wants a "match my wishes" or neutral sort. The first row is the
   150 Charles studio estimated at $12,155 (also round 5, for Modeling).
3. **The estimate breakdown is hard to read** (major). "Description", "How the price was
   recorded", "This unit" and "This building's change over time" carry hundreds of dollars with
   no plain explanation, and the bars have no common scale. It wants the parts grouped
   (apartment, building, market, unknown). This overlaps carried-over items 4 and 7.
4. **"Looks onto" and "Faces" read as conflicting** on one page ("a side street" against "both
   the street and the rear"). Explain them together, or merge them.
5. **Elevator "not stated" next to a walk-up tax class reads as ambiguous.** Say "walk-up (tax
   records)" in the row.
6. **Size is missing on most listings,** and there is no price per square foot.
7. **The "* less reliable estimate" footnote shows on every list,** even when no row has a `*`.
   Show it only when a row is marked.
8. **No side-by-side compare** of shortlisted or rated listings.

Checked, not bugs: "Elevator: Yes" did not keep listings that don't state an elevator (the line
says such filters leave them out). "3rd percentile, lower than 96%" is rounding on purpose (round 7).

## Carried over (rounds 5 and 7, 2026-10-05)

Ranked roughly by how many personas hit the finding and how badly.

1. **Shortlisting help for renters:** photos, a map on the listing page and street quietness
   (round 7, best-1bed). "Faces" is live (#290).
2. **Building Units table cut off:** it shows 13 of 42 rows in a scroll box with no count
   (round 5, renewer, major). Show the count and every row, or paginate.
3. **Estimate form reads as one step:** "Find the building" looks like the final submit
   (round 5, renewer, major). Say it is two steps.
4. **Dollar baseline for the estimate breakdown:** the parts are percentages with no starting
   dollar figure (round 7, landlord).
5. **Filters drop "not stated" listings silently:** the summary line notes it, but the filter
   gives no counts (round 7). Show how many are left out.
6. **"Building level" missing from the Glossary, and raw PLUTO class codes** (D6, C7) on
   building pages (round 5, renter, renewer, mobile). Add an entry and decode the codes in words.
7. **Estimate breakdown on phones and laptops:** on phones the intro mentions bars and whiskers
   that are hidden, and on laptops the bars are slivers (round 5, mobile, renter).
8. **Unit history chart has no legend,** and a `*` on a table estimate is unexplained
   (round 5, renter).
9. **Rent map:** it doesn't fit the chosen area, and its avenue labels overprint (round 5).
   The map is now sized to the window's height (#298).
10. **Journalist items** (round 5): "Compare with" defaults to 2010; the growth caveat shows
    only after choosing an area; Glossary entries for "typical rent" and "median building";
    90% vs 95% intervals; CSV for the table view.
11. **Facing in "Looks onto" and the listing summary:** the exposure labels (#290) aren't used
    there yet. Data improvements' proposal (2026-10-06): show the label, then "from the ad" or
    "from window directions" for own labels and "from other apartments in the same line" for
    line labels (they agree with an apartment's own evidence 89% of the time). Per-apartment
    evidence: `/data1/apartments/exposure/labels-evidence-20261006.parquet` (13,126 units, same
    labels as #290 plus an `evidence` column; rebuilt by
    `/data1/apartments/tmp/suspect/exposure-evidence/evidence.py`).
12. **Larger, later** (round 5): compare two buildings; a price column on the Buildings list;
    one sentence reconciling the map's typical rent with the listings' median estimate; a
    warning when a building link lands on a much pricier building.
13. **Windows facing a nearby wall, as a /best minus:** this waits for Data improvements'
    systematic footprint-based feature, and a pill only once the served model has the term. Ben
    (2026-10-07): /best pills only for model terms, never for hand-labelled single listings, so
    the one hand label (82-86 Washington Pl 2B, `outlook` = "wall", #382) is not shown; other facts
    are grey informational notes (see `docs/site.md`).
14. **A current price for every apartment Ben has seen** (Ben, 2026-10-07, for later; not
    started): estimate today's rent for every unit seen, from the latest listing's unit
    attributes and the building's latest attributes, evaluated at the current date. It needs
    the served model's predict path from Modeling. The nearest existing piece is the kit
    pricing of current listings (#377, #385), which already takes the latest unit and building
    attributes and evaluates them at today's date.
