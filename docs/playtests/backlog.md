# Website backlog (on hold)

Ben put website features on hold on 2026-10-05 (18:22 UTC). Playtests go on with the
`best-1bed` persona only, one per round, and their findings are logged here, unbuilt.
Fixes for things that are broken or wrong on the live site still ship.

Each round adds a section at the top, ranked by how much the finding gets in the way of
finding the best one-bedroom. Reports are in `/data1/apartments/tmp/playtests/<round>/`.

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
    there yet. Wording to be agreed with Data improvements.
12. **Larger, later** (round 5): compare two buildings; a price column on the Buildings list;
    one sentence reconciling the map's typical rent with the listings' median estimate; a
    warning when a building link lands on a much pricier building.
