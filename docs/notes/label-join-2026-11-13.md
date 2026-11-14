# History joins kept to labels that agree up to spelling (2026-11-13)

`analysis.label_units` joins the unit pages of a building in seven layers. The fourth layer,
`history`, joins the two pages of each pair of `analysis.history_pairs`, where an ad on one
page lists an ad on the other in its StreetEasy history. The history follows StreetEasy's
property id, and a broker can move a property record from one apartment to the next, so the
layer also joins different apartments (Riverbank 9H with 20H, 452 Amsterdam Ave 4S with 2N).
An earlier reading found two apartments in 14 of 19 history-layer units
(`/data1/apartments/tmp/outlier-sprint/s2/E/results.md`).

I added the rule `unit-labels-v18` to the model, with a history layer joining a pair only when
the labels of its two pages agree up to spelling. I reran v17 and v18 on the inputs of L1's
pipeline build, had Sonnet read 100 of the pairs, and wrote a copy of L1's dataset with v18's
units. Nothing has been fit on it. The scripts are in `label-join-2026-11-13/`.

## v17 stays the default

No fit hashes `pipeline/models/analysis/label_units.py`. Still, the served dataset, the
backtests and the Deals page all come from pipeline builds, and a new default would move their
units with no fit behind the change. So I treated the model as pinned and made v18 an option:

- The variable `label_rule` picks the rule. `PIPELINE_LABEL_RULE` sets it in
  `pipeline/config.py`, and it is `unit-labels-v17` when unset.
- `ops/pipeline/build.py` records the rule in the build's catalog line.
- The model raises an error on an unknown rule.

The model's code changed, so the next build reruns `analysis.label_units` and the models after
it once. Under v17 they write the same rows, and the rows file keeps its name, which
`build.py` takes from the file's SHA-256.

## The rule

`spelling_key` reads a label as runs of letters and digits and rewrites them:

1. It drops case, spaces and punctuation, a leading apt, apartment, unit, suite or residence,
   and a leading "no" or "num" before a number.
2. It writes each number without its leading zeros. It also drops a lone zero at the head of a
   label when letters follow, as in "0B" and "B", "00PH109" and "PH109", or Stuyvesant Town's
   "0ME" and "ME".
3. It writes "penthouse" as "ph", and a number word as its digits ("third" as "3", "fourb" as
   "4b").
4. It drops floor words ("fl", "flr", "floor") and the ordinal suffix after a number, so "3rd
   Floor", "THIRD-FL", "fl3" and "03" all give "3".
5. It puts the number first in a label of one or two letters and a number, so "H9" gives "9h"
   and "PH2" gives "2ph".
6. It keeps a hyphen between two numbers, so "1-2" and "12" stay apart.

"Apt 4-B", "#04b" and "UNIT4B" all give "4b", and "PENTHOUSE A" and "PH-A" both give "pha".
Each unit gets the set of keys of its pages' labels, and the history layer joins a pair when
the two sets share a key. The other six layers run as in v17.

A unit with no label on its pages, or only lead words such as "unit", gets an empty set, and
the history layer joins it to nothing. I want evidence beyond the history link before joining
two pages, and a blank label gives none. On L1's build no pair joined by v17's history layer
had a blank side, so the decision moves no rows there.

`pipeline/tests/test_label_units.py` checks:

- the key on 13 groups of spellings;
- the sets a unit gets from its pages;
- the history layer under v18 on small pages: 4D and D-4 join, 5A and 3A stay apart, and a
  page with no label joins nothing;
- the whole model under v18 on the test fixture, where the two units joined through history by
  v17 stay apart;
- the error on an unknown rule.

## Rerunning the rules on L1's build

L1's dataset comes from the build with the rows file `rows-b3ddebf19af1dc1e.parquet`. I rebuilt
the model's inputs from that build's parquet files in `/data1/apartments/pipeline/datasets`,
without the pipeline's database:

1. `extract_history.py` reads each ad's property history from the build's records file, as
   `ads.history_events` parses it.
2. `inputs.py` writes the ledger rows (the rows file and the ads dropped by
   `analysis.label_months`), the history pairs and the unit pages.
3. `count.py` runs the layers of `label_units.py` under both rules, cuts the label units into
   pieces as `analysis.history_splits` does, and writes each row's unit under v17, `split17`,
   and under v18, `split18`.
4. `count2.py` reruns the label-month check on the label units split by v18, and counts.

My v17 rerun gives the build's `split_unit` on all but 5 of its 1,969,284 rows, and on the
1,927 rows of my recheck it drops the same 130 rows in the label-month check as the build did.

## Counts

The build has 18,820 history pairs, 17,511 of them with rows on both pages. v17's history layer
joins 750 pairs left apart by the first three layers:

- 41 agree up to spelling, and v18 joins them as before: "0B" and "B", "3B" and "B3", "PHA"
  and "0PHA", "G09" and "0G9".
- 709 disagree, and v18 keeps them apart. No later layer joins any of them.

362 of the 709 pairs are at 175 Spencer Street in Brooklyn, where StreetEasy files many
apartments under the property id 1440913. The next building, 574 St Marks Avenue, has 10.

Under v18, 305 of v17's label units come apart into 661, from 707 page units.

| | The build's rows | L1's rows |
|---|---|---|
| Rows | 1,969,284 | 1,896,471 |
| Rows changing unit | 970 | 947 |
| Rows in units split by v18 | 1,669, in 279 units | 1,630, in 261 units |
| Held-out ads changing unit | | 71 of 189,647 |
| Held-out ads in units split by v18 | | 125, in 109 buildings |

At 175 Spencer Street, 36 of L1's rows change unit and 40 are in units split by v18, with a
single held-out ad among them.

In the label-month check, v17 drops 130 rows of the units split by v18, as a second ad of a label
unit in a month. v18 drops 10 of them, so 120 rows come back. They are missing from L1's rows
file, and only a pipeline build under v18 adds them.

## The reading

I drew 60 of the 709 split pairs and 40 of the 41 kept ones, at random with the seed
20261113 (`sample.py`). Each pair got a dossier with:

- the pages of both sides;
- the ads of both sides in date order, with each ad's labels, property id, ask, bedrooms,
  baths, rooms, stated size and lister;
- the first 600 characters of each ad's text.

Five Sonnet readers took 20 dossiers each, with the brief `READER.md`, and gave each pair the
verdict one apartment or two. `reads.jsonl` holds their verdicts and evidence, and `tally.py`
counts them.

| Pairs | One apartment | Two apartments | Unclear |
|---|---|---|---|
| Split by v18, 60 | 12 | 46 | 2 |
| of them at 175 Spencer Street, 29 | 0 | 29 | 0 |
| of them elsewhere, 31 | 12 | 17 | 2 |
| Kept by v18, 40 | 35 | 1 | 4 |

All 29 splits at Spencer Street separate two apartments, and so do 17 of the 29 decided splits
elsewhere (59%). Weighted over the 362 pairs at Spencer Street and the 347 elsewhere, about 80%
of v18's 709 splits are right, and between 134 and 144 of them cut one apartment in two. By
rows the share is nearer 59%, since Spencer Street holds 36 of the 947 rows changing unit.

In the 12 wrong splits, the labels differ by more than spelling:

- a label missing a part of the other: "A" and "1A", "D" and "6D", "8" and "8N", "3N" and
  "3NE", "2L" and "2";
- typos and truncations: "2363E" and "23603E", "thouse" and "house", "carriagehou" and
  "carriage-house", "parlor-floor" and "parlorfloor-2n";
- unrelated labels: "3" and "llc", "3" and "simplex", "2" and "1".

A rule joining a label with a longer one containing it would recover the first group. The
readers also judged "3" and "3bed" two apartments (pair 95), so such a rule needs its own test.

Among the kept pairs, 35 of the 36 decided ones hold one apartment (97%). The exception, "1B"
and "B1" (pair 75), was read with low confidence. Two of the four unclear pairs (38 and 69)
involve Stuyvesant Town's page "0me", whose ads describe three apartments: 624, 626 and 628
East 20th Street. The ads of that page belong to three apartments, so the page needs a
`split_unit` entry in the unit ledger rather than a label rule.

## The copy

`rentfrontier.b0labeljoin` wrote
`/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-labeljoin`
from L1's dataset and `l1_units.parquet`, the units of each row under both rules:

- A row takes `split18` as its `unit_id` where L1's unit equals `split17`, and keeps L1's unit
  on the 5 rows where they differ. 947 rows change unit, and 293 of L1's units become 342.
- The copy marks `carried_heldout` for a fit with `--split carried`: L1's latest split, less
  the rows no longer the single latest row of a unit with two or more rows. That keeps 189,616
  of L1's 189,647 held-out ads. Each of the 31 left out is in a unit split by v18 and ends up
  alone in its new unit.
- The manifest records the SHA-256 of L1's rows (`d901a565`) and of the units file
  (`02880bb7`), and the counts.

B0 rows carry no column derived from the unit, so changing `unit_id` is the whole change. The
120 rows restored in the label-month check are not in the copy.

## L1's held-out ads in split units

The gap is the log ask less L1's median, in percent, and the squared gap is in log units, both
with SEs clustered by building (`gaps.py`).

| L1's held-out ads | n | Gap (%) | Squared gap | Mean elpd |
|---|---|---|---|---|
| In units split by v18 | 125 | -1.24 ± 1.02 | 0.0107 ± 0.0025 | 1.027 |
| All others | 189,522 | -0.44 ± 0.02 | 0.00665 ± 0.00009 | 1.228 |
| Changing unit | 71 | -2.81 ± 1.24 | 0.0083 ± 0.0027 | 1.149 |
| Left out of the carried split | 31 | -2.39 ± 2.50 | 0.0156 ± 0.0051 | 0.785 |

L1 misses the ads in split units by more than the others. Their squared gap is higher by
0.0041 ± 0.0025, 1.6 SE, and their mean elpd is lower by 0.20, about 25 nats over the 125. The
ads changing unit ask 2.4% ± 1.2 less than the others against L1's median, about 2 SE. Under
v17 their unit's level partly comes from another apartment, and the negative gap agrees with
that apartment asking more.

## What a fit would test

A fit of L1's model on the copy with `--split carried`, against L1 on the same 189,616 ads,
would test whether L1's model predicts the ads in split units better from units holding one
apartment than from v17's units, net of v18's wrong splits. For the comparison I'd take L1's
scores from its `pred_scores.npz` on the carried ads, matched by listing. Only 947 rows change
unit, so I expect the scalars and the convergence to match L1's, and any change in elpd to come
from the 94 carried ads in split units and their buildings.

A build under v18 would also bring back the 120 rows, and a fit on that build would test the
whole rule.

## Predictions for a fit on the copy

I write these before any launch, and I propose none here. For L1's model on the copy with
`--split carried`, against L1 on the same 189,616 ads:

1. The fit passes the convergence gate, and sigma, nu, unit_sd and the phase factors fall
   within one posterior sd of L1's.
2. The summed elpd changes by about +4 nats, with 80% odds between -5 and +15, and stays within
   2 SE of zero. The paired SE comes to about 3 to 6 nats.
3. On the 94 carried ads in split units, the elpd rises by about 0.05 per ad on average, and
   the mean squared gap falls below L1's on the same ads, with the mean gap closer to zero.
4. Over all 189,616 ads, the RMSE and the median absolute error of the predictive median change
   by less than 0.0001 in log units, and the coverage of the 50%, 80%, 90% and 95% intervals
   by less than 0.01 percentage points.

## Unresolved

- The 120 rows restored in the label-month check need a pipeline build with
  `PIPELINE_LABEL_RULE=unit-labels-v18`.
- I did not trace the 5 rows where my v17 rerun and the build disagree. The copy keeps L1's
  unit on them.
- A containment rule for labels such as "D" and "6D" or "8" and "8N" needs writing, and testing
  against "3" and "3bed".
- Pages holding several apartments, such as Stuyvesant Town's "0me", need `split_unit` entries
  in the unit ledger, like the 15 of 2026-11-12. v18 leaves those entries in force, since the
  layers read each row's page unit before the ledger's splits.
