# Four traits from the Deals top read, on held-out history (2026-11-21)

No fit and no money spent. Scripts and logs are in `docs/notes/four-traits-2026-11-21/`.

## The question

The read of the top Deals ads (`docs/notes/deals-top-read-2026-11-21.md`) counted four traits
more often in the top 60 than in the middle of the list: walk-ups in the text (7 against 1),
a virtual doorman (16 against 7), a condo or co-op unit an owner rents out (7 against 1), and
garden or ground-floor wording (18 against 11). A count among live ads cannot tell a missing
feature from a bargain, so each trait goes to the held-out history instead: does it mark asks
the model prices badly, on both halves of the buildings?

## Data

As in `docs/notes/flex-wording-2026-11-21.md`: the latest split's l2bt held-out errors
(189,629 ads), one text per listing, and the any-unit note's halves of buildings. `gap` is
the mean log error, `low` an ask below the 5% point and `high` one above the 95% point, so an
ad the model fits has gap near -0.004 and low and high near 0.05 to 0.06. The marks read coded
fields or the text, never the ask. Each script printed both halves at once, so half B was not
held back from the choices below.

- The walk-up mark is the ads dataset's `elevator` False, by the first entry of `regions` (a
  crawl region, not a borough).
- The doorman mark is the coded `doorman_type`.
- The condo mark is "condo", "condominium" or "co-op" in the text; the owner mark is "owner",
  "owned by", "privately owned" or "my apartment".
- The garden mark is garden-level, ground-floor, lower-level, below-grade or basement
  apartment wording, against the coded `label_floor` (`physical_floor` is empty in this
  build).
- `fx6_floor1.py` then reads the floor snapshot the served model's floor curve uses
  (`unit-floor/20261021-d84914c0`), with its garden and lower flags.

## Results (`fx5_fields.py`, `fx6_floor1.py`)

**Walk-ups: no steady excess of low asks.** In each region the coded walk-ups run a slightly
lower median than the elevator buildings, most below 59th Street (gap -0.012 and -0.010, se
0.003) and around Prospect Park (-0.011 and -0.012), but the low share does not hold: 8.5%
on half A below 59th and 6.5% on B, 5.9% and 5.4% around Prospect Park. Part of the gap is
floor 1, below.

**Virtual doorman: no excess.** 12,929 and 13,270 ads, low 5.6% and 5.9%, against full-time
doormen at 6.5% and 6.4%.

**Condo or co-op text: a small two-sided excess.** 8,583 and 8,464 ads, low 7.0% and 7.0%
and high 5.7% and 5.5%, against 5.9% and 5.7% low and 4.9% and 5.0% high for the rest. The
median is close (gap -0.007 and -0.005 against -0.004), so the interval is a little narrow for
these units, which fits units let by many small owners. Owner wording adds nothing on its own
(4.6% and 4.2% low).

**Garden wording: nothing beyond the floor.** Garden wording on coded floor 1 is 5.2% and 6.9%
low on 134 and 102 ads. The excess is in coded floor 1 itself, with or without the wording.

**Floor 1: a steady excess of low asks, on both halves.**

| Coded `label_floor` | Ads (A, B) | Gap (A, B), se | Low (A, B) | High (A, B) |
|---|---|---|---|---|
| 1 | 6,328, 6,471 | -0.012, -0.011, 0.001 | 8.3%, 8.0% | 5.5%, 5.2% |
| 2-3 | 20,123, 20,138 | -0.004, -0.004 | 5.3%, 5.2% | 4.5%, 4.8% |
| 4+ | 40,167, 41,738 | -0.003, -0.003 | 5.6%, 5.4% | 4.9%, 4.8% |
| unknown | 26,677, 26,176 | -0.004, -0.004 | 6.6%, 6.3% | 5.3%, 5.4% |

On the model's own floor snapshot, floor 1 runs low in every building group and with or
without the garden flag:

| Snapshot floor 1 | Ads (A, B) | Gap (A, B) | Low (A, B) |
|---|---|---|---|
| elevator | 1,611, 1,747 | -0.016, -0.014 (se 0.002) | 10.7%, 9.3% |
| walk-up | 212, 262 | -0.015, -0.016 (se 0.006) | 12.3%, 6.5% |
| elevator not coded in the ads dataset | 5,152, 5,041 | -0.011, -0.011 (se 0.001) | 7.4%, 7.6% |
| garden flag on floor 1 | 450, 402 | -0.019, -0.016 (se 0.005) | 8.0%, 8.2% |

Floor 2 in elevator buildings is 5.9% low on both halves, gap -0.004. So the model prices a
floor-1 unit about 1% above where its held-out asks fall, and the low tail is wider there. The
`unit:garden` flag does not take it up.

## Why floor 1 might run low

The served model's floor curve is pinned at zero on floor 1 and draws floors 2 and up from a
Gaussian process on log floor (`building_zones_floor.py`), with a lengthscale prior centred
on 0.7, about the distance from log 1 to log 2. A smooth curve can only partly follow a step
between the ground floor and the next. A broker would add that ground-floor units vary more:
street noise, a window onto a shaft or a back yard, bars on the windows, a duplex with a
cellar. Both readings fit a lower median and a wider low tail.

## Decision

No caution: floor 1 is a trait of the unit, and a lower price for it is what a renter expects.
The next base refit gets a candidate change: a `unit:floor1` step outside the Gaussian process,
with the Normal(0, 0.5) prior the floor flags carry, so floor 1 can sit apart from the curve.
It goes in as one change, with its own note and predictions first. A floor-1 scale term is the
second candidate if the step leaves the low tail wide. The condo text is a weaker lead for a
scale term. Walk-ups, the virtual doorman and garden wording are closed.
