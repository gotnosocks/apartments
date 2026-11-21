# A broker read of the top 60 Deals (2026-11-21)

This note reads the first 60 ads of the Deals page's default view as a broker would, and
counts the traits they share against 60 ads from the middle of the same view. It is a read
of the product. The readers' blocks held the asks, so no rule or term is chosen from it. A
trait found here goes forward only once it is coded without rent and tested on the held-out
history, as `docs/expert-reads.md` sets out.

## What was read

The page was the live publish of 2026-11-21 04:31Z, from the run
`drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3` (scoring day 2026-11-20),
with its backtest `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`.

- **Top.** The default view is `deals.choose` over the published rows. It keeps unit and
  building bases, drops suspect, cautioned, peer-cautioned and ruled-out ads, and sorts by
  the cautious saving, `(lo80 - ask) / lo80`. It holds 4,067 of 6,502 ads. The top group is
  places 1 to 60.
- **Middle.** Places 2004 to 2063 of the same view form the base-rate group.
- **Blocks.** Each block holds the coded fields from the ads file and the whole description
  from the ad's last stored API record. Top blocks also carry the ask, the model's median and
  the 90% interval (`drift_score.score_run`, exact). The medians match the page to the dollar.
- **Broker reads.** Four Sonnet readers took 15 top blocks each (`READER_TOP.md`). Each
  answered (a) whether the ad is one apartment for a regular renter at that ask, (b) the
  problem if it is not, and (c) for the rest, whether a broker would call it a real deal,
  with reason tags.
- **Blind codes.** Eight Sonnet coders took all 120 picked ads in batches of 15, shuffled
  with seed 20261121 (`CODER.md`). Their blocks had no ask, no fees, no model output and no
  group, and every dollar amount was masked. They coded 14 traits from the text.
- **Field traits.** These come from the ads file and the record: coded free months, the
  deposit mark below, availability more than 30 days before the scoring day, fewer than 8
  photos, the elevator field and the source type.

All 60 top asks fall below the model's 5% point except one. Their median ask is 0.84 of the
model's median (range 0.69 to 0.91).

## (a) and (b): one apartment at the ask

| answer | ads |
|---|---|
| one apartment at the ask | 39 |
| net-effective ask | 18 |
| wrong bedroom count | 2 |
| short lease | 1 |

The two bedroom calls quote the ads directly. T01 says "The fifth bedroom remains flexible,
the dividing wall is not yet installed". T25 is a "Spacious True Alcove Studio Convertible to
2-Bedroom" coded as two bedrooms. T01's flex wording is already in the backlog for the bedroom
text reader. The short lease is T40: "$17,500 for a 6-month lease or $19,995 with 1 month
free and 1 month OP".

### The 18 net-effective calls

15 of the 18 have coded free months. The model's target is the ask net of free months, and
months free is one of its columns, so these ads compare a net ask with a net estimate. The
readers called them net because the page price is gross. Even so, the gross page price lies
below the model's median for 14 of the 15 (median ratio 0.93). These 15 are priced net
against a net target, with `ad:months_free` in the design, so they are no Deals defect; the
readers' call is about the page's wording. Coded free months are also only a little more
common in the top than in the middle (15 against 11).

The other 3 have no coded free months and a flat security deposit above the page price.
New York caps a deposit at one month's rent, so the deposit is the lease rent:

| ad | building | page price | deposit | deposit / price | deposit / model median |
|---|---|---|---|---|---|
| T50 | 600 Myrtle Avenue | 3,680 | 4,171 | 1.13 | 0.96 |
| T52 | 733 Lincoln | 5,300 | 6,350 | 1.20 | 1.08 |
| T59 | 733 Lincoln | 4,700 | 5,640 | 1.20 | 1.09 |

At 733 Lincoln the ratio is exactly 1.2, two months free on a 12-month lease, and the first
ask equals the page price, so the existing `net_ask` caution cannot mark it. At the deposit,
two of the three are above the model's median.

The first-pass top blocks showed the fee amounts without their labels. The readers inferred
the net rent from the "fee field", which was in fact the deposit. The blocks were rebuilt
with labelled fees, a deposit line and the source type before the blind coding, and the
deposit check below reads the label directly.

## (c): the 39 that are one apartment

| real deal | ads |
|---|---|
| yes | 4 |
| unclear | 23 |
| no | 12 |

The four real deals are a condo owner's high-floor corner two-bedroom at The Avery (T04), a
large SoHo one-bedroom on a low floor at a busy corner (T07), an East Harlem three-bedroom
walkup on 3rd Avenue (T44), and a Park Slope three-bedroom second-floor walkup on 4th Avenue
(T49). T44's reader adds that its "virtual doorman" code misleads.

Reason tags over the 39 (an ad can carry several):

| tag | ads |
|---|---|
| low floor | 15 |
| owner or small landlord | 15 |
| old or plain building | 15 |
| walkup | 14 |
| small rooms | 8 |
| noisy or busy street | 6 |
| far from the subway | 6 |
| no fee, low marketing | 5 |
| odd layout | 5 |
| high walkup (4th floor or up) | 5 |
| dated finishes | 5 |
| poor spot within the area | 5 |
| garden or basement level | 4 |
| no laundry | 3 |
| stale price cut | 3 |

The readers' tags come from the top alone. The blind codes give their base rates.

## Blind codes against the middle

Counts of 60 in each group. The difference is in shares, with its standard error.

| trait | from | top | middle | difference | SE | z |
|---|---|---|---|---|---|---|
| walkup | text | 7 | 1 | +0.10 | 0.045 | 2.2 |
| condo or co-op owner rental | text | 7 | 1 | +0.10 | 0.045 | 2.2 |
| low floor or garden | text | 18 | 11 | +0.12 | 0.077 | 1.5 |
| railroad or odd layout | text | 2 | 0 | +0.03 | 0.023 | 1.4 |
| busy street or elevated train | text | 22 | 16 | +0.10 | 0.084 | 1.2 |
| owner or small landlord | text | 6 | 3 | +0.05 | 0.048 | 1.0 |
| high walkup | text | 1 | 0 | +0.02 | 0.017 | 1.0 |
| small for its rooms | text | 2 | 1 | +0.02 | 0.028 | 0.6 |
| new development | text | 8 | 7 | +0.02 | 0.060 | 0.3 |
| renovated | text | 18 | 19 | -0.02 | 0.084 | -0.2 |
| flex or unbuilt bedroom | text | 4 | 5 | -0.02 | 0.048 | -0.3 |
| thin ad | text | 5 | 8 | -0.05 | 0.057 | -0.9 |
| utilities beyond heat | text | 1 | 5 | -0.07 | 0.039 | -1.7 |
| doorman | text | 19 | 38 | -0.32 | 0.086 | -3.7 |
| deposit fits a net rent | field | 5 | 1 | +0.07 | 0.039 | 1.7 |
| coded free months | field | 15 | 11 | +0.07 | 0.075 | 0.9 |
| available over 30 days before scoring | field | 16 | 12 | +0.07 | 0.077 | 0.9 |
| fewer than 8 photos | field | 23 | 20 | +0.05 | 0.087 | 0.6 |
| owner source | field | 1 | 0 | +0.02 | 0.017 | 1.0 |
| elevator field true | field | 32 | 44 | -0.20 | 0.086 | -2.3 |
| feed source | field | 5 | 20 | -0.25 | 0.071 | -3.5 |

The doorman field tells the same story as the text. The top holds 16 ads coded "virtual"
doorman against 7 in the middle, and 26 with no doorman against 17. Full-time or unspecified
doormen number 17 against 35. Six of the seven text walkups have the elevator field false.

Among the 39 one-apartment ads, the walkup code splits 4, 1 and 2 across the readers' "no",
"unclear" and "yes" answers on a real deal. Low floor splits 4, 6 and 3. Neither trait marks
the false deals apart from the real ones.

Most of these traits are already model terms: floor curves by elevator and walk-up, the
building's doorman columns (full, part and virtual), and MapPLUTO's condo and co-op columns.
By `docs/expert-reads.md`, a trait the model has stays a candidate only if the term is coded
wrong or too coarse. The read suggests two such cases. A virtual doorman may be priced too close to
a staffed one in the building columns. A condo or co-op unit an owner rents out is a
different product from a rental building's unit, and the lot class does not tell them apart.
The feed share repeats the first-page read of 2026-11-18 (3 of 100 against 12 of 25), whose
width-by-source item is already in the backlog.

## The deposit check over the whole table

`deposit.py` reads the record of every one of the 6,502 published ads from the pipeline
records file the publish reads for texts (`records-941f4a6588cbd8cc`, the build of the run's
ads file), choosing the ACTIVE record fetched last as `descriptions.record_descriptions`
does. A first count on the API export's last record gave 388, 319 and 94 for the rows below;
the places in the default view came out the same.

| step | ads |
|---|---|
| flat security deposit | 5,128 |
| deposit above page price by 2% or more | 372 |
| of those, with coded free months | 67 |
| uncoded, deposit equals the first ask (a cut) | 211 |
| uncoded, deposit fits a net rent | 88 |
| uncoded, other | 6 |
| uncoded and over, already cautioned | 82 of 305 |

`deposit_kinds.py` calls a deposit a net fit when deposit × (L - m) / L matches the page
price within the larger of $2 and 0.2%, for m from 0.5 to 3 free months and a lease L of 12
to 24 months. It reads no model output. By place in the default view:

| places | net fit | cut |
|---|---|---|
| 1 to 60 | 5 (8.3%) | 2 |
| 1 to 300 | 12 (4.0%) | 14 |
| 301 to 2000 | 13 (0.8%) | 54 |
| 2001 to 4067 | 15 (0.7%) | 70 |

The net fits gather near the top of the page, as a missed concession would. They also gather
by building: The Lightwell Dumbo 6, 733 Lincoln 6, The Baltic Canal 3. Two of the five in the
top 60 (T12 at Gilsey House, ratio 1.04, and T29 at 34 Eighth Avenue, 1.07) were read as one
apartment. A ratio that small fits half a month on a 13-month lease and also fits a stale
deposit from an intermediate price, so the mark is strongest at ratios near 1.1 and above.
The deposit field comes from API records, which start about 2026-10, so a long held-out
history test of this mark may not be possible. The backtest day can be checked where records
cover it.

## Caveats

- The broker readers' blocks held the ask, the median and the interval. Their tags are a reading of
  the top and cannot stand as evidence for a term.
- The middle group is the middle of the uncautioned view. It is no random draw of held-out
  ads, and the groups are 60 each. Every z above is rough.
- The first-pass top blocks carried unlabelled fees (above). The three uncoded net calls were
  checked against the labelled deposit afterwards.
- The 15 coded concessions compare net with net, so the readers' "net-effective" answer on
  them is a call about the page's wording.

## Recommendations

### Deals cautions computable at publish time

1. **`deposit_net`.** Mark an ad when its record has a flat security deposit at least 2%
   above the page price, no coded free months, a deposit different from the first ask, and a
   deposit that fits a net rent as above. The publish already reads the records file for the
   ad's text, so the deposit comes from the same record. On the live table it would mark 88
   ads, 5 in the top 60 and 12 in the top 300. A first form could require a ratio of 1.05 or
   more, to leave out the half-month fits.
2. **`short_lease`.** Mark ads whose text prices a lease under 12 months ("6-month lease",
   "short term" with a price). T40 is the one case in the top 60.
3. **Bedroom wording.** Extend `beds` to text that says "convertible", "alcove studio" or "wall
   not yet installed" on an ad coded one bedroom or more. T01 and T25 are the cases here.

### Data rules and ledger drafts

1. No data rule comes from the deposit mark. With coded free months the target stays net
   (`ledger_rows.sql` with `concessions.sql`, and `latest_ask` in `b0data.py`), so taking a
   gross rent from the deposit would break it. The only form that keeps the target net is a
   free-months and lease-term fill for ads of the 733 Lincoln and Lightwell Dumbo kind. The
   mark compares the deposit with the page price, so under `docs/leak-free-scoring.md` it may
   screen or carry a Deals caution and may not become a data rule, as with the overlap mark
   of the any-unit read of 2026-11-21. It goes forward as the caution above.
2. T25 at its alcove studio and T01's unbuilt fifth bedroom go to the bedroom ledger as drafts.

### Traits to test as terms on the held-out history

Each must be coded without rent and checked on the unread half of the held-out buildings,
against a null from shuffled labels, before any fit note.

1. **Walkup by area.** The walkup and elevator excess (7 against 1 by text, 28 against 16
   without a true elevator field) with the existing floor curves suggests the walkup discount
   varies by area. Test an interaction of the elevator field with zone.
2. **Virtual doorman.** Test whether the held-out gap of ads in buildings coded virtual
   differs from full-time ones once the building columns are in.
3. **Condo or co-op owner rental.** Code it from text ("owner", "condo", "board approval",
   "co-op") on condo and co-op lots, and test it on history.
4. **Low floor or garden level.** Code garden, basement and ground-floor wording against the
   floor field, and test it where the floor curve is flat.
5. **Feed source.** Already in the backlog as a width by source. This read adds a second
   sample with the same direction.

## Files

In `docs/notes/deals-top-read-2026-11-21/`. Scripts take the scratch folder
`/data1/apartments/tmp/deals-top-read` as their argument. Blocks with the whole ad texts stay
in scratch.

- `pick.py`: the top and middle picks from the published table.
- `q90.py`: the 5%, 10%, 90% and 95% points from `drift_score.score_run`.
- `scan_records.py`: the picked ads' stored API records.
- `blocks.py`: the reading blocks, top and blind, and `fields.csv`.
- `deposit.py`, `deposit_kinds.py`: the deposit check over all 6,502 ads.
- `tally.py`: the tables above.
- `READER_TOP.md`, `CODER.md`: the briefs.
- `reads.csv`: the 60 broker reads, with short quotes.
- `codes.csv`: the 120 blind codes with field traits and short quotes; `blind_key.csv` maps
  the blind keys to ads and groups.
- `fields.csv`: coded fields of the 120 ads, with no text.
- `deposit_kinds.csv`: the 305 uncoded deposit-over-price ads by kind.
