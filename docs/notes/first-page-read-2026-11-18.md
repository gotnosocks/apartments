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
walkup, a lost extra, net ask, changed free months) appears on 39 of the 100 `first` ads
and on 9 of the 25 controls, 39% against 36%. The first page carries those traits at the
table's ordinary rate, so none of them is a feature the model lacks by this read. A
broker would say of the first page that its landlords have cut their asks: 22 ads against
1, and 8 of the 46 "reason" verdicts rest on a cut alone, which is what a deal is.

Two things did set the first page apart.

**The ask is net of free months on 2 ads.** One ad's 3,618 is 4,100 less 2 months over 17;
another's 6,783 is 7,400 times 11/12. Both carry coded free months, so the model may have
taken the free months off a second time. The data backlog gets an item for a count of
market ads whose page price equals an earlier price of the same ad net of its coded free
months.

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
feed ads is about 140 elpd on 45,448 ads. Feed asks are a little tighter around the
model's median than the model allows. Narrowing them by a tenth would move the share of
feed ads below 10% from 9.2% to 11.2% and their 80% coverage from 82.5% to 78.8%, past
the target on the other side, so the best factor lies between 0.9 and 1.

## Verdict

- The first page holds no trait of the apartment at a rate above the middle of the table.
  No new term comes from this read.
- A width by source is real and small. It would bring a few more feed ads onto the first
  pages and change no ad's caution. At about $4 for a backtest and a market fit it waits
  behind items with more effect on the table; it is recorded in the backlog.
- Stale owner ads are a caution candidate: an `OWNER` ad open for many months that places
  low. The count in the live table comes first.
- The net-ask count goes to the data backlog.
