# S16: blind spots in L1's misses (2026-11-14)

Duplexes came to light because I read ads, not because a residual plot showed them: renters
price a second level, and L1 has no column for it. In this screen I look for more qualities of
that kind. I take L1's largest misses on its held-out ads, in both directions, with random
held-out ads as controls, and have Sonnet readers name a priced quality missing from the coded
fields, without showing them the ask or the group. When a cause turns up much more often among
the misses than among the controls, I count it as a candidate blind spot.

The screen runs against L1's saved fit, the pool `drift-building-phase-b0-latest-9a7830fb-l1`,
and its dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, on the latest split.
Nothing is fit, nothing goes to Modal, and no photo or OxyLabs page is fetched. The scripts are
in `docs/notes/blind-spots-2026-11-14/` and write to `/data1/apartments/tmp/blind-spots-2026-11-14/`.

## Predictions, written before the draw and before any ad was read

When I wrote these I had computed nothing on L1's held-out ads for this screen. I knew from
earlier notes that L1's noise is a Student-t with `nu` 1.69, so its tails are heavy and the
extreme misses are few standard scales out; that `furnished` and `short_term` are false on
every row of L1's dataset, so L1 can't tell a furnished ad from an empty one; that the
rewritten income flag adds 122 held-out ads to the old one's, at 0.107 under L1's median
(S15); that the rewritten shared flag marks 33 held-out ads (the text-flag screen); and that
duplex and text-penthouse ads scatter about 35% wider than others around L1's median (S7, S14).

The draw takes 150 overpriced and 150 underpriced misses and 100 controls. "Overpriced" means
the ad asks far above L1's median, and "underpriced" far below it.

1. **Data errors lead both miss groups.** The readers put 30% to 50% of the underpriced misses
   and 20% to 40% of the overpriced misses down to a data error in beds, baths, unit or price,
   against at most 8% of the controls (70%). Over all 300 misses the share is 25% to 45%, with
   my point guess at 33% (65%).
2. **Overpriced misses.**
   - Furnished or short-term is the most common unseen quality, in 10% to 25% of them, against
     at most 3% of the controls (60%).
   - A unit far larger than its count suggests, such as a whole house or a loft coded with few
     rooms, comes to 5% to 15% (55%).
   - Penthouse or top floor, private outdoor space, duplex and views each come to 2% to 8%
     (55%), and 10% to 25% taken together (55%).
3. **Underpriced misses.**
   - Shared or room rentals come to 8% to 20% (60%), and income-restricted or other program
     ads to 8% to 20% (60%).
   - With data errors, those two make up over half of the underpriced misses (60%).
   - Garden or basement units come to 2% to 8% (50%), and a unit needing work under 5% (60%).
4. **Controls.** "None apparent" is the most common answer among the controls, at 35% to 65%
   (65%). Renovation state is the most common named quality there, at 8% to 20% (55%), since
   readers will name a gut renovation whenever an ad boasts one.
5. **Direction.** For each of the three most common causes in a miss group, the readers' stated
   direction agrees with the group's sign in at least 70% of its reads (65%).
6. **The bar of step 4.** Between 5 and 9 causes pass it (65%), with my guess at 7: data
   error, furnished or short-term, shared or room rental, income-restricted, a unit far larger
   or smaller than its count, and one or two of penthouse, private outdoor space, duplex and a
   luxury building. At most 2 of the passing causes are new to the project's screens (60%).
7. **The cap.** Three ads a building per group displaces 15 to 60 ads from the two miss groups
   together, mostly from a few buildings of income-restricted or room-rental ads (60%), and
   none or almost none from the controls (90%).
8. **Missing text.** Ads with no description over 80 characters make up 5% to 15% of the
   misses against 2% to 6% of the controls (55%).
9. **Patterns.** Each flagged cause with a first text pattern reaches a precision of at least
   0.7 on its 30 read matches (55%).
