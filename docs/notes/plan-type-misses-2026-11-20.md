# Are new buildings' large units priced by floor plan type? (2026-11-20, no fit)

The open item in `docs/TODO.md` asks about buildings whose new units of two or more
bedrooms miss together on the Deals backtest (The Seren, Lawrence Tower, Union Channel, 420
Carroll, 12 Halsey St). Are those asks set by floor plan type, a line or plan that the lister
prices as a group, in a way the model could learn from fields or ad text without the rent?
And is that general, or only these buildings?

No fit was run, nothing was fetched and nothing was published. Scripts and logs are in
`docs/notes/plan-type-misses-2026-11-20/`.

## Answer

The shared miss is real and general, and it sits at the level of the building and bedroom
count. The unit's line or plan adds little that can be measured beyond that level, and no
trait that readers found in the ads separates the misses on both halves of the buildings.

- In buildings up to three years old, units of two or more bedrooms that are new to training
  share 23% of their held-out gap variance with the building's other new units of the same
  count (sd about 7%). They share nothing with its units of another count. So the model's
  building level is doing its job, and what is missing is a level for the building's units
  of one count.
- Beyond that, the same line shares more only within the error of a small sample (30 pairs
  of new units in the backtest). Once a unit has one training ad the excess of a line is at
  most 0.0007 of variance (sd under 3%).
- The ads of these buildings are mostly one lister's template for the whole building. A
  third say anything about their own unit, none states square feet in the text, and 6%
  name a plan or line. The traits that do vary within a building (private outdoor space,
  penthouse, duplex) are already columns in the model or already screened.
- No new column is proposed. The candidate for the next base refit is the one already
  written and not fit: a level for building and bedroom count (LN1, `drift-building-phase-line`,
  whose line is building, bedrooms and full baths).

## What was already known

`docs/research-record.md` has these earlier results, and none is repeated here.

- Lines of three or more units as a model term (September and October): tied or failed the
  gate, never served.
- The line-level screen of 2026-11-12: on held-out ads, a level for building and bedrooms
  was worth +705.8 elpd (SE 49.3) and for building, bedrooms and full baths +750.0 (SE
  83.1), against +172.3 for the building alone.
- LN1 of 2026-11-13: written, not fit; its GPU rehearsal did not converge (R-hat 1.5115).
- The outdoor sprint's `sib.py`: a building's earlier asks at the same count predict about a
  quarter of the shared gap (slopes 0.29 to 0.39).
- Duplex (S7, D1), penthouse (S14) and outdoor size (`b0outdoorsize`): screened or written.

The served model, `drift-building-bedtext-layout-range`, has no line term
(`docs/model/drift.md`). Its mean is the columns, the market walk, a building level, a unit
level and a building drift. A unit's line enters only when its size is filled from earlier
training rows of the unit or line.

## Data and definitions

| Set | Run | Held-out ads | Buildings |
| --- | --- | ---: | ---: |
| Latest split | `...-b0-latest-c1ffaefd-l2bt` | 189,647 | 36,207 |
| Backtest | `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j` | 9,346 | 4,771 |

The latest-split run in full is
`drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`. Sources: `b1.py`
(`logs/b1.log`) and `b2.py` (`logs/b2.log`).

- The gap is the log ask less the model's median. It is clipped at 0.5 either way before any
  product or mean.
- Buildings are split in two by a hash of the building id (`b1.half`). **Half A was read**
  and any choice of form was made on it. Half B is the check. 420 Carroll falls in half B and
  was read because the item names it, so it and every other read building leave the half B
  checks of the traits (`t1.py`).
- A building is new when its first ad in the data is at most three years before the ad. This
  was fixed before any result was seen.
- The line is the letter or last two digits of the unit label (4B gives B, 412 gives 12), from
  `unit_features`. The plan image is the first floor plan image's hash. Neither uses a rent.
- The latest split holds out each unit's last ad, so **it has no held-out ad of a unit new to
  training**. Units with exactly one training ad stand in for new units there. The backtest
  has 3,168 ads of new units, all priced on one day (2025-11-10).

## Size, with no reading

`s1.py` takes every pair of held-out ads of two units in one building and averages the
product of their gaps, each less its stratum's mean. That average is the variance the pair
shares. Pairs are grouped by whether the two ads have the same bedroom count, the same line
and the same plan image. Standard errors resample buildings 400 times. In the latest split a
pair counts when its two ads are within 365 days.

Backtest, units new to training (`logs/s1_bt.log`). "Excess" is same line (or same plan
image) less other line, among pairs of one bedroom count.

| Stratum | Ads | Bld | Variance | Other count (SE) | Same count (SE) | Share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| New bld, 2+ bed | 431 | 221 | 0.0197 | 0.0004 (0.0007) | 0.0046 (0.0013) | 23% |
| New bld, 2+ bed, half A | 246 | 121 | 0.0174 | -0.0001 (0.0007) | 0.0033 (0.0011) | 19% |
| New bld, 2+ bed, half B | 185 | 100 | 0.0229 | 0.0010 (0.0012) | 0.0074 (0.0027) | 32% |
| New bld, 1 bed | 447 | 157 | 0.0091 | 0.0004 (0.0005) | 0.0017 (0.0007) | 19% |
| New bld, studio | 219 | 87 | 0.0148 | -0.0003 (0.0006) | 0.0037 (0.0009) | 25% |
| Older bld, 2+ bed | 1,072 | 888 | 0.0192 | 0.0035 (0.0014) | 0.0121 (0.0040) | 63% |
| Older bld, 1 bed | 686 | 605 | 0.0109 | 0.0012 (0.0006) | 0.0023 (0.0011) | 21% |
| Older bld, studio | 313 | 270 | 0.0148 | 0.0025 (0.0015) | 0.0108 (0.0047) | 73% |

| Stratum | Other line (SE) | Same line (SE) | Pairs, bld | Line excess (SE) | Plan excess (SE) |
| --- | ---: | ---: | ---: | ---: | ---: |
| New bld, 2+ bed | 0.0038 (0.0011) | 0.0104 (0.0040) | 30, 23 | 0.0067 (0.0040) | 0.0253 (0.0200) |
| New, 2+, half A | 0.0030 (0.0010) | 0.0154 (0.0095) | 11, 9 | 0.0124 (0.0094) | 0.0125 (0.0143) |
| New, 2+, half B | 0.0063 (0.0024) | 0.0069 (0.0023) | 19, 14 | 0.0006 (0.0030) | 0.0395 (0.0471) |
| New bld, 1 bed | 0.0007 (0.0004) | 0.0043 (0.0019) | 70, 28 | 0.0036 (0.0020) | 0.0089 (0.0031) |
| Older, 2+ bed | 0.0133 (0.0047) | 0.0122 (0.0031) | 19, 16 | -0.0011 (0.0042) | 0.0022 (0.0042) |

The plan-image excess for new two-bedroom units rests on 13 pairs in 12 buildings.

For units the backtest has seen in training, the shared variance at the same count is small:
0.0003 (0.0007) in new buildings (197 ads) and 0.0011 (0.0003) in older ones (2,286 ads), with
a line excess of -0.0009 (0.0024) and 0.0021 (0.0007).

Latest split, where every unit has a training ad (`logs/s1_l2.log`). "1 ad" and "2+ ads"
count the unit's training ads, and "New" and "Older" are the building:

| Stratum | Ads | Variance | Same count (SE) | Line excess (SE) | Plan excess (SE) |
| --- | ---: | ---: | ---: | ---: | ---: |
| New, 2+ bed, 1 ad | 8,369 | 0.0079 | 0.0007 (0.0002) | 0.0007 (0.0005) | 0.0022 (0.0007) |
| the same, half A | 4,078 | 0.0084 | 0.0010 (0.0004) | 0.0015 (0.0008) | 0.0027 (0.0012) |
| the same, half B | 4,291 | 0.0073 | 0.0005 (0.0003) | -0.0000 (0.0006) | 0.0018 (0.0010) |
| New, 2+ bed, 2+ ads | 2,581 | 0.0057 | 0.0002 (0.0002) | 0.0000 (0.0003) | 0.0010 (0.0011) |
| New, 1 bed, 1 ad | 5,214 | 0.0055 | 0.0002 (0.0001) | 0.0003 (0.0003) | 0.0008 (0.0005) |
| New, studio, 1 ad | 2,002 | 0.0065 | 0.0006 (0.0002) | 0.0006 (0.0005) | 0.0011 (0.0006) |
| Older, 2+ bed, 1 ad | 27,986 | 0.0086 | 0.0012 (0.0001) | 0.0006 (0.0002) | 0.0008 (0.0005) |
| Older, 2+ bed, 2+ ads | 45,116 | 0.0062 | 0.0006 (0.0000) | 0.0006 (0.0001) | 0.0005 (0.0002) |

What the numbers say:

1. The building level leaves nothing shared across bedroom counts in new buildings (0.0004,
   SE 0.0007). The shared miss is specific to the building's units of one count.
2. That shared part is large for units new to training (0.0046 of 0.0197 in new buildings)
   and nearly gone once the unit has one training ad (0.0007 of 0.0079). The unit level
   carries it from then on.
3. It is not special to new buildings or large units. Older buildings' new units share more
   (0.0121 for two or more bedrooms), and studios and one-bedrooms in new buildings share
   about the same fraction (25% and 19%).
4. The line beyond the count is not shown. In the backtest the excess for new two-bedroom
   units is 0.0067 (SE 0.0040) on 30 pairs, 0.0124 on half A and 0.0006 on half B. In the
   latest split it is 0.0007 (0.0005), again present on half A and absent on half B.
5. The plan image is the one key with a steady excess: 0.0022 (0.0007) in the latest split
   for new two-bedroom units with one training ad, 0.0027 and 0.0018 by half, and 0.0089
   (0.0031) for new one-bedroom units in the backtest. It is a variance of 0.2% against a
   total of 0.8% in the latest split, on 58 buildings. Units that share a plan image mostly
   share full baths too, and the bath excess there is the same size (0.0021, SE 0.0007).

## Reading the ads

`sel.py` chose 31 buildings: the five named ones, and from half A 16 buildings whose new or
once-seen units of two or more bedrooms miss together and 10 whose do not (`logs/sel.log`).
Six Sonnet readers read all 302 held-out ads of those units in full, with every dollar
amount masked and no gap shown, and coded each ad. `r1.py` joins the codes to the gaps
(`logs/r1.log`).

| Finding | Control | Miss | Named |
| --- | ---: | ---: | ---: |
| Buildings | 10 | 16 | 5 |
| Buildings the reader called plan priced | 0 | 3 | 1 |
| Mean share of a building's ads that describe their own unit | 0.34 | 0.43 | 0.35 |

- No ad states square feet in its text (0 of 302). A plan or line is named in 17 ads (5.6%).
- The four buildings called plan priced are Anagram Columbus Circle, West Wharf, Prospect
  House and 12 Halsey St. Their mean gaps are +0.056, +0.159, -0.110 and +0.121, so the
  wording does not give a direction.
- Of the named five: Union Channel's ads are a template with terrace and penthouse
  headlines. Lawrence Tower's are a template. The Seren's and 420 Carroll's are templates
  that differ by bath count, balcony and floor. 12 Halsey St names each home ("Residence
  N") and gives terrace sizes, duplexes and a home office.
- Within a building and count, among the 196 read ads of two or more bedrooms, the ads with
  private outdoor space sit +0.086 (SE 0.021; 24 against 44) above the rest, penthouses
  +0.122 (0.046; 7 against 25) and ads that state a floor +0.122 (0.040; 7 against 38). The
  sd within building and count is 0.075.

These contrasts come from buildings chosen for their misses, so they need the test below.

## The traits on all of history, by half

`t1.py` codes the readers' traits by pattern on every held-out ad, from text and label only,
and adds one more: the ad's text, digits masked, is the same as another held-out ad's of the
building ("template"). "Within" is the gap on the trait with a level for each building and
count; standard errors are clustered by building. Read buildings are left out of half B.

Latest split, ads of two or more bedrooms (`logs/t1_l2.log`):

| Trait | Ads A | Share A | Within A (SE) | Ads B | Share B | Within B (SE) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Private outdoor words | 7,324 | 17.6% | +0.0053 (0.0018) | 7,713 | 18.2% | +0.0026 (0.0019) |
| Penthouse | 1,211 | 2.9% | -0.0009 (0.0045) | 1,176 | 2.8% | +0.0013 (0.0046) |
| Duplex or triplex | 3,481 | 8.4% | -0.0049 (0.0036) | 3,840 | 9.1% | -0.0005 (0.0033) |
| Corner | 1,960 | 4.7% | -0.0006 (0.0028) | 1,799 | 4.3% | +0.0008 (0.0027) |
| Home office or den | 2,823 | 6.8% | +0.0013 (0.0031) | 2,916 | 6.9% | +0.0009 (0.0028) |
| Plan, residence or line named | 931 | 2.2% | +0.0044 (0.0041) | 880 | 2.1% | +0.0003 (0.0045) |
| Template text | 4,931 | 11.8% | +0.0001 (0.0016) | 4,709 | 11.1% | -0.0013 (0.0018) |

Backtest, ads of two or more bedrooms in new buildings (`logs/t1_bt.log`):

| Trait | Ads A | Within A (SE) | Ads B | Within B (SE) |
| --- | ---: | ---: | ---: | ---: |
| Private outdoor words | 112 | +0.033 (0.035) | 102 | +0.047 (0.032) |
| Penthouse | 13 | +0.205 (0.066) | 18 | +0.053 (0.095) |
| Duplex or triplex | 22 | +0.096 (0.033) | 24 | +0.346 (one building) |
| Plan, residence or line named | 30 | -0.064 (0.136) | 25 | +0.028 (0.007) |
| Template text | 132 | +0.010 (0.024) | 102 | -0.040 (0.014) |

The backtest's standard errors rest on very few buildings where the trait varies within a
count, and are too small where only one or two do.

- No trait separates the misses on both halves in the latest split. The largest, private
  outdoor words, is half a percent. The readers' +0.086 for outdoor space and +0.122 for
  penthouses do not recur.
- In the backtest's new buildings the penthouse and duplex ads sit high on both halves, on 13
  to 24 ads a half and a handful of buildings with a contrast. Both are known: the penthouse
  column exists, and the duplex module D1 is written and not fit.
- A named plan carries no gap. It appears in 2% of ads of two or more bedrooms (9% in the
  backtest's new buildings).
- Ads with template text are priced better, not worse: their mean absolute gap is 0.052
  against 0.062 for the rest in the latest split.

Do units with the same template text miss together more than units with two texts, in one
building and count (`t1.py`, last block)? For new buildings' units of two or more bedrooms
with the fewest training ads:

| Set | Same template (SE) | Pairs, bld | Two texts (SE) | Pairs, bld | Difference (SE) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Latest split | 0.0016 (0.0004) | 1,194, 190 | 0.0005 (0.0002) | 4,702, 657 | +0.0011 (0.0004) |
| Backtest | 0.0047 (0.0023) | 225, 32 | 0.0090 (0.0023) | 232, 50 | -0.0044 (0.0028) |

The two sets disagree in sign, so the template is not a key for the shared miss either.

## Candidate for the next base refit

No new column comes out of this. The supported term is a level for each building and
bedroom count, between the building level and the unit level. It needs no coding beyond
fields the model has. The line of LN1 (building, bedrooms, full baths) is the written form;
the plan image could refine it later and is not proposed now.

- Ads carrying it: every ad, and it matters for units with no training ad. In the backtest
  those are 3,168 of 9,346 ads, of which 431 are units of two or more bedrooms in new
  buildings and 1,072 in older ones.
- Expected gain, by arithmetic and not by a fit: the level can only be learned from the
  building's training ads at that count. If it were known exactly, the 23% of variance would
  go and the mean absolute gap of new two-bedroom units in new buildings would fall by about
  12% (the square root of 0.77), from about 0.09 (`logs/t1_bt.log`, all such units) to
  about 0.08. `sib.py` found that earlier asks predict about a quarter of the shared gap,
  which makes the likely gain about 3% of that mean absolute gap, or about 0.003. For
  units with a training ad the gain is near zero.
- LN1's rehearsal did not converge, so under the rules the data and the model come before
  the sampler when it is taken up.

## Not sure of

- Same-line pairs of new units are few (30 in the backtest for new two-bedroom units), so a
  line effect of sd 5% to 8% among new units is not ruled out. It is ruled out at that size
  for units with a training ad.
- The backtest is one day. The buildings picked from it as missing together all miss high.
- The latest split has no units new to training, so its figures are for units seen once.
- Readers saw text only. Floor plan images were used as a key and were not looked at.
- The half B rows of the sizing tables include 420 Carroll (7 ads); the sizing uses no
  reading, so this does not bias it.
- The other half of the TODO item, the 307 open ads on pages whose previous ad has another
  bedroom count, was not done.
