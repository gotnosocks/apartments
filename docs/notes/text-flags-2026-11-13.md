# Rewritten text flags against L1 (2026-11-13)

The model reads a few flags from each ad's description, set by `b0data` with the patterns of
`features.DESCRIPTION_FLAGS` (copied in `b0data.TEXT_FLAGS`). The reading for the Deals
cautions on 2026-11-10 found two of them poor on the market of 2026-11-09:
`income_restricted` marked 22 income-restricted ads of 55 and quoted a fee schedule in 8 of
its 30 hits, and `shared_space` matched "roommates" in sales talk without finding a single
room in a share. In this screen I rewrite the poor flags as new columns in a copy of L1's
dataset, measure old and new by reading, and check whether the ads they disagree on are ones
L1 misprices. Nothing is fit, and nothing goes to Modal.

L1 is the pool `drift-building-phase-b0-latest-9a7830fb-l1`, fit on the dataset
`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`. Its design takes the five flags of
`b0.FLAGS`. Two of them, `furnished` and `short_term`, come from the ads file and are false
on every row of this dataset. The other three come from the description of each listing's
latest record:

| Flag | Pattern (lowercased text) | Rows marked | L1's coefficient (90%) |
|---|---|---:|---|
| `shared_space` | `shared (?:bath\|kitchen)\|\bsro\b\|roommate` | 30,209 | -0.004 (-0.005 to -0.003) |
| `income_restricted` | `income restrict\|affordable housing\|housing lottery\|\bami\b` | 1,703 | -0.084 (-0.089 to -0.078) |
| `rent_stabilized` | `rent[- ]stabiliz` | 30,179 | -0.002 (-0.004 to -0.001) |

L1 also reads the mean of `rent_stabilized` over a unit's earlier rows
(`umean:flag:rent_stabilized`, -0.022, -0.025 to -0.020). The dataset has 1,896,471 rows, and
1,825,199 of them have a description over 20 characters. The counts and coefficients come from
the dataset's manifest and L1's `result.json` and `posterior.npz`.

## What each flag should mean

I give each flag the meaning its name and its place in the model suggest, and the readers get
these as written rubrics:

- `income_restricted`: the ad offers this apartment under an income-restricted program, such
  as a housing lottery, an AMI band, an HPD or HDC unit, Housing Connect, Mitchell-Lama or a
  421-a affordable unit. A market ad quoting the 40-times-the-rent rule is not one, nor is a
  building's fee schedule for its income-restricted units.
- `shared_space`: the ad offers a room or a bed in a shared apartment or house, an SRO room,
  or a unit whose kitchen or bath is shared with other tenants. A whole apartment pitched as
  good for roommates is not one.
- `rent_stabilized`: the text says this apartment is rent-stabilized. An ad saying the
  apartment is not stabilized, or that only other units of the building are, is not one.

## How I measure

I develop the new patterns on a first sample of read ads. Once they are frozen, I draw a fresh
sample from the listings of L1's dataset with a description, leaving out the ads of the first
sample. For each flag the draw is stratified into the ads both patterns mark, the ads only the
old one marks, the ads only the new one marks, the unmarked ads with a looser candidate word,
and a random draw from the rest. Sonnet or Haiku readers class each ad against the flag's
rubric and quote their evidence. I weight each stratum back to its count among the dataset's
listings, and give precision and recall with Wilson intervals on the effective sample size.
A flag that reading finds good stays as it is, and its old and new columns are the same.

Against L1, I take L1's held-out ads of the latest split and compare their gap from L1's
predictive median across the ads both versions mark, the ads only the old one marks and the
ads only the new one marks, with SEs clustered by building.

## Predictions, written before any ad was read or any pattern was counted

Precision is the share of a flag's ads that the readers class as the flag's meaning. Recall is
the share of the ads the readers class that way which the flag marks. Both are over the
listings of L1's dataset with a description.

1. Old `income_restricted`: precision 0.70 to 0.92 (65%), recall 0.30 to 0.60 (65%). The fee
   schedule of the 2026-11-09 market belongs to recent ads, so over 2013 to 2026 the old
   precision comes out higher than the 22 of 30 found on that market (60%).
2. New `income_restricted`: precision at least 0.90 (70%) and recall at least 0.80 (60%), with
   the recall interval's lower end under 0.70 (65%), since the unmarked strata are large.
3. Old `shared_space`: precision under 0.30 (75%), recall 0.30 to 0.80 (50%).
4. New `shared_space`: precision at least 0.70 (60%), and recall at least the old flag's
   (65%).
5. `rent_stabilized`: precision at least 0.85 (75%) and recall at least 0.75 (65%). Reading
   finds it good enough to keep as it is (55%).
6. Rows changed: the new `income_restricted` differs from the old on 1,000 to 3,000 rows
   (65%), and gains more rows than it loses (85%). The new `shared_space` drops at least 15,000
   of the old flag's 30,209 rows (70%). Over all the rewritten flags, 15,000 to 35,000 rows
   change (60%).
7. On L1's held-out ads, the ads only the new `income_restricted` marks have a mean gap from
   L1's median of -0.03 to -0.12 (65%), more than 2 SE under zero (60%). The ads only the old
   flag marks have a mean gap more than 2 SE above that of the ads both mark (55%).
8. The ads only the old `shared_space` marks have a mean gap within 0.02 of the unmarked ads'
   (75%), since L1 gives the flag -0.004. If the new flag alone marks at least 20 held-out ads,
   their mean gap is at least 0.05 under the unmarked ads' (50%).
9. The comparison says the rewrite could move a fit for `income_restricted` (a gap difference
   over 2 SE for the ads that change) (60%), and could not for `shared_space` (70%).

## The rewritten patterns

The scripts are in `docs/notes/text-flags-2026-11-13/`, run in order, and write to
`/data1/apartments/tmp/text-flags-2026-11-13/`. `t1_texts.py` takes each listing's latest
description as `b0data` picks it. For the development sample, `t2_dev.py` draws ads by which of
several patterns mark them: the old flags, `b0income.INCOME` from the Deals cautions, and
looser candidate words. Sonnet readers took 135 income ads and 130 shared ones, and Haiku
readers took 70 stabilized ones. `t2_dev_labels.py` counts their labels:

- Income: all 50 ads marked by `b0income.INCOME` are income-restricted, and all 20 marked by
  the old flag alone quote a building's fee schedule. Among 65 unmarked ads with a looser
  word, the readers found 6 income-restricted ones.
- Shared: 9 of the 10 ads the old flag marks through "SRO" are shares, as are 7 of 20 through
  a shared bath or kitchen and 1 of 20 through "roommate". Among 80 unmarked ads with a looser
  word, the readers found 6 shares.
- Stabilized: all 30 ads the old flag marks are stabilized, and the readers found 3 among 40
  unmarked ones with a looser word. Most of those 40 matched the word only inside
  "established".

From the readers' quotes I wrote the new patterns in `rentfrontier.b0textflags`. For
`income_restricted_v2` I took `b0income.INCOME` and added HDC, income caps, a table of
maximum incomes by household size and "is an affordable unit"; I also kept the pattern from
reading an agent's surname as "AMI". For `shared_space_v2` I kept "SRO" unless a former SRO
is meant, asked for a bath or kitchen shared with other tenants or down the hall, and added
rooms for rent, roommate matching, room pricing and ads looking for a roommate. I left
`rent_stabilized` as it is. The tests in `frontier/tests/test_b0textflags.py` hold paraphrased
phrases from the ads on each side of each pattern.

## Reading a fresh sample

With the patterns frozen, `t3_eval.py` draws 700 fresh ads with the seed 20261114, leaving out
the development ads, and writes them in batches for the readers: Sonnet for income and shared,
Haiku for stabilized. `common.write_batches` shuffles each flag's draw (`random_state=7`)
before cutting it into batches of 30. The Agent tool first refused the reader of one shared
batch at its limit of 20 subagents running at once. After the first scoring I gave that batch,
from the same frozen draw, to a single Sonnet reader, so every ad of the draw is read. Of the
700, the readers called one unclear. Over both samples the readers took 1,035 ads.

`t4_score.py` counts the labels in each part of the draw. Listings are those of L1's dataset
with a description, outside the development sample:

| Flag | Part of the draw | Listings | Read | Yes |
|---|---|---:|---:|---:|
| `income_restricted` | both mark | 1,542 | 40 | 39 |
| | old only | 115 | 30 | 0 |
| | new only | 1,139 | 60 | 60 |
| | neither, a caution word | 1,025 | 40 | 3 |
| | neither, another candidate word | 1,213 | 40 | 1 |
| | neither, "affordab" only | 9,672 | 40 | 0 |
| | neither, no candidate | 1,810,158 | 20 | 0 |
| `shared_space` | both mark | 250 | 50 | 37 |
| | old only | 29,903 | 100 | 1 |
| | new only | 76 | 50 | 47 |
| | neither, share words or a shared bath or kitchen | 2,891 | 40 | 1 |
| | neither, another candidate word | 2,989 | 40 | 2 |
| | neither, no candidate | 1,788,755 | 19 | 0 |
| `rent_stabilized` | marked | 30,102 | 50 | 50 |
| | unmarked, a "stabilized" word | 1,425 | 50 | 45 |
| | unmarked, regulated, control or RS | 98 | 20 | 2 |
| | unmarked, no candidate | 1,785,692 | 10 | 0 |

Weighted back to the listings, as in "How I measure", with intervals from the delta method
and Wilson's interval on the effective sample size:

| Flag | Version | Listings marked | Precision (95%) | Recall among listings with a mark or a candidate word (95%) | True marks |
|---|---|---:|---|---|---:|
| `income_restricted` | old | 1,657 | 0.907 (0.836 to 0.950) | 0.547 (0.467 to 0.625) | 1,503 |
| | new | 2,681 | 0.986 (0.930 to 0.997) | 0.961 (0.796 to 0.994) | 2,642 |
| `shared_space` | old | 30,153 | 0.016 (0.005 to 0.055) | 0.623 (0.335 to 0.844) | 484 |
| | new | 326 | 0.787 (0.693 to 0.858) | 0.330 (0.183 to 0.520) | 256 |
| `rent_stabilized` | kept | 30,102 | 1.000 (0.929 to 1.000) | 0.959 (0.954 to 0.963) | 30,102 |

For the recall I assume that the listings with no mark and no candidate word, about 1.8
million for each flag, hold no true ads. The readers found none in the 10 or 20 they read there, but so few
reads can't bound a small rate. If 0.1% of those listings were true, the income recall would
come to 0.330 old and 0.580 new, the shared recall to 0.189 and 0.100, and the stabilized
recall to 0.907 (`t4_score.py`). That assumption is also why the stabilized interval is narrow.

The readers' evidence, printed at the end of `t4_score.py`, explains the disagreements:

- None of the 30 income ads marked by the old flag alone is income-restricted. Most of them
  quote a line of a fee schedule, "optional for income restricted units". The
  income ads both versions miss give an income band in words ("no less than $70,000 and no
  more than $240,000") or announce a table of income and household size requirements.
- The 13 shared ads both versions mark but the readers reject are whole apartments, offered
  with a roommate-matching service or as "flexible" bedrooms. The one share among the 100 ads
  of the old flag alone is a house letting its bedrooms one at a time, at $950 and $825 a
  room. Weighted back, that ad stands for about 300 listings, most of the old flag's true
  marks, and it is why the old recall comes out above the new. The new flag also misses a
  co-living building and a list of rooms with their prices.
- 45 of the 50 unmarked ads with a "stabilized" word are stabilized. They misspell it
  ("stablized", "stabalized") or leave out "rent". They stand for about 1,280 listings, the
  4% of recall the pattern misses. The development draw found few of them because its
  candidate word mostly matched "established", and the fresh draw's word leaves that out. I
  chose to keep the flag as it was frozen, and L1 gives it -0.002. That loss of recall argues
  for a rewrite of this flag too.

The new patterns have edges the tests leave open. `t6_checks.py` counts them over every
listing:

- `income_restricted_v2` marks "no income caps" and "no income restrictions", on 41 listings.
  The fresh reading met one of them, in the part both versions mark, and its precision
  counts it.
- `shared_space_v2` marks "converted from an SRO" and "a former single room occupancy". No
  listing of the dataset uses those phrases.
- `shared_space_v2` misses "I'm looking for a roommate" when the apostrophe is curly. No
  listing of the dataset uses it.

A fix would move ads between the parts of the fresh draw, so I list these edges and leave
the patterns as they were read.

## Rows changed

`rentfrontier.b0textflags` wrote the copy
`/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags`,
run in a 3 GB scope. `t5_gap.py` reads it, checks the new columns against `t3_eval.py`'s
matches (they agree on every row) and counts the rows each version marks, over all rows and
over L1's 189,647 held-out ads of the latest split:

| Flag | Old | New | Gained | Lost | Held-out old | Held-out new | Held-out gained | Held-out lost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `income_restricted` | 1,703 | 2,739 | 1,171 | 135 | 207 | 275 | 122 | 54 |
| `shared_space` | 30,209 | 344 | 78 | 29,943 | 2,542 | 33 | 8 | 2,517 |

31,278 rows change at least one flag.

## L1's gaps on the changed ads

For each held-out ad `t5_gap.py` takes the gap of its log ask from L1's predictive median
(`pred_scores.npz` from L1's saved draws). A negative gap means the ad asks less than L1
predicts. SEs are clustered by building:

| Flag | Ads marked by | Ads | Buildings | Mean gap (SE) |
|---|---|---:|---:|---|
| `income_restricted` | both | 153 | 103 | -0.020 (0.013) |
| | old only | 54 | 2 | +0.006 (0.003) |
| | new only | 122 | 67 | -0.107 (0.027) |
| | neither | 189,318 | 36,172 | -0.004 (0.0002) |
| `shared_space` | both | 25 | 20 | -0.043 (0.036) |
| | old only | 2,517 | 1,458 | -0.010 (0.002) |
| | new only | 8 | 5 | -0.107 (0.066) |
| | neither | 187,097 | 35,928 | -0.004 (0.0002) |

The differences between cells, with the SE of each difference clustered by building:

- Income, new only less neither: -0.103 (0.027). New only less both: -0.087 (0.030). Old only
  less both: +0.026 (0.014). Old only less neither: +0.011 (0.002).
- Shared, old only less neither: -0.005 (0.002). New only less neither: -0.103 (0.059). Old
  only less both: +0.033 (0.035). New only less both: -0.064 (0.070).

L1 prices the 122 ads only the new income flag marks about a tenth above their asks. The
readers found all 60 ads of that part they read income-restricted, and `t6_checks.py` finds 8
of those 60 among the 122 held-out ads. The 54 ads L1 reads as income-restricted by the old
flag alone come from two buildings and ask close to L1's median, presumably because L1's
terms for those two buildings make up for the flag's -0.083. An SE from two clusters means
little. The 2,517 ads losing the shared flag ask about 0.005 further under L1's
median than unmarked ads, about the size of L1's coefficient for the flag.

The table at the top of this note gives L1's income coefficient as -0.084 (-0.089 to -0.078),
from a mean of -0.0835 rounded a second time. `t6_checks.py` reads `posterior.npz` again: over
all 10,880 traced draws the coefficient comes to -0.083 (-0.089 to -0.078), and over the 272
kept draws, which L1's predictions use, to -0.083 (-0.089 to -0.077). The coefficients of
`shared_space` and `rent_stabilized` round as in the table over both sets of draws.

## Predictions scored

The predictions above set recall over every listing with a description. I score their recall
parts on recall among listings with a mark or a candidate word, the figure the reading measures.
If 0.1% of the listings with neither were true, the recall part of #2 would miss (0.580).

1. Hit on all three parts: old income precision 0.907, recall 0.547, and over 2013 to 2026 the
   precision comes out above the 22 of 30 (0.73) on the market of 2026-11-09.
2. Hit for precision (0.986) and recall (0.961). Miss on the interval: its lower end is 0.796.
3. Hit on both parts: old shared precision 0.016, recall 0.623.
4. Hit for precision (0.787). Miss on recall: 0.330 against the old flag's 0.623, which rests
   on a single read ad.
5. Hit for precision (1.000) and recall (0.959). The third part is a hit only because I chose
   to keep the flag, and the 4% of recall lost to misspellings argues for rewriting it.
6. Hit on all four parts: income changes on 1,306 rows, gaining 1,171 and losing 135; shared
   drops 29,943 rows; 31,278 rows change in all.
7. Hit for the ads only the new income flag marks: -0.107, 3.9 SE under zero. Miss for the ads
   only the old flag marks: their mean gap is 0.026 above that of the ads both mark, 1.9 SE.
8. Hit on the first part: the old-only shared ads ask 0.005 further under L1's median than
   the unmarked ads. The second
   part doesn't apply, since only 8 held-out ads carry the new flag alone.
9. Hit for income: the new-only ads ask 0.103 further under L1's median than the unmarked
   ads, 3.8 SE. Miss for shared by the rule I wrote: the ads losing the flag ask 0.005 further
   under it than the unmarked, 3.1 SE, though the difference is the size of L1's coefficient.

## A fit to test it

The income rewrite reads better and marks ads L1 overprices. A fit of L1's model on the `-textflags` copy,
reading `income_restricted_v2` in place of `income_restricted` with nothing else changed,
would test it on the latest split by elpd, the median's error and interval coverage. I haven't
written or registered it. The shared rewrite moves 2,525 held-out ads by about L1's coefficient
of 0.004 and adds 8 more, so I would test it in a fit of its own after the income one, if at
all.

## A negation guard and the program's terms (2026-11-14)

This section is a data change made after the scored sections above, and I left their counts
as they were. A rerun of `t5_gap.py` on the rebuilt copy reads the guarded flag, so its counts
for `income_restricted_v2` change by the 41 rows the guard unmarks (10 of them held-out ads),
and it reports those 41 rows as differing from `t3_eval.py`'s flags.

In S15 (`docs/notes/income-flag-2026-11-14.md`) a Sonnet reader found stabilized ads saying
"no income restrictions" among the rows `income_restricted_v2` marked. So
`b0textflags.income_marked` now passes over a match of `INCOME_V2` when "no", "not", "non" or
"without" comes just before it, with at most "a", "an" or "any" between. An ad keeps its mark
through any other match. The pattern itself is unchanged.

The patterns still miss some cases, and I left them as they are. The guard looks only at the
words just before a match, so "no pets or income limits", "not part of the affordable housing
lottery" and "Income restrictions: none" still mark their ads. Among several tiers,
`b0textflags.TIED` misses a unit named with a word between, as in "this 1BR apartment", and
`AMI_PCT` reads "30% of median income" as a tier of 30.

I rebuilt the `-textflags` copy of L1's dataset once with the guard and with four columns read
from the descriptions of the rows the guarded flag marks:

- `ami_pct_text`, the AMI percentage the ad gives its unit;
- `ami_tiers_text`, how many different AMI percentages it states;
- `income_min_text` and `income_max_text`, the household income band it states.

The minimum comes from the rent, so a fit must not read it. I built the new copy beside the old
one, checked with `docs/notes/income-flag-2026-11-14/g1_counts.py` that every other column
was unchanged, and then deleted the old copy and moved the new one into its place.

The guard unmarks 41 rows of 41 listings, 31 training rows and 10 held-out ads, and marks no
new row. 36 of the 41 were marked by the old flag too, so against the old flag the guarded
flag gains 1,166 rows and loses 171. It now marks 2,433 training rows and 265 held-out ads.
A Sonnet reader read all 40 of the unmarked listings that `g1_counts.py` sampled and called
every one of them not income-restricted. Most are stabilized ads saying "no income
restrictions" or "no income cap", and two are HDFC co-ops whose ads say the unit has no
income cap.

| | training rows | held-out ads |
|---|---|---|
| marked | 2,433 | 265 |
| with `ami_pct_text` | 243 (10.0%) | 27 (10.2%) |
| stating any percentage | 261 (10.7%) | 27 (10.2%) |
| stating several, none tied to the unit | 18 | 0 |
| with a minimum or a maximum income | 1,363 (56.0%) | 160 (60.4%) |

The 18 training rows with several tiers are copies of one 266 West 96th Street ad ("70%-130%
AMI"). The tiers of the training rows run from 40 to 250, with 110 the most common (64 rows),
then 130 (42), 165 (28), 125 (24) and 80 (23). The held-out tiers are 90 (1), 100 (3), 110
(10), 125 (2), 130 (5), 165 (4), 180 (1) and 250 (1).

A second Sonnet reader checked 68 listings: 50 drawn from those with a tier and the 18 with
several. It found the tier and the count of tiers right on all 68. It found the income band
right on 42, partly right on one and wrong on 25. The 18 copies of the 266 West 96th ad make
up most of the errors, since they write the band as "$40,526 - $198,250" with no word before
it. The rest are tables that put "(minimum income limit)" after the amount, and ranges with no
"and" or dash between the two amounts. I use only the tier in S15b, and a fit would need the
band patterns fixed before reading the maximum.
