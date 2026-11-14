# H1 as an optional recode of studio-coded rows (2026-11-14)

S17 (`studio-rooms-2026-11-14.md`) recommended rule H1. It marks a row coded as a studio on a
unit of 5 or more coded rooms when the unit's page also has an ad coded 1 bedroom or more
within 730 days. S17 proposed an exclusion. The coordinator asked for a recode instead,
because 243 rows are too few to justify a fit of their own, and an exclusion would take 24
held-out ads out of the comparison. I wrote it as `rentfrontier.b0studiohistory`, under the
rule name `studio-history-h1`. Nothing was fit, and nothing went to Modal.

## The rule

For each studio-coded row with 5 to 20 coded rooms, I collect the other ads of its unit page
coded 1 bedroom or more and put on the market within 730 days of the row's ad, before or
after it. The ads come from the ads file of the dataset's pipeline build, and the rooms from
the listing-codes file. I read coded fields only, with no ad text.

1. I give the row the bedroom count of the ad nearest to it in time.
2. When several ads lie at that nearest distance and give different counts, the row stays a
   studio. No row of L1's dataset ends that way.
3. I ignore farther ads. S17 had preferred an exclusion because unit histories disagree on
   the count, but with the nearest ad taken, every disagreement on L1's dataset settles. Of
   the recoded rows, 28 have ads that disagree, and I count them in the manifest entry as
   `ads_disagree`.
4. For a row held out by the latest split, I use only ads put on the market before the row's
   ad. `docs/leak-free-scoring.md` lets a held-out row's covariates read its unit's earlier
   listings, because those are known when it is listed. F1 was withdrawn for reading whether
   a unit gets listed again, which nobody could know when the ad went up. A later ad's bedroom
   count is the same kind of look-ahead, so a held-out row with no earlier ad stays a studio.
   I let training rows use ads on both sides, since the leak in that document involves rents
   only and the recode reads bedroom counts.

The recode changes `bedrooms` only. Rows keep their `unit_id`, and the latest split ignores
bedrooms, so it draws the same held-out rows before and after.

## Off by default

The rule is off until someone writes a dataset copy with it. `recode` returns its frame
unchanged unless it is given `rule="studio-history-h1"`, and the command writes a copy only
when it is given `--out`. I wrote no copy, so the datasets of served and selected fits are as
they were.

I kept the rule out of `pipeline/ledger`, the folder of B2's file. Every file in that folder
goes into the next pipeline build, with no switch to leave one out. The pipeline also lacks
the room counts and the latest split.

The plan is to let the rule ride along with the next data-version change that gets a fit
anyway, as one more step after that version's other copies. It gets no fit of its own.

## Counts on L1's dataset

I ran `python -m rentfrontier.b0studiohistory` on
`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise` under a 3 GB memory scope. Units are
counted as S17 counted them, by building and the dataset's `unit_id`.

| rows | S17 | the rule |
|---|---|---|
| marked | 243 | 243 |
| marked, held out | 24 | 24 |
| units | 228 | 228 |
| buildings | 161 | 161 |

Of the 243 marked rows:

- 231 are recoded, 219 in training and 12 held out, in 218 units and 155 buildings. They
  become 1 bedroom on 82 rows, 2 on 82, 3 on 48, 4 on 15 and 5 on 4.
- 12 held-out rows stay studios, since their only evidence ads came later. They are in 12
  units and 10 buildings.
- No row stays a studio through a tie.

## Caveats

- **H1 is post hoc.** S17 chose it after scoring 9 rules on the same 70 held-out ads, so the
  24 held-out ads it marks are no fresh test. When the rule rides along with a data version,
  any gain on those ads should be read with that selection in mind.
- **Split units.** The pipeline cuts a unit page's history at each change of bedroom count
  (`unit-splits-v4`). In L1's dataset 230 marked rows have evidence ads that are also rows,
  and for 224 of them every such ad carries another `unit_id`. The recode leaves those pieces
  apart, so a recoded row keeps a unit effect separate from the history of its 1+ bedroom
  ads. Ledger sets with `other_ad` evidence would rejoin the pieces at the pipeline, but every
  build would then include them, and held-out rows would need a separate answer.
- **Rooms above 20.** With no upper bound, H1 would mark 4 more rows in 4 buildings, none held
  out. S16 and S17 treated those room counts as feed errors, so the rule leaves them out.

## Refusals

The permission check refused two Bash commands, and I split each into plain steps:

1. a heredoc writing a script and then running it after `cd`, as too complex to verify;
2. a `systemd-run` line with `PYTHONPATH=$PWD/src`, because a value was computed at runtime.
   From then on I used absolute paths.
