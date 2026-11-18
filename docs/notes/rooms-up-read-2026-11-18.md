# Broker read of the Deals table from `range-m` (2026-11-18)

Deals has read the layout-range model since 11:54 AM ET on Nov 18
(`docs/notes/low-outliers-2026-11-18.md`). That note left a question open. The `rooms_up`
caution hides 328 market ads coding more bedrooms or baths than the apartment's previous
ad, and the new model already lowers its estimate for an ad above the apartment's earlier
low count. If the model now prices those ads soundly, the caution hides real deals, and
the bedroom half of it could go. The same fit moved ads with fewer rooms than an earlier
ad up the table (20 of the first 200 uncautioned ads, up from 12), and nobody had read
them.

## The read

`rooms-up-read-2026-11-18/build.py` drew 125 market ads from the live table, lowest
`below_share` first within each set, at most two ads a building:

| set | ads | drawn from | `below_share` |
|---|---|---|---|
| `up_beds` | 30 | hidden by `rooms_up` alone, more bedrooms than the previous ad | 0.010 to 0.217 |
| `up_baths` | 25 | hidden by `rooms_up` alone, more baths only | 0.010 to 0.250 |
| `fewer` | 30 | uncautioned, fewer bedrooms or baths than an earlier ad | 0.004 to 0.085 |
| `plain` | 25 | uncautioned, no range mark, sampled from the first 200 | 0.005 to 0.060 |
| `ctl` | 15 | uncautioned, mid-table | 0.25 to 0.75 |

Six Sonnet readers each took a shuffled group of about 21 ads with the brief in
`READER.md` (the brief of the earlier read). A reader had the ad's text, its fields and
the apartment's earlier ads. A reader did not have the set, the model's estimate or the
ad's place in the table. `tally.py` joined the answers to the key.

## Counts

Each reader said whether the ad reads as a sound deal (`yes`), as low for a reason
(`no`), or as an ordinary ask.

| | `up_beds` | `up_baths` | `fewer` | `plain` | `ctl` |
|---|---|---|---|---|---|
| yes | 1 | 0 | 5 | 3 | 0 |
| no | 20 | 10 | 14 | 8 | 4 |
| ordinary | 9 | 15 | 11 | 14 | 11 |

Reasons the readers gave most often, as ads per set:

| reason | `up_beds` | `up_baths` | `fewer` | `plain` | `ctl` |
|---|---|---|---|---|---|
| the earlier ads describe another layout | 15 | 5 | 13 | 0 | 1 |
| bedroom count doubtful | 18 | 3 | 1 | 1 | 1 |
| ask cut soon after posting | 3 | 4 | 4 | 8 | 1 |
| concession gone or changed | 4 | 6 | 4 | 3 | 1 |
| basement or garden level | 3 | 4 | 0 | 4 | 1 |

## Reading of the counts

**The caution stays as it is.** Of the 55 hidden ads read, readers called 1 a sound deal.

- In `up_beds`, 18 of 30 carry an extra bedroom the text does not support: a flex wall
  that is not up, a loft reached by ladder, a home office, a basement room, a living room
  described as convertible. The model's lower estimate for these ads is still an estimate
  for the coded count, and the ask is a fair price for the real count.
- In `up_baths`, 15 of 25 read as ordinary asks and 10 as low for a reason. None reads as
  a deal, so dropping the bath half would add ads to the list with nothing to offer.

**The fewer-rooms ads need no caution.** Readers called 5 of 30 sound deals, against 3 of
25 among the plain ads beside them in the table. The 14 marked `no` are mostly ads where
the reader compared the ask with an earlier, larger layout (13 of 30 have that reason) and
concluded that the lower ask follows from the lost room. That comparison is the reader's
only yardstick, and the model's estimate is already for the smaller count. The rate of
sound deals is the number to hold on to, and it is no lower than for plain ads.

**Sound deals are a minority among the lowest ads in every set.** Among the 55
uncautioned low ads read, 8 read as sound (15%), 22 as low for a reason and
25 as ordinary. The reasons in the plain set are a cut soon after posting (8 of 25) and a
basement or garden level (4 of 25). Wordings for basement and garden level failed the
shuffled-label check in the earlier note, and a cut is the ad's own rent, which a model
term cannot use.

## A check on asks shown net of a free month

Two plain ads had an ask equal to 11/12 of the same ad's first ask, with the text
pointing to a "pricing structure" and no free month coded. That is a net price shown as
the rent. `rooms-up-read-2026-11-18/net.py` coded the trait from the ads table: the page
price over the first ask within 0.0004 of 11/12, 12/13, 13/14 or 10/12.

| | market ads (`range-m`) | backtest ads (`range-j`) |
|---|---|---|
| ads at the four fractions | 52 | 131 |
| expected from bands of the same width beside each fraction | about 15 | about 55 |
| in the first 200 uncautioned | 5 | 2 |
| share in the lowest tenth | 13.5% | 19.8% |
| share in the lowest tenth, other cut ads | 9.3% | 12.9% |

The trait is real and small. About 35 market ads beyond chance carry it, 5 of them in the
first 200, and close to a third of the matches at 11/12, 12/13 and 13/14 are ordinary cuts
of that size. Text cautions were kept when nearly all matches were right, and this one is
below that bar, so no caution was added. The 8 market ads at 10/12 are nearly all beyond
chance (0.2 expected), which is too few to act on alone.

## Outcome

No code change and no fit. The open question from the earlier note is closed: `rooms_up`
keeps both halves. Cost: six Sonnet reads, no Modal spend.
