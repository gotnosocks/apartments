# Unit quality flags in L1, and a fit adding the missing ones (2026-11-12)

The hand reads of `docs/notes/unit-level-reads-2026-11-12.md` found that most units far
from their building are penthouses, units with outdoor space, duplexes, units with a view
and big layouts. I checked which of these L1 already reads as a unit column, and scoped a
fit to add the rest. This note makes no fit.

## What L1 reads already

L1's design (`drift-building-phase-b0-latest-9a7830fb-l1`, 248 columns, from the kitchen
sink design in `building_zones_kitchen_sink.py`) has each of these as a unit column and as
a unit mean (`umean:`). The posterior medians from L1's pool, in log rent, are:

| quality | column | own | unit mean |
|---|---|---:|---:|
| penthouse | `unit:penthouse` | +0.068 | |
| top floor, elevator | `unit:elev_top` | +0.014 | |
| size | `unit:log_size_rel` | +0.016 | +0.261 |
| terrace | `ad:private_outdoor_terrace` | +0.001 | +0.016 |
| private roof deck | `ad:private_outdoor_private_roof_deck` | +0.007 | +0.022 |
| outdoor space, any | `ad:feat_private_outdoor_space` | -0.001 | +0.029 |
| water view | `ad:views_water` | -0.003 | +0.017 |
| loft | `ad:feat_loft` | +0.002 | +0.007 |

Penthouse, top floor, outdoor type, view and size are all in the model, so a fit that adds
them adds nothing. Two qualities from the reads are missing:

- **Duplex or triplex.** The design has no such column, and the listing codes have no such
  feature.
- **The size of the outdoor space.** The design knows a terrace is there, but not whether it
  is 40 or 600 sq ft. The readers quoted these sizes from the ad text again and again.

## Coverage from the ad text

I scanned the description of every capture in the 2026-11-09 records
(`unit-flags-scope-2026-11-12/scan.py`, 2,225,573 ads, 99.4% with text) with two patterns:

- A duplex pattern: duplex, triplex, two-level, two-story or multi-level.
- An outdoor size pattern: a number of square feet within 15 characters before, or 25
  characters after, a word for outdoor space (terrace, patio, balcony, garden, roof deck,
  deck, yard).

On the 1,973,089 ads in the model's rows:

| pattern | ads | share | on the 300 reads |
|---|---:|---:|---|
| duplex | 118,840 | 6.0% | 15 of the 16 duplex units; also 24 of the other 284 |
| outdoor size | 18,435 | 0.9% | 20 of the 90 outdoor or penthouse units; also 4 of the other 210 |

The duplex pattern finds the duplexes. It also fires on 8% of other units, mostly on
building copy ("a two-story townhouse") and on duplexes elsewhere in the building. The
outdoor sizes have a median of 675 sq ft and a 90th percentile of 4,000. That upper end is
mostly shared roof decks and gardens, so many of the matches describe the building's space
and not the unit's. Neither pattern is good enough as a model column as written.

## The fit, scoped

One change on L1: add two unit columns with their unit means.

1. `ad:duplex`, true when the ad's text calls the unit itself a duplex or triplex.
2. `ad:log_private_outdoor_sqft`, the log of the stated size of the unit's private outdoor
   space, 0 where none is stated, with `ad:private_outdoor_sqft_unknown` for a unit with a
   coded outdoor type and no stated size.

Both have to tell the unit from the building. A regex can't do that reliably, so I would
extract them with Haiku over the ads the patterns match (about 130,000 ads), and check the
extraction against the 300 reads before using it. Both come from the ad's own text, never
from its price, so they follow the rule for additive text features. The fit needs a dataset
build with the two columns, and a fit at about L1's cost of $12.

## Which goes first

The Student-t fit goes first. Its code is written and waits only for review and budget, and
it targets the pattern the reads found: units with a long record above their building that
the model pulls back too far. The flags fit needs an extraction pass, a check and a dataset
build first. It would explain part of the same gap with measured qualities, which Ben's rule
prefers, but its columns reach only 1% (outdoor size) to perhaps 3% (duplex, after the
building copy is removed) of rows. The coded outdoor columns L1 has already carry small
coefficients, so I expect a small gain from it. The order should flip if the Student-t fit
misses the gate.
