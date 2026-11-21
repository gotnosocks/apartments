# Unit labels reused across layouts (2026-11-21, no fit)

## Question

In section 2 of `zero-bed-apartments-2026-11-21.md`, 9 of 10 blind reads of 0-bed ads whose
unit's other ads all code 2 or more found those other ads describing a different apartment.
The TODO item asked what produces such units:

1. For the `U_any` rows (12,646 rows, 7,343 units: 0-bed training rows of the live run where
   some other ad of the unit codes 2 or more) and the `U_strict` stratum (every other typed ad
   codes 2 or more), which `analysis.label_units` layer joined each mismatched pair, the 0-bed
   page and the page of the 2+ ad?
2. The shares by layer, and how many of these units `unit-labels-v18` would split.
3. For the units v18 does not split, the main kinds, from fields.
4. A blind read of examples from the largest kind.

No fit was run, no money was spent and nothing went into the ledger. Scripts and logs are in
`docs/notes/label-reuse-2026-11-21/`. No ask or rent enters any column or selection: the
scripts read units, pages, labels, bedroom counts, stated sizes, baths, listers, dates and text.

## Data

- The marks of the zero-bed note: its `zeros.parquet` (`z2_marks.py`), with `U_strict` as
  `z3_size.py` defines it. A pair is the 0-bed training row and one other ad of its unit coded
  2 or more whose bedrooms no active ledger entry sets, as z2 counts them.
- The live build: `ads-417bbdf5ed03f5d3.parquet`, `rows-4f487ef77bb6ca61.parquet` and
  `records-941f4a6588cbd8cc.parquet`, and the live run's dataset
  `b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext`.
- `label_units`' inputs rebuilt from the live build's parquet files (`lr3_inputs.py`), as
  `label-join-2026-11-13/inputs.py` did for L1's build: 10,174,550 history links, 1,985,838
  ledger rows (11,232 dropped by label_months), 18,867 history pairs and 975,140 unit pages.
  My v17 rerun gives the rows file's `label_unit` on all but 11 of the kept rows.
- The scripts ran in `/data1/apartments/venvs/pipeline` (duckdb and the ledger reader) inside
  a `systemd-run --scope -p MemoryMax=3G` call.

## 1. No label_units layer joined any pair

`lr1_pairs.py`. The `unit_id` of the ads file, which z2 groups by, is the page unit: the unit
of one StreetEasy unit page, after the unit ledger's joins and splits. 975,117 of its units
hold one page. So every pair of the mark lies on one page under one label.

| | `U_any` | `U_strict` |
|---|---:|---:|
| 0-bed training rows | 12,646 | 3,115 |
| units | 7,343 | 3,115 |
| pairs (0-bed row, ad coded 2 or more) | 24,419 | 6,885 |
| pairs on one page | 24,419 | 6,885 |
| pairs on two pages joined by a label_units layer | 0 | 0 |
| pairs whose 2+ ad is a row of the live run | 21,493 | 6,217 |
| of those, the two rows in one fit unit | 8 | 0 |

By layer the shares are 100% one page and one label, and 0% for each of the seven layers. v18
changes only the history layer, so it splits none of the 7,343 units.

The fit does not group by page. It takes `split_unit`, which `unit-splits-v4`
(`analysis.history_splits`) cuts at every change of one bedroom or more, and a count of 0 never
goes back into a piece of 2 or more. Of the 21,493 pairs whose 2+ ad is a training row, 21,485
fall in different fit units. The 8 left are 6 rows at three pages, where a run of 1-bed and
2-bed ads sends a later 0-bed ad back to an earlier piece.

## 2. What label_units adds before the splits

`lr2_fit_units.py`, `lr3_layers.py`. The same question on the units of the live build's rows
file, which uses only rows and the rows file's counts. Of the 323,704 0-bed training rows with
no ledger entry:

| unit | rows with a row coded 2 or more in the unit | on the same page | on another page | only on another page |
|---|---:|---:|---:|---:|
| label unit (after label_units, v17) | 12,323 | 11,994 | 637 | 329 |
| fit unit (after unit-splits-v4) | 6 | 6 | 0 | 0 |

The 637 rows hold 907 cross-page pairs in 475 label units. By the first v17 layer that joins
the two pages:

| v17 layer | pairs | v18 keeps them joined | v18 splits them |
|---|---:|---:|---:|
| labels | 319 | 319 | 0 |
| aliases | 279 | 279 | 0 |
| swapped | 250 | 250 | 0 |
| word_letters | 22 | 22 | 0 |
| words | 21 | 21 | 0 |
| spelled | 3 | 3 | 0 |
| history | 11 | 0 | 11 |
| none in my rerun | 2 | 0 | 2 |
| all | 907 | 894 | 13 |

The spelling layers join "3" and "3fl", "1a" and "a1", "06" and "6": the same label written
two ways, which v18 leaves joined. History joins only 11 pairs of 2 rows, and v18 splits those.
After v18, 633 of the 637 rows still have a 2+ row on another page of their label unit. All of
them are cut apart again by unit-splits-v4.

## 3. Kinds of the pages

`lr4_kinds.py`. All 7,343 units are single pages, so v18's history rule leaves every kind
below as it is. Each row takes the first kind it meets:

1. on the market together: the 0-bed ad and an ad coded 2 or more on the page were both open
   for 14 days or more (from `on_day` or `first_day` to `off_day`);
2. floor label of several apartments: the label is a floor number alone ("2", "3rd-fl"), and
   another page of the building carries that floor with a letter ("2A", "2R", "F2");
3. one change of layout: in date order the page's typed ads change once between under 2 and 2
   or more;
4. back and forth: they change two or more times.

| kind | `U_any` rows | units | `U_strict` rows (= units) |
|---|---:|---:|---:|
| on the market together | 71 | 69 | 24 |
| floor label of several apartments | 1,643 | 985 | 438 |
| one change of layout | 5,698 | 3,819 | 2,170 |
| back and forth | 5,234 | 2,502 | 483 |
| all | 12,646 | 7,343 | 3,115 |

Other fields, over the `U_any` rows (`U_strict` in brackets):

- Label form: floor and letter ("3b", "1r") 7,126 (1,749); floor number alone 2,756 (823);
  three or more digits ("318") 2,512 (458); letters alone 226 (73); other 26 (12). No page
  has a blank label.
- The 0-bed ad's own text (`bed_text`): a studio 5,442 (1,218); 1 bed 218 (55); 2 or more
  200 (130); no count 6,786 (1,712).
- Time: the nearest ad coded 2 or more starts a median 824 days from the 0-bed ad (585), with
  quartiles 339 and 1,750 days (238 and 1,288). 165 rows (60) share a day on the market with
  one.
- Lister: the 0-bed ad shares its lister with an ad coded 2 or more on 5,193 rows (1,495).
  The largest listers are Nooklyn (918), Rentopia (549), KCI (465), Moinian (419), Compass
  (374) and Corcoran (318).
- Size and baths: both ads state a size on 898 rows. 426 are within 10% of each other and 472
  apart by 25% or more. An ad coded 2 or more states more full baths on 4,001 rows (1,076).
- Buildings: The Rheingold (138 units), Tribeca House (81), Bridgeview Dumbo (77), Aria at 90
  John Street (75), 338 Evergreen Avenue (70) and The Garnett (61) hold the most units. The
  Rheingold also leads the broker pages of `any-unit-pages-2026-11-21.md`.

So the units are mostly pages that held a studio or 1 bed in one year and a larger layout in
another, often years apart and from different listers, with ordinary apartment labels.

## 4. A read of the largest kind

`lr5_draw.py`, `reader_prompt.txt`, `lr6_tally.py`, `reads.csv`. From the 2,170 `U_strict`
rows of "one change of layout", 8 were drawn from each half of buildings with the seed
20261121. Each block gave the 0-bed ad and up to three ads of the page coded 2 or more, with
coded fields, lister, day and whole text, dollar figures masked and no ask. Two Sonnet readers
took 8 blocks each.

| verdict | half A | half B | all |
|---|---:|---:|---:|
| another apartment filed under the label | 3 | 6 | 9 |
| one apartment, the 0-bed code wrong | 2 | 0 | 2 |
| one apartment whose layout changed | 0 | 0 | 0 |
| a building or several layouts described | 1 | 0 | 1 |
| unclear (an empty or one-line text) | 2 | 2 | 4 |

9 of 16 read as two apartments under one label (Wilson 95% 0.33 to 0.77), 9 of the 11 decided
(0.52 to 0.95). The readers cite a 450 sq ft rear unit against an 800 sq ft full floor, a studio
with one bath against a 2-bed with two baths and a balcony, and a commercial space with a
garden against a 3-bed (L10). In the two miscoded blocks the 0-bed ad's own text states two
bedrooms, the case the text mark `T` already finds. 14 of the 16 texts name no unit, so text
gives little to code a page's identity from. No reader found a renovation or combination.

## Recommendation

Making v18 the default would fix none of this. Every mismatched pair of the unit mark lies on
one page, so no label_units layer joined it, and v18 changes only history joins between pages.
Before the splits, label_units adds a 2+ row on another page for 637 rows, and v18 would split
13 of those 907 pairs. A default rule change needs a refit of the served model, and this
evidence gives no reason for one.

The fit's units already keep these ads apart: unit-splits-v4 cuts the page at the change of
count, and only 6 of the 323,704 0-bed training rows share a fit unit with a row coded 2 or
more. The mismatch is a property of the zero-bed note's unit mark, which counts ads by page
before the splits. So:

- No pipeline rule. The unit mark should not be used for bedroom sets, as the zero-bed note
  already concluded; the text mark `T` stays the evidence for those.
- No ledger draft. Pages reused across apartments are many (7,343 here, 1,643 rows on floor
  labels of several apartments), spread over years and listers, and v4 already separates
  their layouts. A `split_unit` entry would only matter where two apartments of the same count
  share a page, which this mark does not find. The open hand read of The Rheingold in
  `any-unit-pages-2026-11-21.md` covers the largest building of both lists.
- Any later mark built from "the unit's other ads" should group by the fit's unit
  (`split_unit`) and say so.

## What was not checked

- Pages where two apartments of one count share a label: v4 does not cut those, and this mark
  cannot find them.
- Whether the 0-bed piece of a split page carries a different unit effect from its 2+ piece in
  the fit's posterior.
- The 2 cross-page pairs my rerun does not join, from the 11 rows where it differs from the
  build.
