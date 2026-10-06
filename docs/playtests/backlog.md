# Website backlog (on hold)

Ben put website features on hold on 2026-10-05 (18:22 UTC). Playtests go on with the
`best-1bed` persona only, one per round, and their findings are logged here, unbuilt.
Fixes for things that are broken or wrong on the live site still ship.

Each round adds a section at the top, ranked by how much the finding gets in the way of
finding the best one-bedroom. Reports are in `/data1/apartments/tmp/playtests/<round>/`.

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
