# L2 on the unitkn base: a level for each lease phase (2026-11-14)

This is fit 2 of the causal sprint (`causal-sprint-2026-11-14.md`, account B: the ask is a
move in a search). I wrote the predictions below before launching anything, from L1TKN's saved
held-out predictions and the rehearsal in `unitkn-rehearsals-2026-11-14.md`.

## The change

`drift-building-phase-unitkn-level` takes L1TKN (`drift-building-phase-unitkn`, the sprint's
base, `l1-row-dof-fixed-2026-11-13.md`) and adds the six 0/1 phase columns of
`l2-phase-level-2026-11-13.md` to its design:

    phase:none, phase:0-2, phase:3-9, phase:14-21, phase:22-25, phase:26+

A row's mean gains the coefficient of its phase, with 10-13 months as the reference. A row's
phase comes from the `price_at` dates of its unit's ads, so a held-out row's columns depend
on dates alone. The Student-t unit level at 3 degrees of freedom, the rows' degrees of freedom
held at 2 and the noise factor of each phase stay as L1TKN has them.

## Evidence on the base

I tabulated L1TKN's pool on its 189,647 held-out ads by phase
(`/data1/apartments/tmp/sprint-20261114/l2pre.py`, `l2pre2.py`). The gap is log ask less the
predictive median.

| phase | ads | median gap | less 10-13's | asks under the median | 80% coverage | noise factor |
|---|---|---|---|---|---|---|
| 10-13 | 30,233 | -0.0020 | | 51.6% | 81.3% | 1 |
| 0-2 | 13,725 | -0.0121 | -0.0101 | 62.1% | 76.8% | 1.092 |
| 3-9 | 17,068 | -0.0082 | -0.0062 | 55.8% | 78.8% | 1.589 |
| 14-21 | 25,378 | -0.0053 | -0.0033 | 53.7% | 80.4% | 1.301 |
| 22-25 | 21,507 | -0.0014 | +0.0006 | 51.2% | 81.2% | 1.037 |
| 26+ | 81,736 | -0.0045 | -0.0025 | 52.8% | 79.9% | 1.297 |

L1's table has the same medians within 0.0004, so the heavy-tailed unit level took up none of
the phase pattern. On all ads L1TKN has elpd 236,911, a median error of 0.04020 and an 80%
coverage of 80.0%.

The photo check (`photo-disagreement-2026-11-14.md`) left a lead for this term: the ads with
a low ask by L1's median and a long stay were concentrated in large buildings built after
2000, where asks may open high and step down. A unit relisted within two months is one place
such a step would appear, so after the fit I split the 0-2 gain by building size.

## Launch plan

Three H100 containers, seeds 1 to 3, pooled by `drift_pool` into 6 chains, from
`/data1/apartments/serve/master` at the merge commit of the PR with the module and of this
note. The first container of the commit starts alone, and the other two follow once its log
has passed "synced" and its first sweeps.

```sh
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" --split latest \
  --baseline drift-building-phase-unitkn-b0-latest-79dd65f8-l1tkn COMMIT l2kn-a \
  drift-building-phase-unitkn-level b0 2 500 9000 40 --seed 1 --level-dof 4 \
  --no-loo --no-heldout
```

I score the pool against L1TKN's pool on the shared held-out ads with
`python -m rentfrontier.drift_score`, and count the gain a second time after moving each
pool's predictive by a constant cross-fitted over two halves of the buildings.

L1TKN's three containers settled at $10.82. The six columns join a global block of about
250, so I expect $10.50 to $12.00.

## Predictions (written before launch)

All are for the pool of three containers against L1TKN's pool on the shared held-out ads.

1. The pool passes the gate (70%). The rehearsal on 741 buildings mixed the six phase
   coefficients at R-hat under 1.0025 and ESS above 1,300. If it misses, the miss is on
   `unit_sd`, `tau` or a drift scale (75% given a miss).
2. elpd gains 150 to 350 (60%), more than 2 SE (85%) and more than the sprint's 4 SE bar
   (65%).
3. Counted over a constant shift of each pool, the gain is within 100 of the gain in 2 (70%).
4. At least half the gain comes from the 13,725 held-out ads in phase 0-2 (65%).
5. The posterior median of the 0-2 level, as exp(beta) - 1, falls between -1.5% and -0.5%
   (70%).
6. The other levels: 3-9 between -1.0% and -0.2%, 14-21 between -0.7% and 0.0%, 22-25
   between -0.3% and +0.4%, 26+ between -0.6% and +0.1% (50% for all four together). I make
   no prediction for `none`, since no held-out ad is in it.
7. The median's error moves by under 0.0005 from 0.04020 (80%).
8. 80% coverage on all ads stays within 0.005 of 80.0% (85%). On phase 0-2 it rises from
   76.8% by 0.005 to 0.03 (55%).
9. The share of 0-2 asks under the predictive median falls from 62.1% to between 50% and
   57% (60%).
10. The noise factor of phase 0-2 falls from 1.092 by 0.01 to 0.05 (50%), and each other
    factor moves by under 0.03 (65%).
11. Among held-out ads in phase 0-2, the elpd gain for each ad is larger in buildings with 100
    or more units than in smaller ones (55%).
12. The three containers settle between $10.50 and $12.00 in all (80%).

## Accepting it

By the sprint's rule the term is accepted if the pool passes the gate and gains more than
4 SE, and it is provisional between 2 and 4 SE. A gain under 2 SE closes account B's level
term, and the previous ad's ending is then tested by a free screen before any fit.

## Results

I launched `l2kn-a`, `l2kn-b` and `l2kn-c` from b27d1dd8 and pooled them into
`drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn`, 6 chains of 2,880 draws. The
containers settled at $3.62, $3.81 and $3.63, $11.06 in all, which brings the sprint to
$21.88 of $100.

**Gate: pass.** The highest split R-hat is 1.0050 (`beta[bed=0:full>=2]`) and the lowest bulk
ESS is 1,141 (`unit_sd`).

**Held-out score** on the 189,647 shared ads:

| | L1TKN | L2 on unitkn |
|---|---|---|
| elpd | 236,911 | 237,431 |
| median absolute error | 0.04020 | 0.04005 |
| rmse | 0.0789 | 0.0787 |
| 50% coverage | 51.87% | 51.96% |
| 80% coverage | 80.01% | 80.07% |
| median gap | -0.0050 | -0.0037 |

Both coverage columns come from the saved predictive CDF value of each ad (`l2post.py`).
`drift_score`'s own summary, from sampled intervals, prints 51.84% and 80.01% for L2.

The gain is +520 elpd with an SE of 30 when I cluster the ads by building (28 with ads taken
as independent), about 17 SE. 50.2% of the ads score better under L2. Summed over the ads
scoring better the gain is 3,596, and over the others the loss is 3,076, so the gain is
spread thin over many ads and a few dozen ads do not carry it.

**Counted over a constant shift.** I moved each pool's held-out asks by the median gap of the
other half of the buildings (`pshift.py`) and scored again. L1TKN rises by 640 to 237,551 and
L2 by 360 to 237,791. The gain left between them is +240, clustered SE 28, about 8.5 SE. So
279 of the 520 came from L2 lowering every held-out ad's median by about 0.13%, and 240 from
the differences among phases. Both parts follow from the term. Every held-out ad has an
earlier ad of its unit, since the split holds out the most recent ad of a random set of
relisted units, and four of the five
phases with a previous ad carry a negative level against the 10-13 reference.

**By phase** (gain over L1TKN, the same gain after the shift, and L2's calibration):

| phase | gain | after the shift | median gap | asks under the median | 80% coverage |
|---|---|---|---|---|---|
| 10-13 | -27.9 | +50.6 | -0.0033 | 52.8% | 81.25% |
| 0-2 | +418.6 | +153.2 | -0.0036 | 53.65% | 77.74% |
| 3-9 | +99.9 | +7.2 | -0.0038 | 52.75% | 79.09% |
| 14-21 | +30.6 | -2.3 | -0.0039 | 53.0% | 80.3% |
| 22-25 | -10.2 | +42.4 | -0.0030 | 52.2% | 81.2% |
| 26+ | +8.5 | -10.5 | -0.0042 | 52.6% | 79.85% |

The median gaps, spread from -0.0121 to -0.0014 under L1TKN, now run from -0.0042 to -0.0030.

**Phase levels**, as exp(beta) - 1, posterior median with the 5% and 95% points:

| phase | level |
|---|---|
| none | -0.00% (-0.04, +0.03) |
| 0-2 | -1.09% (-1.13, -1.06) |
| 3-9 | -0.64% (-0.68, -0.60) |
| 14-21 | -0.25% (-0.29, -0.22) |
| 22-25 | +0.03% (-0.01, +0.06) |
| 26+ | -0.16% (-0.20, -0.13) |

A unit back on the market at about one year or about two years asks the same as a first ad.
A unit back within two months asks 1.1% less, and the discount fades through nine months.
This reads as a search: the earlier ad did not rent at its ask, or its lease broke early, and
the landlord comes back lower.

**Noise factors** moved little. Phase 0-2 went from 1.092 to 1.077, and the largest move
among the others is 0.005.

**Building size** (prediction 11, `p11.py`, units from the latest PLUTO release). Among the
0-2 ads the gain for each ad is 0.0274 (SE 0.0040) in the 2,578 ads of buildings with 100 or
more units and 0.0311 (SE 0.0017) in the 11,136 ads of smaller ones. The photo check's lead,
asks stepping down in large new buildings, gets no support from this split.

### Predictions scored

| | prediction | outcome | |
|---|---|---|---|
| 1 | passes the gate (70%) | R-hat 1.0050, ESS 1,141 | hit |
| 2 | gain 150 to 350 (60%) | +520 | miss, above the range |
| 2 | more than 2 SE (85%), more than 4 SE (65%) | 17 SE | hit, hit |
| 3 | shifted gain within 100 of the gain (70%) | 240 against 520 | miss |
| 4 | at least half from phase 0-2 (65%) | 419 of 520; 153 of 240 after the shift | hit |
| 5 | 0-2 level between -1.5% and -0.5% (70%) | -1.09% | hit |
| 6 | the four other levels in range (50%) | -0.64%, -0.25%, +0.03%, -0.16% | hit |
| 7 | median error moves under 0.0005 (80%) | 0.00015 | hit |
| 8 | 80% coverage within 0.005 of 80.0% (85%) | 80.07% | hit |
| 8 | 0-2 coverage rises 0.005 to 0.03 (55%) | 76.8% to 77.7% | hit |
| 9 | 0-2 asks under the median fall to 50% to 57% (60%) | 53.65% | hit |
| 10 | 0-2 factor falls 0.01 to 0.05 (50%) | 0.014 | hit |
| 10 | other factors move under 0.03 (65%) | at most 0.005 | hit |
| 11 | larger gain per 0-2 ad in buildings of 100+ units (55%) | 0.0274 against 0.0311 | miss |
| 12 | cost $10.50 to $12.00 (80%) | $11.06 | hit |

Twelve of the fifteen parts hit. I set the range in 2 from the gaps between phases and left
out the level common to every ad with a previous ad, which is the same omission behind the
miss on 3.

### Reading

The term is accepted: the pool passes the gate, the gain is over 4 SE with and without the
constant shift, and it is spread over the ads. L2 on unitkn is the base for the sprint's later
fits.

Leads from this fit:

- The held-out asks still fall 0.37% under L2's median in every phase, worth 360 elpd as a
  constant. By ad date the gap is widest from April 2021 to March 2024 (-0.8%) and near
  -0.2% in the latest eighth of the ads. Since each held-out ad is the most recent ad of its unit, the
  remaining gap may come from the way a listing ends (a final cut before it rents) or from
  the unit's drift. The previous ad's ending and the price history within an ad are the
  screens to run on it, on L2's saved predictions, at no cost.
- Coverage in phase 0-2 is still 77.7% at 80%, so the spread of quick relists is wider than
  their factor of 1.08 gives.
- `drift_today` refuses a Student-t unit level, so neither L1TKN nor this model can publish
  Price now or Deals until that code handles it.
