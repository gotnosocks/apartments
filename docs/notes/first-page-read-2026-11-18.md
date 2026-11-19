# Broker read of the first page of Deals after the refresh (2026-11-18)

Deals has read the market of Nov 18 from `range-m2` since 9:00 PM ET
(`docs/notes/market-refresh-2026-11-18.md`). Ben skipped the held-out fit of this model, so
there are no held-out misses of it to read. This note reads the table a renter gets
instead: the first 100 ads with no caution, against ads from the middle of the table.

## The read

`first-page-read-2026-11-18/build.py` drew 125 ads from the live table, one ad an
apartment and at most two a building:

| set | ads | drawn from | `below_share` |
|---|---|---|---|
| `first` | 100 | the first uncautioned ads (places 1 to 106) | 0.001 to 0.029 |
| `ctl` | 25 | uncautioned, mid-table, seed 20261119 | 0.286 to 0.749 |

Six Sonnet readers each took a shuffled group of 20 or 21 ads with the brief in
`READER.md`, the brief of the two earlier reads. A reader had the ad's text, its fields
and the apartment's earlier ads, and did not have the set, the model's estimate or the
ad's place. `tally.py` joined the answers to the key.

## Counts

| verdict | `first` (100) | `ctl` (25) |
|---|---|---|
| a sound apartment asking less with no reason found | 11 | 0 |
| ordinary | 43 | 20 |
| a reason explains a lower ask | 46 | 5 |

Of the 53 `first` ads with earlier ads of the apartment, 30 ask less than that history
did; none of the 20 such controls does.

| reason | `first` | `ctl` |
|---|---|---|
| ask cut after sitting, or a relist below a failed ask | 22 | 1 |
| basement, garden or ground floor | 11 | 2 |
| bedroom count doubtful | 9 | 2 |
| free months differ from the earlier ad | 7 | 3 |
| earlier ads describe another layout | 8 | 0 |
| small | 5 | 2 |
| owner-direct, plainly written | 7 | 0 |
| restrictions | 4 | 2 |
| fourth floor or higher walkup | 3 | 1 |
| earlier ad sold a renovation or extra this one lacks | 3 | 0 |
| earlier ads furnished or short-term | 2 | 0 |
| ask shown is net of free months | 2 | 0 |

A reason about the apartment itself (basement, doubtful bedrooms, another layout, small,
walkup, a lost extra, net ask, changed free months, an income program, a shared house,
an earlier furnished or short-term ad) appears on 39 of the 100 `first` ads
and on 9 of the 25 controls, 39% against 36%. The first page carries those traits at the
table's ordinary rate, so none of them is a feature the model lacks by this read. A
broker would say of the first page that its landlords have cut their asks: 22 ads against
1, and 8 of the 46 "reason" verdicts rest on a cut alone, which is what a deal is.

Two things did set the first page apart.

**The ask is net of free months on 2 ads.** One ad's 3,618 is 4,100 less 2 months over 17;
another's 6,783 is 7,400 times 11/12. Neither has coded free months in the table, so
Deals compares a net ask with the model's gross rent. A count over the live table: of the
5,148 ads with no coded free months, 39 have a page price that is no multiple of 5 below a
round first ask, and 20 of those equal the first ask net of some free months over a 12 to
24 month lease. That matcher is loose (it also fits 244 of 769 ordinary cuts to a round
price), so about 10 ads are real cases, among them 3 of the first 100 uncautioned ads
(two at 555 West 45th Street, one at 308 Eldert Street). A caution for these ads is the
next item.

**The ad's source.** The packets carry StreetEasy's source type. Among the controls 12 of
25 ads come from a landlord's feed (`FEED`); among the first 100, 3 do. Five of the first
100 are owner ads (`OWNER`) and no control is. The `first` ads also have fewer photos
(median 10.5 against 15).

## The source on the backtest

`source.py` reads the source type and photo count for the 8,564 open uncautioned ads of
the backtest `range-j`:

| source | ads | in the lowest tenth of places | in the highest tenth | lowest tenth: median days on the market |
|---|---|---|---|---|
| FEED | 1,847 (21.6%) | 2.4% | 20.4% | 63 |
| PARTNER | 6,566 (76.7%) | 6.9% | 17.7% | 25 |
| OWNER | 151 (1.8%) | 13.9% | 13.2% | 710 |

Feed ads seldom place low, and those that do stay open about as long as other feed ads
(63 days against 73), with no sign of a quick close. The 21 owner
ads in the lowest tenth are mostly stale: a median of 710 days open. Photo count shows
little: 9.6% of ads with at most 3 photos place in the lowest tenth against 4.4% to 6.3%
for the other groups.

## A width by source, at no cost

`calib_source.py` repeats the method of `docs/notes/duplex-scale-2026-11-18/calib.py` on
the 189,440 held-out ads of the base model (run b9): a Student-t approximation of each
ad's predictive distribution (4 degrees of freedom matched the stored log density),
widened m times for the ads of one source, with m picked on one half of the buildings and
scored on the other.

| group | ads | 80% interval covers | below 1% | m picked | cross-fit elpd gain (SE) |
|---|---|---|---|---|---|
| FEED | 45,448 | 82.5% | 0.45% | 0.9 | +256.6 (43.7) |
| PARTNER | 140,648 | 80.3% | 0.75% | 0.9 | +59.8 (60.4) |
| OWNER | 3,344 | 79.9% | 1.14% | 1.0 | 0.0 |
| control, random | 10,000 | 81.1% | 0.78% | 0.9 | +25.3 (11.5) |

The random control gains 25.3 on 10,000 ads from the same narrowing, about 115 at the feed
group's size, so the approximation itself favours 0.9 a little and the gain particular to
feed ads is about 140 elpd on 45,448 ads. The control's gain has an SE of 11.5, so that
figure is known only to within about 50 either way. Feed asks are a little tighter around the
model's median than the model allows. Narrowing them by a tenth would move the share of
feed ads below 10% from 9.2% to 11.2% and their 80% coverage from 82.5% to 78.8%, past
the target on the other side. By coverage the best factor lies between 0.9 and 1; the
grid of elpd says only that 0.9 beats 1.0.

## Verdict

- The first page holds no trait of the apartment at a rate above the middle of the table.
  No new term comes from this read.
- A width by source is real and small. It would bring a few more feed ads onto the first
  pages and change no ad's caution. At about $4 for a backtest and a market fit it waits
  behind items with more effect on the table; it is recorded in the backlog.
- Stale owner ads need no caution. The live table has 87 uncautioned owner ads with a
  median of 9 days open and none open more than 90 days; the backtest's old owner ads
  are not a feature of a fresh snapshot.
- About 10 live ads show a net ask with no coded free months, 3 of them on the first
  page. A caution for them comes next.

## Two follow-ups, at no cost (later on Nov 18)

**The doubtful bedroom counts.** Readers doubted the coded count on 9 `first` ads and 2
controls, and none of the 11 has the `beds` caution. That caution reads the coded counts
of the apartment's ads, and these ads' doubt is in their text, which the model's
`bedtext` columns read. Of the 11, 4 carry `bed_flex_at`, so the model already prices the
made room. The other 7:

- 4 have text with no stated size to read ("plenty of flexibility to create separate
  living, sleeping, and work-from-home areas", a railroad layout, a small floor area);
- 1 states sizes on both sides of the coded count (a "One bedroom Oasis" headline over a
  "Beautiful Studio" body), which the reader leaves blank by design;
- 1 says "5 Bedrooms (flexible 5th bedroom)", a flex wording the reader lacks;
- 1 opens "Gorgeous 1 Bed + Home office" on a coded two-bedroom and then lists the
  building's sizes ("studio, one-, two-, and three-bedroom residences"). The reader drops
  every stated size when a text offers sizes of other units.

A reader that trusted a size stated in the first line over a later list would mark 6 more
of the 6,565 live ads as stating fewer bedrooms (72 are marked now), 3 of them
uncautioned and 1 in the first 100. That is too few for a fit. The change belongs in the
next rewrite of the reader, with "flexible Nth bedroom".

**Earlier ads of another layout.** Readers gave this reason on 8 `first` ads and no
control. `range_share.py` computes the layout-range model's marks for the live table: 7
of the 8 carry `ad:beds_below_high` or `ad:baths_below_high`, so the model knows the
apartment's earlier ads coded more rooms and applies its step. Among the first 100
uncautioned ads 7% carry `ad:beds_below_high` and 3% `ad:baths_below_high`, against 4.3%
and 1.8% of all 5,471, a difference of about three ads. The controls' zero is 25 ads at
an expected one. No term is missing here.
