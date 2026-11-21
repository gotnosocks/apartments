# A short-lease caution on Deals (2026-11-21)

No fit and no money spent. Scripts and logs are in `docs/notes/short-lease-2026-11-21/`.

## The question

The read of the top Deals ads (`docs/notes/deals-top-read-2026-11-21.md`) found one ad, T40,
whose text prices a 6-month lease: "$17,500 for a 6-month lease or $19,995 with 1 month free
and 1 month OP". Does wording of that kind mark asks the model misprices on held-out history,
and how common is it?

## Data

- Texts: one per listing, the last ACTIVE record's description, else the last record's
  (the rule of `descriptions.record_descriptions`), 2,071,277 listings, from the scratch
  table the any-unit note built (`docs/notes/any-unit-pages-2026-11-21/a1_texts.py`,
  `a4_text.py`).
- Held-out errors: the latest split's l2bt run, 189,629 ads. `gap` is the log ask less the
  log of the predicted median; `low` and `high` say the ask is below the 5% point or above the
  95% point.
- Halves are the any-unit note's halves of buildings. Half A was meant to choose the form and
  half B to check it, but one script printed all four forms on both halves at once, so half B
  was not held back from the choice.
- Each mark is a regex on the lowercased text with runs of white space as one space. The scan
  did not map dashes to hyphens as `cautions.plain` does, so it misses a few "6–month" forms
  the caution takes. No ask enters a mark.

## Four forms of the wording (`sl1_scan.py`, `sl1_scan.log`)

`N` is a number of months from 1 to 11, in digits or words.

| Form | Listings with it | Held-out ads, A / B | Low, A / B | High, A / B | 90% coverage, A / B |
|---|---|---|---|---|---|
| "N-month lease" (also "N mo term", "N month sublet", "rental", "stay") | 3,569 | 83 / 74 | 15.7% / 18.9% | 4.8% / 12.2% | 0.80 / 0.69 |
| "lease of N months" | 1,027 | 59 / 25 | 6.8% / 4.0% | 5.1% / 4.0% | 0.88 / 0.92 |
| "short-term lease" (or rental, stay, sublet, furnished) | 5,348 | 372 / 235 | 7.8% / 10.6% | 4.3% / 7.2% | 0.88 / 0.82 |
| "month-to-month" | 407 | 12 / 12 | 16.7% / 8.3% | 8.3% / 8.3% | 0.75 / 0.83 |
| None of the four | | 93,669 / 95,113 | 6.0% / 5.8% | 5.0% / 5.0% | 0.89 / 0.90 |

On half A only the "N-month lease" form shows a clear excess of low asks: 15.7% against
6.0%, 13 of 83 ads. Mean gap −0.029 (se 0.011). Half B repeats it: 18.9% against 5.8%, 14 of
74 ads. B's mean gap does not repeat A's: −0.008 (se 0.014). Half B also has an excess of
high asks, so the model's interval is too narrow for these ads in both directions, and the
excess of high asks offsets the low ones in the mean. "Month-to-month" is too rare to choose
on. "Lease of N months" is near the unmarked rate on both halves. "Short-term" is near it on
half A but 10.6% low on half B; it is left out, though a later scan could take it up.

## What the mark finds (`sl2_snips.py`)

Forty half-A held-out ads with the mark, drawn by a hash of the listing id and printed with
dollar amounts masked. All 40 name a lease or term under 12 months, as an option, a minimum
or the only term. In 11 the text ties the rent shown to the short lease. Examples: "price
advertised is on 10 month leases" (three ads of one landlord), "price is offered for a
9 month lease", "net effective for 1 month free on an 11-month lease", "3 months complimentary
on a 10 month lease", "price reflects a 10 mo term average rent". Several of the low ones are
of this kind, where the rent shown is a net rent over a short lease.

## The live Deals table (`sl3_live.py`, `sl3_live.log`)

On the texts the publish of `range-m3` read, 8 of 6,502 ads carry the mark; one already has
another caution. Six are in the default view, at places 39 (T40), 1,380, 2,953, 3,043, 3,313
and 3,883.

## What follows

`cautions.short_lease` takes the "N-month lease" form, with a guard so "13-month" and
"1.5 month" do not match on their last digit, and another so "one month rental fee" and
"1 month rental deposit" do not match (about 24 of the form's matches over all texts are
fee wording of that kind). The chip reads "short lease"; the description
reads "the ad offers a lease shorter than a year, and the rent shown may be for it". Like the
other text cautions it hides an ad from the default view and is computed at publish from the
texts, so the backtest, which has no texts, does not carry it. It reads only the text, so it
could also be a data rule or a term, but with 157 held-out ads in all it is too rare to pay
for a fit.
