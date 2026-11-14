# S17: studios coded on units of 5 or more rooms (2026-11-14)

S16 split L1's studio-coded rows by their coded room count after its reads, and found that
the 70 held-out ads at 5 to 20 rooms outside its draw ask +0.085 ± 0.027 over L1's median,
with half inside the 80% interval (`blind-spots-2026-11-14.md`, follow-up 3). There are 905
such rows in L1's dataset. In this check I read 30 of them against the evidence a correction
needs, to find out whether the coded 0 is wrong and what could back a fix.

The check runs on L1's dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, its
saved fit `drift-building-phase-b0-latest-9a7830fb-l1` and the latest split. Nothing is fit
and nothing goes to Modal. The coordinator barred floor plan fetches for this screen, so I
make no OxyLabs request of any kind and use plans only if one is already stored on disk.

## Predictions, written before any of the 905 rows was read

When I wrote these I had looked at no row of the 905 and drawn nothing. I knew S16's figures
by room count (489 rows at 5 rooms, 214 at 6, 53 at 7, 149 at 8 to 20; held-out ads outside
its draw at +0.086, +0.138, a single ad and -0.021); its 8 precision reads at 5 rooms (1
one-bedroom, 3 studios, 4 unclear); the sprint's finding that under 1% of ads typed as studios
carry more than 3 rooms; and L1's bedroom steps (+0.22 log for the first bedroom, +0.19 for
the second) beside a near-zero coefficient on `ad:extra_rooms`. About 167 listings have a
floor plan stored under `/data1/apartments/archive/floor-plans/`.

The sample takes 30 rows, stratified by room count (5, 6, 7, 8 or more) and by held-out
against training, so the shares below are weighted back to the 905 by stratum.

1. **Shares.** I expect 30% to 60% of the 905 to have 1 bedroom or more, with my point guess
   at 45% (60%). True studios, lofts with no walled bedroom included, come to 20% to 45%,
   guess 30% (55%). The rows I can't settle come to 15% to 35%, guess 25% (55%). Without a
   plan fetch, the unsettled share could run above that range.
2. **By room count.** The share with 1 bedroom or more is higher at 6 and 7 rooms than at 5,
   by at least 15 points (50%), and lowest at 8 or more rooms, where I expect whole buildings,
   townhouses and typed nonsense (60%).
3. **Evidence.**
   - The unit's other ads with a typed count of 1 or more, near in time and with the same
     room count, settle at least half of the settled rows (65%).
   - A stated size comes second. It argues for a bedroom only with other backing, since lofts
     and large studios run past 700 sq ft.
   - Units of the same line in the building settle a few rows where the unit page has no
     other ad.
   - At most 1 of the 30 rows has a plan stored on disk (80%).
4. **Reasons for the high room count.**
   - Among rows with a bedroom, the lister typed the room count and left the bedroom field at
     its default 0, or the feed dropped the count. This accounts for most of them (60%).
   - Among true studios, the room count includes alcoves, dressing rooms or a loft's zones,
     or belongs to the building or a whole house at 8 rooms or more.
   - Combined listings, two apartments under one ad, come to at most 2 of the 30 (65%).
5. **The gap after a fix.** Correcting the bedrooms of the rows with 1 bedroom or more would
   raise L1's median on those ads by about 0.2 log or more, but L1's unit level already absorbs
   part of the miscoding where the unit's earlier ads carry the same 0. So I expect the mean
   gap of the 70 held-out ads to move from +0.085 to between -0.03 and +0.04, guess +0.01, a
   shrink of at least half (60%). The held-out ads whose unit has an earlier ad coded 1 or more
   carry most of the gap: their mean gap is at least +0.15 against under +0.04 for the rest
   (55%).
6. **Rules.** A rule needing the unit's history (other ads of the unit page coded 1 or more,
   near in time, with a room count within 1 of the row's) marks 15% to 40% of the 905 rows,
   with every sample row it marks settled at 1 bedroom or more (55%). No room count threshold
   alone gives a precision of 0.8 or more on the sample (60%).
