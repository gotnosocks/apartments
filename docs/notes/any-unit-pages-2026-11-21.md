# Pages that brokers use for any unit of a building (2026-11-21, no fit)

## Question

In some buildings brokers post ads for any unit of the building under whichever unit page is
at hand. The Rheingold (10 Monteith St) is the case that raised it
(`docs/notes/outlier-sprint-2026-11-11.md`, "The Rheingold"). A page there names no single
apartment, so its unit level averages several apartments. Can the practice be marked from the
ads, and does it hurt the model's held-out asks? The TODO item asked for a screen on the ads'
text and on asks running at once on a page, and for a choice between leaving those unit levels
and dropping them.

No fit was run, no money was spent and nothing went into the ledger. Scripts, logs and the
blind reads are in `docs/notes/any-unit-pages-2026-11-21/`; scratch files are under
`/data1/apartments/tmp/any-unit`.

## Data

- Ads: the candidate ads of the pipeline dataset `ads-14f9e88d75290a0f.parquet` (an ad with a
  unit and a fate in the unit-month check: kept, superseded in its unit-month, or dropped for
  a conflicting layout there), 2,071,277 ads on 938,584 pages (`a2_ads.py`). A page is a
  `unit_id`. An ad runs from its first day to its off day, or to the fetch day while active.
- Texts: the build's records file `records-0d20eb92b9f08c7d.parquet`, one text per listing
  (the last ACTIVE record's, as `descriptions.record_descriptions` takes it), 2,068,472 with a
  text (`a1_texts.py`, `a4_text.py`).
- Held-out asks: the latest split's 189,647 held-out ads in `pred_scores.npz` of
  `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt` (l2bt). Each is the
  latest ad of a unit whose earlier ads trained the fit. 189,629 join the ads frame.
- Deals: the published table (`/data1/apartments/site/deals/deals.json`, 6,502 ads, run
  `...-6cd1f12b-range-m3`), with its own build `ads-417bbdf5ed03f5d3.parquet` and
  `records-941f4a6588cbd8cc.parquet`.
- Halves: buildings cut in two by the hash of `commercial-sweep-2026-11-20/sw3_counts.py` with
  that note's seed. Each mark's form was chosen on half A and checked on half B.

## The two marks

Neither mark reads a model output. The text mark reads no ask. The overlap mark reads the
asks of the two ads in each pair, since it asks whether they are more than 10% apart. As a
screen that is allowed: the held-out comparison below drops each held-out ad's own pairs, so
its ask takes no part in its mark, and a Deals caution built on the mark would be allowed too.
A data rule built on the overlap mark is not allowed, because other rows' rents would then
shape which rows the fit keeps (`docs/leak-free-scoring.md`). The text mark's phrase was chosen
partly by its lift on the overlap fact, so a rule on it would first need its choice redone from
the size fact alone, or confirmed on rows outside the choice.

**Text.** Eight candidate phrases were matched on every ad (`a4_text.py`, contexts in
`logs/a5_context.log`). A page carries a phrase when any of its ads does. A phrase joined the
mark when its half-A pages held at least twice the half's rate of two page facts that read no
rent: an overlap of asks (below) and two stated sizes more than 15% apart (`a6_page_facts.py`,
`a7_choose.py`). Only one phrase passed:

| phrase on half A | pages | lift, overlap | lift, size |
|---|---|---|---|
| any unit of the building ("any unit in the building", "any of the available apartments") | 923 | 3.2 | 4.5 |
| multiple or several units available | 551 | 2.5 | 2.0 (just under) |
| other units available | 578 | 2.9 | 1.8 |
| layouts, units or photos may vary | 986 | 2.3 | 1.9 |
| various or different layouts | 1,764 | 2.1 | 1.2 |
| similar units | 14,247 | 1.3 | 0.8 |
| photos representative | 15,459 | 1.0 | 0.5 |
| prices start at, range or vary | 4,337 | 0.6 | 0.6 |

"Similar unit" and "representative" are photo disclaimers of buildings with one apartment to a
page, and they hold no excess. The text mark is the first phrase alone.

**Overlap.** Two candidate ads of a page run at once for at least 4 days with asks more than
10% apart (the ask ranges, first to latest ask, do not come within 10%). Eleven forms were
compared on half A by the share of their pages that carry the text mark and the size fact
(`a7_choose.py`). The asks-only form at 4 days and 10% led on both (2.0% text and 17.1% size
against 0.43% and 3.5% for all pages). The forms that count a change of bedroom count mark
more pages with weaker facts, and the fit already cuts a page at a change of count.

Counts on pages with two or more candidate ads (`logs/a8_marks.log`):

| half | pages | text | overlap | both | either | ads on them | buildings |
|---|---|---|---|---|---|---|---|
| A | 214,660 | 923 | 1,177 | 24 | 2,076 | 15,366 | 960 |
| B | 218,365 | 722 | 1,236 | 24 | 1,934 | 12,396 | 1,057 |

330 more text-marked pages hold one ad only. The check on half B holds for the overlap mark
(17.0% size, 1.94% text against 3.5% and 0.33%) and only in part for the text mark: its size
fact falls to 4.7% against 3.5%, while overlap among its pages stays at 3.3% against 0.57%.
On half A the size fact reads 15.7% on text pages, and The Rheingold holds 413 of those 923
pages.
The text mark gathers in a few Brooklyn rental buildings (Bridgeview Dumbo 137 pages, 205 N
9th St 109, The Garnett 105, Leonard Pointe 76). The two marks barely meet: The Rheingold's
pages hold their ads one after another, so the overlap mark finds 5 of its 414 marked pages.

## Blind reads

60 pages that hold a held-out ad were drawn (`a10_draw.py`): 10 text-marked and 10
overlap-marked a half, and 20 unmarked pages from the same buildings. Each dossier gave the
page's ads (the 12 latest) with dates, coded counts, size, unit label and text, dollar figures
masked and no ask. Six Sonnet readers took 10 pages each in shuffled order, told nothing of the
marks, and answered whether the page is one apartment or several
(`reader_prompt.txt`, `reads.csv`, `a11_precision.py`).

| set | reads | several | unclear | precision (Wilson 95%) |
|---|---|---|---|---|
| either mark, half A | 20 | 8 | 2 | 0.40 (0.22 to 0.61) |
| either mark, half B | 20 | 5 | 4 | 0.25 (0.11 to 0.47) |
| either mark, both | 40 | 13 | 6 | 0.33 (0.20 to 0.48) |
| text mark | 20 | 5 | 5 | 0.25 (0.11 to 0.47) |
| overlap mark | 22 | 9 | 1 | 0.41 (0.23 to 0.61) |
| unmarked, same buildings | 20 | 4 | 0 | 0.20 (0.08 to 0.42) |

Unclear reads count against a mark; among clear reads the marks give 0.38 (0.24 to 0.55).
Of the 7 Rheingold pages read, 3 were several, 2 one and 2 unclear. Outside The Rheingold the
text mark read one apartment in 8 of 13 pages: a broker offering to show other apartments still
posts each ad on the right page there. Pages that mix apartments are common in these
buildings whatever the mark (a fifth of the unmarked pages), and the marks lift that share
from about 0.20 to 0.33.

## Held-out asks

`a9_heldout.py` compares held-out ads on marked pages with ads on unmarked pages of the same
buildings and with all held-out ads. The overlap mark there leaves out the held-out ad's own
pairs, so the held-out ask takes no part in its mark. `gap` is log ask less log predicted
median, `sd` the spread of the gap, `cover90` the share inside the 5% to 95% interval, `low`
the share below the 5% point. Standard errors resample buildings (400 draws).

Either mark (`logs/a9_heldout.log` has each mark alone):

| half | group | ads | gap | sd | cover90 | low |
|---|---|---|---|---|---|---|
| A | marked | 990 | -0.004 (0.003) | 0.086 (0.004) | 0.838 (0.017) | 0.074 (0.010) |
| A | same buildings | 5,231 | -0.003 (0.001) | 0.083 (0.006) | 0.876 (0.007) | 0.062 (0.005) |
| A | all | 94,180 | -0.004 (0.000) | 0.079 (0.001) | 0.892 (0.001) | 0.060 (0.001) |
| B | marked | 852 | -0.006 (0.003) | 0.083 (0.004) | 0.853 (0.020) | 0.086 (0.013) |
| B | same buildings | 5,859 | -0.002 (0.001) | 0.073 (0.002) | 0.888 (0.006) | 0.058 (0.004) |
| B | all | 95,449 | -0.004 (0.000) | 0.078 (0.001) | 0.894 (0.001) | 0.058 (0.001) |

Marked less all, A then B: sd +0.007 (0.004) and +0.005 (0.004); cover90 -0.054 (0.016) and
-0.041 (0.020); low +0.014 (0.010) and +0.028 (0.013). Marked less same buildings: sd +0.002
(0.007) and +0.010 (0.004); cover90 -0.037 (0.017) and -0.035 (0.019); low +0.012 (0.011) and
+0.027 (0.013).

By mark: text pages have no wider spread (0.080 on both halves, as for all ads) and lower
coverage (0.827 and 0.832), because the model gives them narrower intervals (median width
0.18 and 0.19 in log against 0.22 for all ads, `a13_width.py`): their many ads make the unit
level look well known. Overlap pages have a wider spread (0.092 and 0.086 against 0.081 and
0.074 in the same buildings), wider intervals already (0.22), and coverage 0.848 and 0.858.

So the practice costs the model something on both halves, with no shift of level: about 4 to 5
points of coverage and 1 to 3 points more below the 5% point, on 1,842 held-out ads (1.0% of
the split).

## Deals

`a12_deals.py` recomputes the marks on the live build for the pages of the 6,502 Deals ads
(texts from the live records file), with the table's order by `below_share`:

| mark | Deals ads | top 100 | uncautioned | top 100 of the uncautioned |
|---|---|---|---|---|
| text | 26 | 0 | 5 | 0 |
| overlap | 17 | 0 | 10 | 0 |
| either | 42 (0.65%) | 0 | 15 of 4,884 | 0 |

At 0.65% the top 100 would hold 0.65 marked ads by chance, so the absence tells nothing either
way. The first marked ad ranks 509th and the median 3,826th. Bridgeview Dumbo holds 9 and The
Rheingold 7 (`deals_marked.csv`).

## Recommendation: nothing

Evidence thresholds. These were set after the results above were known, so they are post
hoc, and the verdict rests on the numbers as much as on the lines drawn through them:

- A pipeline rule dropping the unit level needs read precision with a Wilson lower bound of at
  least 0.5 on each half. The marks read 0.40 (0.22 to 0.61) and 0.25 (0.11 to 0.47), and
  their upper bound on both halves together (0.48) is below 0.5. About half the marked pages
  read one apartment, and their unit levels carry information.
- A Deals caution needs the marked ads' share below the 5% point to be at least twice the
  half's share on both halves, and marked ads among the top 100. The share is 1.23 and 1.48
  times the half's, and the top 100 holds none.

Neither is met, so the count changed is 0 ads. For scale, a rule would have dropped the unit
level on 4,010 pages holding 27,762 ads, and a caution would have marked 42 Deals ads, 15 of
them uncautioned and none in the top 100.

The coverage loss holds on both halves. It belongs with the noise-scale terms the history
scans already propose (`docs/TODO.md`, L1 and the changed-count factor), and a scale on the
overlap mark is a candidate term for a later fit. Its form here is a page fact built from
each ad's latest ask, which leaks: a held-out ad's ask would set its own scale, and later ads
would set the scale of earlier ones. The leak-free form builds the flag for each ad from the
page's ads that started before it, read as of the ad's first day (each one's ask as last recorded
by then), with the ad's own ask left out. It reads earlier rents of the same unit, so it goes
in `features.READS_EARLIER_RENTS` and is scored on the latest split, with a prediction
written first.
The Rheingold itself is better repaired by hand than by a rule: a `split_unit` review of its
pages, where 3 of 7 read several, would go to Data improvements with the other
unit-ledger work.
