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
