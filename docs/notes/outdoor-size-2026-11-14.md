# Outdoor size: the stated private outdoor area from ad text, screened against L1 (2026-11-14)

S16 (`blind-spots-2026-11-14.md`) found that ads stating an outdoor area of 300 sq ft or more,
by S7's match, ask +0.021 ± 0.005 over L1's median on the 684 held-out ads outside its draw,
with 1.42 times the spread and 71% inside L1's 80% interval. L1 reads the six private outdoor
types and the private-outdoor feature from the listing codes, and none of its columns gives
the size. If a bigger private terrace is worth more, part of that excess should follow the
size. To test this I wrote a tighter extractor, `rentfrontier.b0outdoorsize`, put its two
columns into a copy of L1's dataset, had readers check a sample of its matches and screened
the columns against L1's held-out predictions. Nothing is fit, nothing goes to Modal, and no
photo, floor plan or OxyLabs page is fetched. The scripts are in
`docs/notes/outdoor-size-2026-11-14/` and write to `/data1/apartments/tmp/outdoor-size-2026-11-14/`.

## Predictions, written before the precision reads and the screen

I wrote this section at 04:55 ET on 2026-11-14 and committed it before I drew the reads or
computed any gap for the new columns. At that point I knew:

- the extractor's results on the 460 reads I developed it on: S7's 400 reads, where it agrees
  with the readers' area within 5% on 94 of the 95 ads both give an area for, and S16's 60
  precision reads, where it marks all 26 `outdoor_large` ads the readers called private and
  none of the 4 they called shared or unclear;
- its counts over L1's 1,896,471 rows: 13,718 rows with an area, 12,058 of them with a
  private-outdoor code, and 1,475 held-out ads outside S16's draw, 1,338 coded and 137 not;
- S7's finding that among held-out ads with the private outdoor flag and a stated size, the
  gap doesn't rise with the size (-0.02 ± 0.16% per doubling), with every bin from 100 sq ft up
  at +1.8% to +2.5% and the ads under 100 sq ft at -0.1%;
- S16's figures for `outdoor_large`, given above.

What I expect:

1. **Precision.** The readers confirm the area on 0.90 or more of the pool, weighted by
   stratum, with the lower end of the 95% interval above 0.75. Leaving out unclear answers,
   0.93 or more.
2. **Level.** The 1,475 marked held-out ads ask +0.010 to +0.025 over L1's median on average.
3. **By size.** Ads under 100 sq ft come out between -0.010 and +0.010, ads from 100 to 300 sq
   ft between 0 and +0.020, and each bin from 300 sq ft up between +0.012 and +0.030.
4. **Slope.** Within the marked ads, the gap rises by -0.3% to +0.5% per doubling of the area,
   with an SE near 0.2%, so I expect no clear slope, as S7 found. Within the coded ads alone,
   the same.
5. **Spread and coverage.** The standardized residual's sd comes to 1.1 to 1.5 times that of
   all held-out ads in each bin, highest from 300 sq ft up. The share inside L1's 80% interval
   comes to 0.70 to 0.78 from 300 sq ft up and 0.74 to 0.80 below.
6. **Coded or not.** The 137 uncoded ads ask 0 to 3 points more over L1's median than the
   1,338 coded ones, since L1 has no outdoor column to give them. Their mean gap comes to
   +0.015 to +0.045, with an SE near 0.01.
7. **A model term.** I write one, without fitting it, if the slope is 0.5% per doubling or
   more and over 2 SE, or if the uncoded ads differ from the coded ones by more than 2 SE.
   Otherwise I write none, and the columns stay in the dataset copy for later screens.

## The extractor

S7's match took any number of square feet within a few words of an outdoor word. In the
reads of S7 and S16 it also caught roof decks and gardens the whole building shares, sizes in
lists of building amenities, and interior sizes. `rentfrontier.b0outdoorsize` starts from
the same idea and adds checks, which its docstring gives in full:

- The outdoor word has to start within 4 words after the area, with no word between that
  ties the area to something else ("1,200 sq ft apartment with a terrace" fails), or end
  within 6 words before it, joined only by connecting words ("a terrace measuring about
  500 sq ft").
- I drop the area when interior or lot words follow it, when the outdoor word belongs to a
  place or a unit type (garden level, Carroll Gardens), when shared or building words come
  with it and no private word does, when a negation comes just before it, and when its
  sentence says only some units have the space.
- I also drop a roof deck, and any area in a list of building amenities, unless a private
  word comes with it.
- An ad with several areas gets the stated total when it gives one, and otherwise their sum.
  Areas under 20 or over 5,000 sq ft count as implausible and give no value.

The text is the description of each listing's latest record, picked as `b0textflags` picks
it. I developed the checks on 460 ads read before this item (`o1_dev.py`):

- On S7's 400 reads, the readers gave an area for 98 ads and the extractor for 97, and on
  the 95 ads where both give one they agree within 5% on 94. S7's parse gives an area on 105
  of these ads; it agrees with the readers on 81 of the 92 it shares with them, and 13 of
  its areas come on ads where the readers found none.
- Of S16's 30 `outdoor_large` precision reads, the extractor marks all 26 the readers called
  private and none of the 4 they called shared or unclear.

## The dataset copy

I built the copy from L1's dataset (rows SHA-256
`d901a565b7836cea82aac6924e8df5139271aa1292508811dd121fabaa0c7a3d`) with
`python -m rentfrontier.b0outdoorsize SRC OUT`, under a 3 GB memory cap. It is at

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-outdoorsize

and holds L1's rows in L1's order with two columns added: `outdoor_sqft`, the area or NaN,
and `outdoor_sqft_src`, how the area was read. Its rows SHA-256 is
`1bd20f04b036e5d8c273e922a1f34302f992dc497d49b45cc1f2f3a897008267`, and the manifest's
`outdoorsize` entry records the source, the patterns and the counts below.

## Counts

Of L1's 1,896,471 rows, 1,825,199 have a description, and 13,718 (0.72%) get an area
(`o2_counts.py`):

| how the area was read | rows |
|---|---:|
| area, then the outdoor word | 11,742 |
| outdoor word, then the area | 1,651 |
| sum of several areas | 203 |
| stated total | 112 |
| midpoint of a range | 10 |

Another 2,116 rows have only implausible areas and get none. Counted over matches, the roof
deck check drops 8,511, the amenity check 5,593, the shared checks 2,539, the place and unit
type check 229 and the some-units check 106.

The areas run from 112 sq ft at the 10th percentile through 250, 500 and 800 at the
quartiles to 1,100 at the 90th and 3,000 at the 99th. By size, 1,239 rows have 20 to 100 sq
ft, 1,767 over 100 to 200, 1,450 over 200 to 300, 3,331 over 300 to 500, 4,436 over 500 to
1,000 and 1,495 over 1,000. 12,058 of the 13,718 rows (87.9%) carry a private outdoor code
L1 reads. 1,481 are held-out ads, 1,475 of them outside S16's draw: 1,338 coded and 137 not.

Against S16: S7's parse gives a size on 10,380 rows, and S16's `outdoor_large`, S7's size of
300 or more, marks 6,681. The new column gives 5,648 of those an area of 300 or more and 10 a
smaller one, and the other 1,023 get no area. It gives 300 or more to 9,857 rows in all,
4,209 of them outside `outdoor_large`.

## Precision

I drew 40 ads from the 13,591 rows with an area, leaving out the 460 development ads and
S16's 400 drawn ads (`o3_draw.py`, seed 20261114). The draw takes 3 ads from each size bin of
the area-first matches, 2 from each size bin of the word-first matches, 2 ranges, 4 totals
and 4 sums. Four Sonnet readers read 10 ads each, with dollar figures masked and the
extractor's area left out, and said whether the description states the size of a private
outdoor space belonging to this unit alone (`precision_prompt.txt`).

All 40 said yes. Weighted back to the pool as in `text-flags-2026-11-13/t4_score.py`
(`o4_precision.py`), precision is 1.00, with a 95% interval of 0.83 to 1.00 and an effective
sample of 19. With no unclear answers, the settled precision is the same. The readers' own
total comes within 5% of the extractor's on 38 of 40 ads (0.83 to 0.99). In both misses the
ad states one space's size and multiplies it with "each" or "two", and the extractor counts
the size once. Forty reads can't tell a precision of 1.00 from one near 0.85.

## The screen

`o5_screen.py` matches the copy to L1's `pred_scores.npz` on the latest split and leaves out
S16's 400 drawn ads. The gap is the log ask less L1's median. "Within building" is the gap
less the mean gap of the building's other kept held-out ads. The z sd ratio and the MAD ratio
compare the group's spread with that of all kept held-out ads, and "in 80%" is the share
inside L1's 80% interval. SEs are clustered by building.

| group | ads | mean gap | within building | z sd ratio | MAD ratio | in 80% |
|---|---:|---:|---:|---:|---:|---:|
| all kept held-out ads | 189,247 | -0.0046 | | 1 | 1 | 0.798 |
| with an area | 1,475 | +0.0196 ± 0.0032 | +0.0269 ± 0.0035 | 1.16 | 1.41 | 0.729 |
| coded | 1,338 | +0.0170 ± 0.0033 | +0.0245 ± 0.0036 | 1.16 | 1.41 | 0.729 |
| uncoded | 137 | +0.0448 ± 0.0121 | +0.0487 ± 0.0134 | 1.14 | 1.34 | 0.730 |

By size, with each bin holding its upper end:

| sq ft | ads | mean gap | within building | z sd ratio | MAD ratio | in 80% |
|---|---:|---:|---:|---:|---:|---:|
| 20 to 100 | 161 | -0.0097 ± 0.0064 | +0.0014 ± 0.0063 | 0.95 | 1.03 | 0.814 |
| 100 to 200 | 218 | +0.0070 ± 0.0061 | +0.0080 ± 0.0062 | 1.08 | 1.13 | 0.752 |
| 200 to 300 | 148 | +0.0287 ± 0.0085 | +0.0351 ± 0.0097 | 1.04 | 1.35 | 0.791 |
| 300 to 500 | 346 | +0.0191 ± 0.0066 | +0.0208 ± 0.0072 | 1.19 | 1.49 | 0.731 |
| 500 to 1,000 | 461 | +0.0195 ± 0.0056 | +0.0343 ± 0.0068 | 1.18 | 1.54 | 0.712 |
| over 1,000 | 141 | +0.0643 ± 0.0149 | +0.0802 ± 0.0181 | 1.42 | 2.10 | 0.582 |

By size and code:

| group | ads | mean gap | within building | in 80% |
|---|---:|---:|---:|---:|
| under 300, coded | 437 | +0.0008 ± 0.0043 | +0.0068 ± 0.0044 | 0.776 |
| under 300, uncoded | 36 | +0.0415 ± 0.0189 | +0.0417 ± 0.0212 | 0.806 |
| 300 or more, coded | 901 | +0.0249 ± 0.0043 | +0.0345 ± 0.0050 | 0.706 |
| 300 or more, uncoded | 101 | +0.0460 ± 0.0136 | +0.0513 ± 0.0159 | 0.703 |

The gap rises with log2 of the area by +0.0102 ± 0.0023 per doubling over all 1,475 ads,
+0.0107 ± 0.0025 over the coded ads, +0.0031 ± 0.0060 over the uncoded ads and +0.0114 ±
0.0063 over the ads of 300 sq ft or more. Uncoded ads ask +0.0278 ± 0.0124 more than coded
ones, and +0.0212 ± 0.0141 more among ads of 300 sq ft or more.

For comparison:

| group | ads | mean gap | MAD ratio | in 80% |
|---|---:|---:|---:|---:|
| coded, no area | 45,927 | -0.0030 ± 0.0004 | 1.04 | 0.786 |
| uncoded, no area | 141,845 | -0.0053 ± 0.0002 | 0.98 | 0.803 |
| only implausible areas | 311 | -0.0030 ± 0.0027 | 0.80 | 0.820 |
| S16's `outdoor_large` | 684 | +0.0211 ± 0.0048 | 1.42 | 0.714 |
| `outdoor_large`, new area 300 or more | 583 | +0.0240 ± 0.0051 | 1.48 | 0.698 |
| `outdoor_large`, new area under 300 or none | 101 | +0.0041 ± 0.0111 | 0.90 | 0.802 |
| new area 300 or more, not `outdoor_large` | 419 | +0.0311 ± 0.0068 | 1.62 | 0.716 |

The 101 `outdoor_large` ads the new column leaves out ask about what L1 predicts, with a
spread under that of all ads, and the 419 it adds carry the largest excess in the table.

14 of the 1,475 ads come from the development set. Without them the mean gap is +0.0195, the
slope +0.0106 per doubling, and the uncoded and coded means +0.0446 and +0.0170.

## Predictions scored

1. **Precision: hit.** 1.00 (0.83 to 1.00) against 0.90 or more with the lower end above
   0.75, and the same settled.
2. **Level: hit.** +0.0196 against +0.010 to +0.025.
3. **By size: four of six bins.** Under 100 sq ft at -0.0097, just inside -0.010 to +0.010;
   100 to 200 at +0.0070, inside 0 to +0.020; 300 to 500 and 500 to 1,000 at +0.0191 and
   +0.0195, inside +0.012 to +0.030. Two misses: 200 to 300 at +0.0287, over its top of
   +0.020, and over 1,000 at +0.0643, more than twice its top of +0.030.
4. **Slope: miss.** +1.02% ± 0.23% per doubling, 4.4 SE from zero, against -0.3% to +0.5%;
   coded ads alone +1.07% ± 0.25%. I took the flat slope from S7, and it doesn't reproduce
   (next section).
5. **Spread and coverage: half.** The z sd ratio from 300 sq ft up is 1.19, 1.18 and 1.42,
   inside 1.1 to 1.5 and highest there as predicted; below 300 it is 0.95, 1.08 and 1.04,
   under the predicted floor. Coverage from 300 up is 0.731 and 0.712, inside 0.70 to 0.78,
   and 0.582 over 1,000 sq ft, far under it; below 300 it is 0.814, just over 0.80, then 0.752
   and 0.791, inside.
6. **Coded or not: hit.** Uncoded ads at +0.0448 ± 0.0121, at the top of +0.015 to +0.045,
   and +0.0278 ± 0.0124 over coded ads, inside 0 to 3 points, with the SE near 0.01.
7. **A model term: written.** The slope is 1.0% per doubling at 4.4 SE, and the uncoded ads
   differ from the coded by 2.2 SE, so both conditions hold.

## S7's flat slope

S7 reported -0.02 ± 0.16% per doubling over 681 coded held-out ads with a stated size. With
S7's own parse (`out_sqft` in `s7_text.parquet`) on L1's coded held-out ads with a size from
20 to 5,000 sq ft, I get +0.8% per doubling over 994 ads, and I didn't find which of S7's
choices gives 681 ads and a flat slope. The coded ads only S7's parse marks have a mean gap
of +0.0006 and a median size of 100 sq ft.

## S16's outdoor misses

Of S16's 11 overpriced misses read as private outdoor space, the new column gives an area to
3 (516, 1,800 and 700 sq ft), the same 3 S7's parse marked. The other 8 state no area, and 5
of those have no private outdoor code. Most of S16's outdoor misses come from ads with an
outdoor space and no stated size, which belong with the text-columns item in `docs/TODO.md`.

## How much a fit could take back

The screen gives the excess as a mean, but a fit is scored by its predictive density. So
`o6_emulate.py` rescored L1's held-out ads from its 272 kept draws, as S15 and S15b did for
income ads: each marked ad's location moves by a shift, or its noise scale and unit sd grow by
a factor k, and its gain is the change in its log predictive density. I split the buildings
into two halves; each half takes the change picked on the other half's marked ads, and the
SEs are clustered by building.

| change | picked on each half | elpd gain |
|---|---|---:|
| level, least squares | +0.021, +0.028 | -51.9 ± 15.2 |
| level, slope and uncoded, least squares | +0.021 +0.008 +0.022, +0.030 +0.012 +0.026 | -49.1 ± 17.6 |
| level, least squares weighted by 1/s² | +0.015, +0.016 | -14.5 ± 9.7 |
| level, slope and uncoded, weighted | +0.016 +0.005 +0.018, +0.017 +0.005 +0.022 | -8.8 ± 11.2 |
| level, grid | +0.003, +0.005 | +1.9 ± 2.5 |
| level and slope, grid | +0.005 +0.004, +0.010 +0.004 | +3.3 ± 4.9 |
| level, slope and uncoded, grid | 0 +0.002 +0.020, +0.005 +0.002 +0.020 | +6.6 ± 4.2 |
| k on all 1,475 marked ads | 1.45, 1.30 | +38.8 ± 12.1 |
| k on the 1,002 of 300 sq ft or more | 1.60, 1.55 | +57.8 ± 13.7 |
| k on all, after the last grid shift | 1.45, 1.30 | +44.6 ± 13.2 |
| k on 300 or more, after the last grid shift | 1.60, 1.55 | +63.4 ± 14.6 |

Here s is L1's 80% interval width over 2 × 1.2816, the level is at 500 sq ft, the slope is per
doubling, and "grid" means the point of a grid with the largest gain on the picking half.

The least-squares shifts lose because the excess falls mostly on ads with wide intervals. By
quartile of s the marked ads ask +0.007, +0.012, +0.018 and +0.060 over the unmarked ads' mean
gap, and the mean weighted by 1/s² is +0.016 against +0.024 unweighted. L1's predictive has
heavy tails, so a shift sized to the wide ads' gaps costs more on the narrow ads than it wins
on the wide ones. On the grids, the best points put the level near 0.5%, the slope at 0.2% to
0.4% per doubling and the uncoded step at 2 points, and the best spec gains +6.6 ± 4.2, 1.6 SE
from zero. Widening the predictive gains far more: k near 1.6 on ads stating 300 sq ft or
more gives +57.8 ± 13.7, and k near 1.4 on every marked ad, with no threshold, gives +38.8 ±
12.1.

In the emulation I kept the rest of L1's posterior where it is. A fit would also move the
other coefficients, the unit levels and the phase scales, so it would likely take back less
than these figures.

## The term, written and not fit

`rentfrontier.drift_building_phase_outdoorsize` (`drift-building-phase-outdoorsize`) is L1's
design with three ad columns built from `outdoor_sqft`:

- `ad:outdoor_sqft_stated`, 1 where the ad states an area;
- `ad:outdoor_log2_sqft`, log2 of the area over 500 sq ft, the median area, where the ad
  states one, else 0;
- `ad:outdoor_sqft_uncoded`, 1 where the ad states an area and none of L1's private outdoor
  columns is set on the row.

Each column gets its unit mean over the row and its unit's earlier training rows, as L1's
other ad columns do, and the coefficients take the flag prior, Normal(0, 0.5). A coded row
with no stated area keeps the coded columns' premium alone, so the stated indicator plays
the part of the scope note's unknown indicator. Three tests cover the columns, the refusal
of a dataset without `outdoor_sqft`, and the unit means' exclusion of held-out rows. The
module isn't listed in `rentfrontier.run` yet, so a fit needs that line first, then three
H100 containers on the latest split against L1 at about L1's $12.

If it is fit, I expect:

1. the gate to pass on the six new coefficients;
2. `ad:outdoor_sqft_stated` between -0.005 and +0.015, `ad:outdoor_log2_sqft` between +0.001
   and +0.008 per doubling, and `ad:outdoor_sqft_uncoded` between +0.005 and +0.035;
3. held-out elpd against L1 between -10 and +15, within 2 SE of zero;
4. 80% coverage on the 1,475 marked ads still under 0.75, since the term moves the median and
   leaves the interval's width as L1 has it.

## Whether this replaces the unit-flags plan

The scope note of 2026-11-12 (`unit-flags-scope-2026-11-12.md`) planned a Haiku extraction
over about 130,000 ads for `ad:duplex` and `ad:log_private_outdoor_sqft`, with
`ad:private_outdoor_sqft_unknown`, then a dataset build and a fit at about $12 after the
Student-t fit. Its author picked Haiku because the regex patterns of that day matched
building spaces as well as the unit's. For the outdoor half, I separated the two with the
checks above, at a precision of 1.00 (0.83 to 1.00) and no extraction cost, and the dataset
copy is built. The duplex half
went to `rentfrontier.b0duplex` and D1 (`drift-building-phase-duplex`). So this item replaces
the plan's extraction and dataset build. The plan's fit would be the term above, which I
don't recommend fitting on its own (below).

## S16's post hoc figures

- S16 set the 300 sq ft threshold of `outdoor_large` after S7's held-out bins and after
  reading ads picked by their gaps. Its +0.021 ± 0.005, its MAD ratio of 1.42 and its
  coverage of 0.71 on 684 ads describe a group chosen to show an excess, on the same held-out
  ads, so they are post hoc.
- S16's precision of 26 of 30 came from reads of matches drawn after the threshold was set,
  so it isn't post hoc.
- My screen uses the same held-out pool. My level prediction leaned on S16's figure, so its
  hit says little. The slope and the split by code were new looks, and the 40 precision
  reads were fresh ads.
- The emulation's factor on ads of 300 sq ft or more reuses S16's threshold, so its +57.8 is
  post hoc too. The factor on all marked ads uses no threshold.

## Recommendation

- Keep `outdoor_sqft` in the dataset copy, and don't spend a fit on the mean term alone. The
  emulation's best shift gains +6.6 ± 4.2, so a $12 fit would most likely tie L1.
- The excess on these ads is mostly spread. The next outdoor candidate is a factor on the
  noise of rows stating an area, as I1 puts one on income-restricted rows. I'd write it after
  I1's fit shows how a row-level factor behaves in the sampler, and use all rows with an
  area, or a factor rising with log2 of the area, rather than S16's 300 sq ft cut. I haven't
  written that module or tested the rising version.
- Ads with an outdoor space and no stated area, 8 of S16's 11 outdoor misses, go with the
  text-columns item in `docs/TODO.md`.

## Refusals

The worktree's permission check refused six commands. I split each into plain steps:

1. a shell variable holding a path, passed to `python -c`;
2. mkdir, a heredoc, cd and python chained in one command;
3. grep piped through cut and xargs into sed, with a line number computed at run time;
4. a heredoc appending to a scratch script, followed by a run of it;
5. a Python heredoc rewriting `o6_emulate.py` in place; I made the change with file edits;
6. `sed -i` inserting the research-record row from a scratch file; I added it with a file
   edit.
