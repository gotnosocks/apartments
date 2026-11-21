# Flex and studio wording against the bedroom-text term (2026-11-21)

No fit and no money spent. Scripts and logs are in `docs/notes/flex-wording-2026-11-21/`.

## The question

The read of the top Deals ads (`docs/notes/deals-top-read-2026-11-21.md`) named two ads with
bedrooms the coded count overstates. T25 is a "true alcove studio convertible to 2-bedroom"
coded as 2 bedrooms. T01 is a 5-bedroom whose "fifth bedroom remains flexible - the dividing
wall is not yet installed". The TODO item asked whether to extend the `beds` caution or the
bedroom text reader to wording of this kind.

The served model already carries `ad:bed_text_smaller`, 1 where `b0bedtext` finds flex
wording for the coded count (`bed_flex_at`) or a stated size below it (`bed_text_fewer`).
T25 has `bed_flex_at` and still shows 24.8% below its median. T01 has neither: the reader
takes no ordinal count ("flexible 5th bedroom") and no wall still to be built.

So there are two questions. Does wording the reader misses mark mispriced asks? And among
ads the term already marks, does any kind still hold an excess of low asks?

## Data

As in `docs/notes/short-lease-2026-11-21.md`: one text per listing, the latest split's l2bt
held-out errors (189,629 ads; l2bt carries `ad:bed_text_smaller`), and the any-unit note's
halves of buildings. `low` is an ask below the 5% point and `high` one above the 95% point.
The marks read the text and the coded bedrooms, never the ask. Every script printed both
halves at once, so half B was not held back from the choices below.

## Held-out errors by kind (`fx1_scan.py`, `fx3_split.py`)

| Kind | Held-out ads, A / B | Low, A / B | High, A / B | 90% coverage, A / B |
|---|---|---|---|---|
| `bed_text_smaller` (either flag) | 2,552 / 2,476 | 8.0% / 7.6% | 5.5% / 5.5% | 0.87 / 0.87 |
| `bed_flex_at` | 1,823 / 1,811 | 7.3% / 7.0% | 5.5% / 6.1% | 0.87 / 0.87 |
| `bed_text_fewer`, stated size 1 or more | 667 / 597 | 8.8% / 6.9% | 5.7% / 3.5% | 0.86 / 0.90 |
| `bed_text_fewer`, stated as a studio | 160 / 166 | 12.5% / 17.5% | 5.0% / 4.2% | 0.83 / 0.78 |
| Ordinal flex room ("flexible 5th bedroom") | 26 / 25 | 11.5% / 4.0% | 7.7% / 16.0% | 0.81 / 0.80 |
| Wall still to build ("wall not yet installed", "wall installation") | 38 / 25 | 5.3% / 8.0% | 21.1% / 4.0% | 0.74 / 0.88 |
| None of these | 86,883 / 88,283 | 6.0% / 5.7% | 4.9% / 4.9% | 0.89 / 0.90 |

- **The wording the reader misses** is rare (80 held-out ads not already flagged) and holds
  no steady excess of low asks. On half A the wall wording leans high. T01 has no class
  behind it.
- **Flex wording** with the flag is only a little above the unmarked rate (7.3% and 7.0%
  low), so the term prices it near enough. T25 is one of these.
- **A studio in the text of an ad coded 1 bedroom or more** is where the term falls short:
  12.5% and 17.5% low, mean gap −0.021 (se 0.008) and −0.024 (se 0.008). The term pools
  these with the larger group whose stated size is 1 or more, where the excess is small.

## The live studio readings (`fx4_live.py`, `fx4_live.log`)

Of 6,502 live Deals ads, 24 coded with 1 bedroom or more read as a studio in the text. About
16 are studios by their text ("luxury studio duplex", "studio + home office", "gorgeous
studio apartment"). Eight are reader errors:

- Six ads from one building whose amenity list names a "wellbeats studio". `AMENITY` lacks
  "wellbeats". Its "workout studio" is masked.
- "The size of a medium-to-large studio apartment", a bedroom described by its size.
- "Oversized parlor floor studio/office", a room of a larger unit.

The first studio reading in the default view is at place 376.

## What follows

No caution. A third of the live readings are wrong, and a caution hides an ad from the
default view, so it would hide eight good ads to flag about 16 others. None of the 16 is
near the top of the page. The finding belongs to the model: a separate term for a studio
reading on an ad coded 1 bedroom or more, beside `ad:bed_text_smaller`. It should come with
reader fixes for amenity names ("wellbeats" and its kind) and for "the size of a ... studio".
A reader change alters the column of every later fit, so it goes into the next base refit
as its one change, with a note and predictions first. It does not ride on the market refresh.
