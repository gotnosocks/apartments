# Project to-do list

Open items for the current model (`drift-building`, see [model/drift.md](model/drift.md)) and the
Deals page, and two data items from October. The aim is in the root [README](../README.md). The list as it stood before 2026-11-10,
with the Chelsea pilot's and the frontier line's items, is in
[archive/TODO-2026-10.md](archive/TODO-2026-10.md).

**From the outlier sprint of 2026-11-11** (`docs/notes/outlier-sprint-2026-11-11.md`). Ben
ruled out Modal fits for the rest of the sprint, so these wait for after it.

- [ ] c3: the narrowed closing dataset (`rentfrontier.b0closingraise`, 59,026 rows repriced:
  raises typed as the ad closed) fitted with b9's design, three containers of 2 chains,
  seeds 11 to 13. Its 7 predictions are in `docs/notes/closing-asks-2026-11-11.md`. It takes
  the place of c2, the fit of the full closing rewrite: the second look found support for
  the rewrite in the closing raises alone. The unit `outlier-c2` and its script
  `/data1/apartments/tmp/outlier-sprint/c2/run.sh` are stopped and stay stopped.
- [ ] The wider income flag (`rentfrontier.b0income`), on the dataset c3's comparison picks.
  Predictions are in `docs/notes/income-flag-2026-11-11.md`.
- [ ] A term for the 2020 and 2021 gap between buildings with concessions and buildings
  without. In the buildings the closing rewrite left alone, c1 lost 205.7 elpd to b9, 175
  of it in 2020 to 2022 and 159 of that on ads with no concession in their record or text,
  most per ad in buildings with few training rows
  (`docs/notes/closing-asks-2026-11-11.md`). Needs a note with predictions.
- [ ] Gate fits run 6 chains (three containers of 2). c1's 4 chains missed the gate by what
  reads as a tail event, with a chance of 2.1% to 2.8% at b9's mixing, against 0.55% to 0.74% for 6
  chains (`docs/notes/closing-asks-2026-11-11.md`, "The gate miss, second look"). The
  reparameterization of `drift_tau`, `unit_sd` and `drift_sd` proposed earlier is
  withdrawn: the scale step already slices along their ridge.
- [ ] Sampler candidate: a second pass of steps 6, 7 and 3 (unit levels, noise with the
  mixing scales, the scale step) within each sweep. The ridge of the unit scales is
  unrelated to the coefficients, the trend and the buildings, so two passes should act on
  it like two sweeps. Predicted: the ridge's autocorrelation time falls from 15.5 sweeps
  to between 7 and 10. Run a timing pilot on thelio's GPU first (b9's sweep takes 0.64 s),
  and go on to a full fit only if the ridge's effective draws per second rise by at least
  about 20%.
- [ ] Stabilized units following a share of their area's path. The stabilized flag's gap
  runs -0.011, +0.010, +0.004 and -0.023 in 2019 to 2022 and -0.010 to -0.017 since, which
  fits a stabilized rent moving by the Rent Guidelines Board's increase while the market
  fell and recovered (the sprint note, "Residuals by text flag"). The term is a coefficient on the
  area path for flagged rows. Predicted: the coefficient lies between 0.3 and 0.7, the
  yearly gaps of flagged ads fall inside ±0.006, and elpd gains 20 to 80 on the latest
  split. Needs a note. The DHCR building lists are a source for the flag apart from ad
  text and should be joined first.
- [ ] A noise factor for units with no earlier ad, built only from what is known when the
  ad opens. It takes the place of F1, withdrawn for reading whether the unit is listed
  again (`docs/notes/first-ad-split-2026-11-12.md`). Single-ad units hold the tails of
  L1's "none" phase (0.82% of rows beyond 6 robust scales, against 0.31%). Candidate
  inputs, each as of the ad's first day:
  - the unit label failing the label standard of the outlier sprint: absent from the
    lot's city records, off the building's grid of floors and lines
  - the lister's reposting so far
  - the building's ad history so far, such as its count of earlier ads
  Needs a note with predictions, and a check that each input reads no later ad.
  Outcome of the free check, 2026-11-20 (`docs/notes/first-ad-noise-inputs-2026-11-20.md`):
  the latest split holds no first-ad units, so the test ran on the 2025-11-10 backtest. The
  label standard and the lister's totals do not mark the wide asks. A first ad whose lister
  closed no ad of the same counts under another label in the building in the prior 30 days
  needs a scale factor of 1.23 and 1.32 on the two halves, the other first ads 0.99 and
  0.91. Review showed the mark is largely thin history of the building at that bedroom
  count: among those ads the factor runs from 1.52 and 1.65 with no earlier same-bedroom ad
  in the building to 1.10 and 1.10 with 20 or more, and forms with no lister in them gain
  as much. That is the gap LN1 (the level for building and bedroom count,
  `docs/notes/plan-type-misses-2026-11-20.md`) addresses. Still to do, in order: fit LN1
  with a market backtest; tabulate the factor of first ads by same-bedroom history under
  it; a factor by thin same-bedroom history only if one is still needed; the lister form
  after that. The evidence is one backtest day with every form seen on both halves, so it
  is suggestive and a second backtest day is wanted.
- [x] A renovation step dated from the unit's own ads: a column set from the first ad of a
  unit whose text says renovated or gut renovated when an earlier ad of the unit lacked the
  words. Ads switching the words on sit +0.009 to +0.012 over the model, and ads dropping
  them sit at zero, so the step stays once taken. Predicted: a coefficient of +0.005 to
  +0.010 and an elpd gain under 40. DOB alteration filings by BIN can date the work without
  the ad text, and photos can confirm it. Sized on stored l2bt predictions on 2026-11-21
  (`docs/notes/renovation-step-2026-11-21.md`, no fit): the words flicker, a lasting step
  carries +0.003 (+48, SE 12), and the gain is in the first worded ad. That ad's wider scale
  belongs to any rewritten description, so two terms go to the base refit's list in its
  place (below). DOB filings stay untested.
- [x] Text columns where the lister left the coded field empty: private outdoor space (+0.0154
  where the field is false), penthouse (+0.0058), dishwasher (+0.0064), furnished (8,064
  held-out ads say it, no training row has the coded field) and full floor (no column,
  +0.0124 within building). Each is a fit of its own. Predicted for each: a coefficient
  between half and the whole of the figure given here, and an elpd gain under 30. For
  private outdoor space, the outdoor-size item of 2026-11-14 covers only the ads that state
  an area: 136 uncoded held-out ads at +0.045 ± 0.012, which
  `drift-building-phase-outdoorsize` marks with a column of their own. 8 of S16's 11 outdoor
  misses state no area, so the text column is still needed
  (`docs/notes/outdoor-size-2026-11-14.md`). Rescored on L1's draws, that term's best shift
  gains +6.6 ± 4.2 and a noise factor on the rows with an area +31.1 ± 10.0, so the note
  recommends writing the factor after I1's fit instead of fitting the term. Sized on stored
  l2bt predictions beside the queued base-refit terms on 2026-11-21
  (`docs/notes/text-columns-2026-11-21.md`, no fit): none is worth 2 SE alone and the five
  together gain +33 (SE 14); 72 low-tail ads leave and 72 join (about 1% each). Dishwasher,
  furnished and full floor leave the queue. Outdoor space with the box unchecked (+16, SE
  10) and penthouse (+8, SE 5) clear 1.5 SE (a cutoff chosen after the run) and go to the
  base refit's list as optional terms.
- [ ] Free months parsed from ad text as an added column for the 5,502 held-out ads (and
  their training counterparts) with a concession in the text and none in the record. The
  ask stays as recorded: in most of these ads the lister typed the net rent as the price.
  Predicted: the group's mean gap moves from -0.011 to within ±0.004. This widens the
  parsing item under the Deals list. The wording is on about 120,000 training rows with
  no recorded free months, 94,867 of them through 2019 (11.9% of those rows) and 25,230
  in 2020 (12.3%), and on 586 to 1,549 rows a year since 2021. The column therefore acts
  on the years before listers used the structured field and hardly on current ads.
  Since 2026-11-13 the column exists as `months_free_text` in the `-freetext` copy of L1's
  dataset (the parsing item below). No fit reads it yet, so the prediction is untested.
- [x] Diagnostics: take each held-out ad's previous ask from the same build and the same
  model unit as the fit. `prev_ask` in `site/diagnostics/ads.parquet` comes from the market
  build's history, which crosses the pieces of an apartment: in 40% of the ads whose
  adjusted previous ask sits over 0.3 above the model it belongs to another configuration,
  and of 79 market ads checked, 38 had their previous ad under another unit id in the other
  build and 28 had none in the market build. Done 2026-11-20 in code
  (`drift_diagnostics.previous`): each row reads the dataset of the fit that scored it, by
  the model's unit, from training ads dated strictly earlier. Rebuilt on the 2026-11-09
  runs, 7,540 of 195,423 rows change `prev_ask` or `prev_day` (7,385 had read another
  piece, 934 a held-out ad, 162 an ad of the same day). The published folder is unchanged
  until the next `publish`.
- [x] Deals: the previous-ask ring reads `diagnostics/ads.parquet` by listing id, so it
  comes from the diagnostics fits (2026-11-09), not the fit Deals publishes, and 2,462 of
  6,502 live deals have no diagnostics row. Republish diagnostics from the Deals fit's
  pair of runs, or give `deals.json` its own previous ad from `drift_diagnostics.previous`.
  Done 2026-11-20 in code: `drift_deals.deals` gives each deal `prev_ask` and `prev_day`
  from `drift_diagnostics.previous` on the run's own rows and held-out mask, and the page
  draws the ring from them (an older `deals.json` still reads the diagnostics). A dry run
  on the live run gives 4,380 of the 6,502 deals a ring, against 2,805 now: 1,575 gain one,
  none lose one, and 3 of the 2,805 move. Every other field of `deals.json` is the same.
  The live page is unchanged until the next `publish`.
- [ ] Size-fill order, for the next base refit (read done 2026-11-20, no fit:
  `docs/notes/size-fills-read-2026-11-20.md`). The blanking rule proposed by the outlier
  sprint is rejected in two of its three clauses. Line fills more than 20% to 60% over the
  bedroom median still describe the apartment better than the median a blank gives: on the
  later check, the only evidence on the rows the rule blanks (628 of the 3,669 line fills
  over 40%), rmse 0.31 and 0.18 by half against 0.42 and 0.43, a thin margin on half A. No
  fill of the as-of design crosses pieces of an apartment. The supported rule is an order
  of layers in `sizefill.asof_size` as `building_zones_floor_asof.size_table` calls it: (1)
  the piece's earlier training ads with the row's bedroom count, (2) the line layer, (3) the
  piece's earlier training ads with another bedroom count. On the later check, fills are off
  by more than 30% in 6.3% of same-bedroom unit fills, 25.5% of other-bedroom unit fills and
  6.5% of line fills; the own check gives 1.6%, 22.2% and 3.3%, lower because 74% and 46%
  of its same-bedroom and line checks are exact copies of an earlier stated size. On rows
  with both, the line fill beats the other-bedroom unit fill on both checks. It changes the size of 1,830 rows (1,474 training, 356 held-out) and blanks none. The
  change makes the served fit unservable until a refit, so it goes in with the refit.
- [ ] Refit term candidate: a slope of its own for filled sizes (`unit:size_imputed` times
  `unit:log_size_rel`). Held-out ads with a filled size over 1.4 times the bedroom median
  are 12% to 21% below the 5% point against 10% to 12% for stated sizes, about twice the
  share, and predicted rent does not explain it (stated sizes reweighted to the fills' mix
  of predicted rent are 9.0% and 9.8% low). The checked size has a slope of 0.8 on the
  filled one on the later check (same note). One change per fit.
- [ ] For Modeling: extend `label_key` in `pipeline/models/analysis/label_units.py` to
  labels with "apt" or "unit" typed after or inside the unit ("garden-apt", "3apt",
  "5c-unit") and to penthouse labels with a leading zero ("0phb"). Of 19,481 page pairs
  with variant labels, 93.7% are joined already; these two cases cover most of the 280
  unjoined pairs with fit rows on both pages
  (`/data1/apartments/tmp/outlier-sprint/s2/F3/results.md`).
- [ ] For Modeling: have the history layer of `analysis.label_units` join two pages only
  when their labels agree up to spelling. It joins pages through StreetEasy's page history,
  which follows a property id, and brokers move a property record from one apartment to
  the next (Riverbank 9H to 20H, 452 Amsterdam Ave 4S to 2N). 14 of 19 history-layer units
  read held two apartments, about 234 of the 317
  (`/data1/apartments/tmp/outlier-sprint/s2/E/results.md`). The 15 `split_unit` entries of
  2026-11-12 repair single pages until the next ad arrives on them. The rule is now
  `unit-labels-v18`, an option of the model behind `PIPELINE_LABEL_RULE`, with v17 still the
  default. On L1's build it splits 709 of the 750 pairs v17's history layer joins, and Sonnet
  read about 80% of the splits as right, 69% to 88% at 95% (59% outside 175 Spencer Street).
  947 of L1's rows change unit, in the copy `...-closingraise-labeljoin`
  (`docs/notes/label-join-2026-11-13.md`). Next: a fit on the copy with `--split carried`, a
  build under v18 for the 120 rows the label-month check restores, and a containment rule
  ("D" and "6D"). The v18 build goes in a lane with its own `--state` and `--out`
  (`ops/pipeline/build.py`): `rentfrontier.b0data` takes the newest catalog line, so a v18
  build in the shared folders would feed the next dataset. The dataset manifests from
  `ops/pipeline/observations.py` and `rentfrontier.b0data` record the build's `label_rule`
  beside its `stale_days`, so a v18 dataset shows its rule.
- [ ] For Data improvements: a pipeline rule for ads posted with a blank form. Real Street
  Inc, M1 Ventures and Stuyvesant Heights Realty Corp post ads with the form's fields
  empty, and the feed codes them as 0 bedrooms, 1 bath and 1 room. The marks are a
  description of one to three characters or "Draft" for Real Street, "Draft rental
  description" for Stuyvesant Heights and legal boilerplate alone for M1, with 0 bedrooms,
  1 bath and 1 room coded. The ledger of 2026-11-12 decides the kept ads of this kind by
  hand (768 of Real Street and M1, then 264 of Stuyvesant Heights and Real Street; a few
  take their building's count and the rest are excluded as `bedrooms_unknown`). The rule
  would treat the coded count of such an ad as missing when the ad arrives, so new ones
  need no ledger entry. The screen of the other listers is in
  `docs/notes/outlier-sprint-2026-11-11.md` under "Ads coded 0 bedrooms across all
  listers": the rule has to be written per lister, since about two thirds of all blank ads
  coded 0 are real studios. Constantinos Kaimakliotis, Capital Ventures Group, Skyhigh
  Realty and PadRabbit have low studio shares on few ads and need a read before they join
  the list.
- [ ] Blank ads coded 0 with no evidence on their page. 8,923 blank ads have no counted ad
  on their unit page within two years, and the mixture reading puts a quarter to a third of
  the blank class at 1 bedroom or more. A floor plan or photo count per ad would decide them, and no cheaper
  evidence exists in the records. Real Street's 20 blank ads with 2 rooms are among them.
- [ ] Studio-coded ads on units of 5 or more coded rooms (S16, S17,
  `docs/notes/studio-rooms-2026-11-14.md`). S16 chose this split after its reads, so its
  figures are post hoc. S17 read 30 of the 893 rows outside S16's draw without plan
  fetches: 8 have bedrooms, 9 are studios, 3 are commercial space and 10 stay unresolved.
  Weighted to the 893, .35 ± .14 have bedrooms (.59 ± .12 of settled rows) and .42 ± .13
  stay unresolved; none of 8 at 8 to 20 rooms has bedrooms. S17's rule H1 marks the 243
  rows whose unit has an ad coded 1 bedroom or more within 730 days. It marks 24 held-out
  ads, and the 20 of them outside S16's draw ask 0.14 ± 0.07 more than the other 50, which
  still ask +0.045 ± 0.025. S17 picked H1 after scoring 9 rules on those 70 ads, so that
  contrast is post hoc too. H1 is now written as an optional recode, off by default
  (`rentfrontier.b0studiohistory`, `docs/notes/studio-history-rule-2026-11-14.md`): it gives
  227 of the rows the bedroom count of the nearest such ad, earlier ads only for held-out
  rows, and keeps a studio when that count reaches the row's rooms. Next: add it as a step
  to the next data-version change that gets a fit anyway, and judge the gain on its 11
  recoded held-out ads with the selection in mind. Some unit pages mix apartments; if that
  fit's recoded rows miss, S17's H2 (rooms within 1) is the stricter variant. The
  nonresidential check (`docs/notes/nonresidential-2026-11-14.md`) counts all 3 of S17's
  commercial reads among its candidates and writes no rule. It didn't split by room count,
  so a screen of nonresidential ads at 8 or more rooms is still open.
- [x] Screen The Rheingold (10 Monteith St) and buildings like it, where brokers post ads
  for any unit of the building under arbitrary unit pages. Done 2026-11-21
  (`docs/notes/any-unit-pages-2026-11-21.md`): a text mark ("any unit in the building", 923
  and 722 pages by half) and an overlap mark (asks more than 10% apart running 4 or more days
  at once, 1,177 and 1,236 pages) mark 4,010 pages. Blind reads find several apartments on
  13 of 40 marked pages (0.33, 0.20 to 0.48) against 4 of 20 unmarked pages in the same
  buildings. Held-out ads on marked pages show no level gap; coverage falls 4 to 5 points
  and the low tail rises 1 to 3 points on both halves. 42 of 6,502 Deals ads are marked,
  none in the top 100. No rule and no caution (thresholds set post hoc); the overlap mark reads asks, so it
  may screen or caution and may not carry a data rule. Open: a noise scale on the overlap
  mark, built for each ad from the page's ads that started earlier, read as of its first
  day with its own ask left out, listed in `READS_EARLIER_RENTS` and scored on the latest
  split; and a hand `split_unit` read of The Rheingold's pages.
- [ ] L1: a noise scale by lease phase, a factor on the ad-level scale per group of months
  since the opening of the unit's previous ad (none, under 3, 3 to 9, 10 to 13, 14 to 21,
  22 to 25, 26 or more). The served intervals cover 0.752 of held-out asks at 3 to 9
  months against 0.841 at 10 to 13, and the model's width runs the other way. Predictions
  and the free checks are in the sprint note ("The lease cycle"; elpd +400 to +900).
- [ ] Y1: a noise scale by calendar year. Coverage is 0.745 for held-out ads of 2020 to
  2022 and 0.826 before and after; current intervals are 7% to 9% too wide by the free
  check. Predictions are in the sprint note (elpd +600 to +1,300). Training rows scored
  as held-out ads show the same spread in 2020 and 2021 (sets B and C of
  `/data1/apartments/tmp/outlier-sprint/s2/Y/`), so the factors do not come from the
  split's choice of units.
- [ ] L2: a level per lease phase on L1's winner (apartments back within 3 months come
  1.4% under the median). Behind it, the previous ad's ending (delisted or paused against a
  deal), now the column `prev_ending` in a copy of L1's dataset
  (`docs/notes/ending-column-2026-11-13.md`). No model reads it yet.
- [ ] R, for Data improvements and Modeling: make the label standard for reposts a
  pipeline step, then collapse the certified chains in the dataset build. The standard
  joins a handoff (same lister, building and counts, the later ad opening 0 or 1 day
  after the earlier ad's last day) when one of its labels is absent from the lot's city
  records and off the building's grid of floors and lines, on lots with adequate
  records. It certified 19,787 joins (`/data1/apartments/tmp/outlier-sprint/s2/G/code/std.py`,
  account in the sprint note under "Reposts under a new label"). The step needs the
  apartment numbers of HPD complaints and violations, marshals' evictions and condo unit
  lots fetched for every lot, on the schedule of the city fetch. `rentfrontier.b0chains`
  then drops 18,208 rows and 16,787 unit ids. Predictions are in the sprint note: no
  change in held-out scores beyond 2 SE, so no fit of its own.
- [ ] Reposts the standard leaves undecided: 23,931 kept links are on lots with thin city
  records, and 16,413 of them have a label with a line on no other floor. A further
  record of real apartment labels (DOB certificates of occupancy, rent registration
  counts by apartment, ACRIS unit lots) would decide part of them. Photos, text and
  timing do not count as evidence of identity.
- [ ] U1: a unit scale growing with size. The sd of a unit's lasting level and of its
  drift are multiplied by `exp(gamma * max(0, log(sqft / 1000)))`. Over 1,500 sq ft the
  80% interval covers 0.69, and the gap keeps 49% of the previous ask's deviation. The
  attributes the ads record explain 9% to 16% of that persistent variance (sprint note,
  "Observed attributes of large units"), so the scale comes first. The mean already
  reads the unit's size (`unit:log_size_rel`), and the scales read none, so the size goes
  to the sampler's unit steps through a module of its own. Predictions are in the sprint
  note (`gamma` 0.3 to 0.6, elpd +150 to +500). U4 runs ahead of it.
- [ ] U4: a unit scale by bedroom count, a factor on the sd of a unit's lasting level for
  2 bedrooms and for 3 or more. For units with no ad in training the 80% interval covers
  0.733, 0.693 and 0.663 of final asks at 2, 3 and 4 or more bedrooms in the backtest j9
  against 0.818 for 1-bedrooms, and 2,244 of those 2,845 ads state no size, so a scale
  on size alone leaves them where they are. Predictions are in the sprint note (factors
  1.2 to 1.6 and 1.4 to 2.0, new-unit coverage for 2 or more bedrooms from 0.72 to
  between 0.76 and 0.80, elpd +100 to +500).
- [ ] U3: a building-level term for large units, on U1's winner. Either a coefficient per
  building on `max(0, log(sqft / 1000))`, or a level per building for its apartments of
  2 or more bedrooms. Different large units of one building share 25% of the persistent
  covariance (15% to 37%), against 4.2% for the building attributes on record. New
  2-or-more-bedroom units of a building have a pair covariance of 0.0082 in their gaps
  (half their variance) against 0.0013 with the building's smaller new units, and the
  building's earlier asks for the count predict a quarter of it (sprint note, "Units
  with no ad in training").
- [ ] U2: a Student-t distribution for the unit's lasting level, on U1's winner. Predicted
  to close with over 8 degrees of freedom and under 100 elpd.
- [ ] Photos of the 1,411 large held-out ads above the 95% point, on Haiku readers, only if
  the finish term among the base-refit terms leaves the high tail as it is. The text of large
  ads covers the second level (duplex, queued), the full floor and renovation (no excess in
  either tail), and the low tail's images were read on Nov 18
  (`docs/notes/large-unit-text-2026-11-21.md`).
- [ ] Backtests on 2024-11-10 and 2025-05-10, each a fit of the served design with the
  day's open ads held out. The served median is 0.47% above the held-out asks of the
  latest split, and in 2022 and 2023 most of that comes with the split: a unit's last ad is an ask low
  against its history, more so in 2022 and 2023 (sprint note, "The level of the held-out
  gap"). The single backtest j9 has +0.3% for open ads of units with history, +0.9% for
  new units and +4% in buildings new to training. The two further days would say whether
  those levels hold. Predictions are in the sprint note. Until then, read an elpd gain
  from a lower level on the latest split against a backtest before taking it as a better
  median.
- [ ] The base of about -0.4% in the held-out gap of 2014 to 2018, when last and followed
  ads differ little, and the part of regulated apartments with no flag in the last-ad
  selection. Neither was measured.
- [x] Read the ads of buildings whose new 2-or-more-bedroom units miss together (The
  Seren, Lawrence Tower, Union Channel, 420 Carroll, 12 Halsey St) for prices set by
  floor plan type. Done 2026-11-20 (`docs/notes/plan-type-misses-2026-11-20.md`): the
  shared miss is a level for building and bedroom count among units new to training; the
  line and the ad text add nothing that holds on both halves, and the plan image's excess
  is steady but small, the size of the bath excess.
- [x] Read the 307 open ads on pages whose previous ad has another bedroom count, on
  Sonnet or Haiku readers. Done on history 2026-11-20
  (`docs/notes/changed-counts-read-2026-11-20.md`): 300 held-out pairs read; recounts,
  other apartments and coding errors are equally common in the tails and the ordinary ads.
  The wide tails belong to ads whose most recent earlier training ad has other counts
  (10% to 12% low and 10% high by half, scale factor 1.35 and 1.40 against 0.92), and most
  of all to ads whose counts are new to the unit (factor 1.68 and 1.71). Open: a scale mark
  for an ad whose counts are new to the unit, as a candidate for the next base refit, to be
  checked on a market backtest with its form fixed beforehand. No unit-match rule, text
  mark or data change follows.

**From the Deals list of 2026-11-10** (`docs/notes/drift-2026-11-10.md`). Each is a change
of the model's inputs or sampler, so each needs a dataset rebuild or a fit of its own.

- [ ] Refresh the market snapshot every few days. The refresh of 2026-11-18
  (`docs/notes/market-refresh-2026-11-18.md`) found 34.7% of the Nov 9 table closed after
  nine days and 61 of its first 100 uncautioned ads. A refresh is a top-up scrape (about
  100 OxyLabs requests), a pipeline build, the dataset chain with `b0nyc --registry` set to
  the build's NJ registry, and a held-scales market fit at about $2. `ops/deals-refresh`
  runs the datasets, the fit and the publish; each refresh still needs its note with
  predictions on master before the fit.
- [ ] Rewrite the text flags the model reads (`features.DESCRIPTION_FLAGS`, copied in
  `b0data.TEXT_FLAGS`). `income_restricted` missed 33 of the 55 income-restricted ads on the
  market of 2026-11-09 (a hyphen in "income-restricted", "income requirements", "HPD",
  "affordable unit") and 8 of its 30 hits quote a fee schedule. `shared_space` matches
  "roommates" in sales talk and found no room in a share. `rentfrontier.cautions` has
  patterns that were checked by reading. Rewritten on 2026-11-13 as new columns in a copy of
  L1's dataset (`rentfrontier.b0textflags`, `docs/notes/text-flags-2026-11-13.md`):
  `income_restricted_v2` reads at precision 0.99 and recall among listings with a mark or a
  candidate word 0.96, against the old 0.91 and 0.55, and L1 overprices the 122 held-out ads it adds by 0.107 ± 0.027. S15
  (`docs/notes/income-flag-2026-11-14.md`) emulated L1 reading `income_restricted_v2` in place
  of `income_restricted` and found no gain (-64.1 ± 60.7, and -8.2 ± 14.3 on the new flag's ads),
  so that fit is not planned. Since 2026-11-14 v2 has a guard against "no income
  restrictions", and the copy carries the AMI tier and income band read from the text. S15b
  found a level by tier gains +5.3 ± 6.8, all of it on the ads with no tier, against
  +65.4 ± 20.2 for a wider spread. I1, `drift-building-phase-income`
  (`docs/notes/income-noise-2026-11-14.md`), puts a factor on the noise of v2's rows as D1
  does; it is written, not fit. The band patterns miss tables and bare ranges and need work
  before a fit reads the maximum.
  `shared_space_v2` drops 29,943 of the old flag's 30,209 rows. `rent_stabilized` misses
  misspellings ("stablized", about 1,280 listings).
- [x] Parse free months written in words ("FIRST TWO MONTHS OF LEASE AND LAST MONTH ARE
  FREE"). Done on 2026-11-13 as `months_free_text`, `free_lease_months` and
  `free_text_kind` in a copy of L1's dataset (`rentfrontier.b0freetext`,
  `docs/notes/free-months-text-2026-11-13.md`). The text gives months on 112,159 rows with
  no coded value, 85,051 of them before 2020, counting weeks at 4 to the month as the coded
  field does. `ask_basis_text` gives the text's word on the listed price: net on 82,720 of those
  rows, gross on 917.
- [x] Studio-coded ads that are not studios. Of the 292,286 studio-coded training ads of
  the latest split, 1,596 in 908 buildings name two to five bedrooms in a text that never
  says "studio" (25 of 40 read were whole apartments, 11 studios), and 4,517 in 1,701
  buildings are placeholder listings (text under 30 characters or starting "draft", with
  `roomCount` 1). Eight buildings of such
  ads are among the ten behind the building model's one failing R-hat (1259 Jefferson Ave, 310 Linden St, 866
  Knickerbocker Ave, 386 St John's Pl, 1030 DeKalb Ave, 1405 Lincoln Pl, 391 Greene Ave,
  662 Nostrand Ave). Done on 2026-11-12 over all kept ads as far as the records allow
  (`docs/notes/outlier-sprint-2026-11-11.md`, "Ads coded 0 bedrooms across all listers"):
  about two thirds of the placeholder listings are real studios, so no rule excludes them
  as a class. The ledger sets 270 ads on building or page evidence and excludes 479. The
  ads left with a count in the text price as studios (median held-out gap 0.000). Rule B2
  then excludes 412 blank ads in buildings with no studio anywhere in their history
  (`2026-11-12-outlier-sprint-zz-blank-rule-b.ndjson`).
- [ ] Gross up net asks in the dataset: `cautions.net_ask` marks 4,857 ads of the Nov 9
  build whose page price is a round first ask less uncoded free months
  (`docs/notes/net-ask-caution-2026-11-18.md`). Deals cautions them; the model still
  reads them as gross. A data rule, then a fit. On the held-out history the gap of
  net-called asks with no coded free months is -0.014 and belongs to ads before 2022 (268
  ads with free months in the text alone from 2022 on, net-called or otherwise, no gap),
  so the rule cleans training rows of 2016 to 2021 and changes few current predictions (`docs/notes/history-scan-2026-11-18.md`).
- [ ] Terms for the next refit of the base model, each confirmed on both halves of the
  held-out buildings and sized by calibration on stored predictions
  (`docs/notes/history-scan-2026-11-18.md`): LN1, a level for building and bedroom count
  (`drift-building-phase-line`), as the first candidate for first-ad units, with a market
  backtest (`docs/notes/first-ad-noise-inputs-2026-11-20.md`,
  `docs/notes/plan-type-misses-2026-11-20.md`), and after it a factor by thin same-bedroom
  building history only if still needed (factor 1.52 and 1.65 with no earlier same-bedroom
  ad, down to 1.10 and 1.10 with 20 or more); a noise factor for ads whose counts differ
  from the unit's most recent earlier ad, mostly for counts new to the unit (factor 1.68 and
  1.71 by half on the latest split, 1.52 with se 0.13 on the Deals backtest) and smaller
  where the unit had the counts at some earlier time (1.15 and 1.19), suggestive with both
  halves in view, its form to be fixed before the fit and checked on a market backtest
  (`docs/notes/changed-counts-read-2026-11-20.md`). On the Deals backtest the width is among
  ads that `rooms_up` and `beds` already mark (factor 1.65 on 114 ads against 1.24 on the 47
  others), so the term's form should start from those marks; a page caution was tried and
  dropped; a level near -0.03 and a factor near 1.2
  for three or more baths; a factor of
  1.15 to 1.2 for the top 3% of predicted rents; a level near -0.015 for four or more
  bedrooms; the first-floor level and the duplex factor of
  `docs/notes/duplex-scale-2026-11-18.md`, the level confirmed on the model's own floor
  snapshot by `docs/notes/four-traits-2026-11-21.md`, with a floor-1 scale term as the second
  candidate if the level leaves the low tail wide; a level for 3+ bedroom rows rising with
  the building's share of ads naming finishes (marble, a chef's kitchen, named appliances),
  taken from the building's earlier ads: −0.011 at share 0 and +0.006 to +0.010 over 0.5,
  60% to 70% of the step inside a tier of predicted rent
  (`docs/notes/large-unit-text-2026-11-21.md`). None changes enough of the Deals list for a
  fit of its own (the changed-count and three-bath classes hold about 60 of 425 low-tail ads
  on the backtest). Fitted together on stored predictions
  (`docs/notes/joint-terms-2026-11-21.md`) they gain +1,331 elpd (SE 70; +593 and +739 by
  half) on the 129,861 held-out ads from 2022 on, beside an overall predictive about 4% too
  wide that belongs to the noise term; one in seven low-tail ads leaves the tail and about as
  many join. The four-bedroom level (8, SE 5) and the share-0 flag (11, SE 8) add little
  beside the others and can be dropped. Optional additions: text columns for private outdoor
  space where the coded field is false (+16, SE 10) and for penthouse wording (+8, SE 5), each
  beside the others (`docs/notes/text-columns-2026-11-21.md`). A scale term for the count
  of the scan's 31 text flags changed since the unit's last ad (1, 2, 3 or more; 3 or more
  at a scale of 1.13) gains +254 (SE 28; +132 and +121 by half) beside the base and moves
  about 5% of the low tail; built after a first run, so a fit confirms it before Deals reads
  it. Beside it, the renovation switch (the ad whose text first says renovated after the
  unit's last ad did not) gains +54 (SE 12) with a shift near +0.007
  (`docs/notes/renovation-step-2026-11-21.md`).
- [x] Deals page: a first ask below the 5% point closes sooner for studios and one-bedrooms
  (45% and 39% within 7 days against 30% and 29%) and no sooner for four or more bedrooms
  or for ads with coded free months (`docs/notes/history-scan-2026-11-18.md`, last table). A page note or
  an ordering that uses it is a site change with no fit.
  Done: the backtest card's note on low places by bedroom count has carried these figures since #1457; a test now checks it. The free-months row stays off the page (the note's later section says days listed of those ads do not follow price).
- [ ] A width by ad source: feed ads' held-out asks are a little tighter than the model
  allows (free check, about +140 elpd on 45,448 ads, give or take 50, at a factor near 0.9). A term needs a
  new module, a backtest and a market fit.
- [ ] The bedroom text reader (`rentfrontier.b0bedtext`): let a size stated in the ad's first
  line stand when a later sentence lists the building's sizes, and read "flexible 5th
  bedroom" as flex wording. 6 of 6,565 live ads on Nov 18, so it rides with another dataset
  change (`docs/notes/first-page-read-2026-11-18.md`).
- [ ] Tune or defend the 4 degrees of freedom: the levels' body looks normal and the tail
  is a few gross outliers, which sit 10 to 18 scales out under the t prior.
- [ ] A sampler move for a building in two states, if the two above leave any: new
  weights for the building's rows, accepted on its marginal likelihood with level, path
  and units integrated out.
- [ ] Carry an ad's concession through its history, so a first ask can be put on the net
  basis exactly (`drift_deals.first_net` assumes the latest concession throughout).
  `pricing.priceChanges` cannot do it: it holds only dates and prices, and `monthsFree` is
  the record's current value. Only repeat collections since 2026-10-15 show a concession
  changing, so a fix needs a snapshot-dated `months_free` at open in the ads table
  (`rentfrontier.market`) and works only for backtest days after that date
  (`docs/notes/first-net-concessions-2026-11-20.md`).

**From the building-level read of 2026-11-20** (`docs/notes/building-level-read-2026-11-20.md`).
No fit was run for these.

- [ ] Candidate ledger rows for the 96 buildings whose kept level did not mix: 68 drafted in
  `docs/notes/building-level-read-2026-11-20/candidate_rows.ndjson` (75 were read in full, 7
  dropped and 4 re-kinded; not in the ledger; each
  needs `decided`, `source` and `when`), 14 placeholder rows coded 1 bed that need a rule
  decision, 5 misjoin rows to re-read. Importing them is a rule version, which makes the
  served fit unservable until a refit, so it goes with the next refit and needs Ben's word.
- [x] A publish caution for a high building level on few training ads: `thin_level` (level
  over 0.3 on five or fewer training ads, #1478, `docs/notes/thin-level-caution-2026-11-20.md`).
  On held-out history such ads are below the 5% point 14% of the time against 5.9% (both
  halves of the buildings). Live since the publish of Nov 20, 6:02 PM ET: 16 ads marked.
- [ ] The model under-shrinks buildings with few ads in both directions: levels on 1 to 5
  training ads should be 7% to 10% smaller (`docs/notes/thin-building-shrinkage-2026-11-20.md`).
  The test is `--level-dof 8` at held scales, with the prediction written there. Not launched:
  the backtest cannot show the gain. It fits best inside the next base refit.
- [x] After each fit, list buildings with a level beyond 0.5 in size and under ten training
  ads. R-hat does not see them: six buildings sat at levels of 0.56 to 2.17 with live R-hat
  of 1.03 or less, except 922 Lincoln at 1.052. `python -m rentfrontier.drift_kept_report RUN`
  lists them with their count of training rows, and the ads and buildings with kept R-hat
  over 1.05 (`docs/model/drift.md`, "Running it"). It gives counts, not the rows themselves.
- [ ] Read the 338 buildings the report lists on the live run (4 hold 6 scored ads, all four
  read in `docs/notes/building-level-read-2026-11-20.md`); the rest matter when an ad joins.
- [ ] Import the 254 drafted excludes of
  `docs/notes/commercial-sweep-2026-11-20/candidate_rows.ndjson` with the next base refit
  (226 `nonresidential`, 28 `bedrooms_unknown`). The hand read of all 934 ratio-mark
  training rows is done (note section "Hand read of the ratio rows (2026-11-21)"): 204
  commercial, 27 placeholder, 38 unclear and 665 apartment, two blind reads on every code
  other than apartment. 31 listing ids also appear in
  `building-level-read-2026-11-20/candidate_rows.ndjson`, all `nonresidential` in both, so
  the import should take each once. The 38 unclear rows stay in training. The sweep found no
  pipeline rule and no case for a building-level change.
- [x] Check the 0 bed code on apartment ads of the ratio read: 165 of the 665 apartment rows
  in `docs/notes/commercial-sweep-2026-11-20/reads_ratio_all.csv` are coded 0 bed, and 53
  of their reads cite 2 to 5 beds. Size the pattern on the history (ads coded 0 bed whose
  text or unit's other ads give 2 or more), against the 2026-11-12 blank-form rules in
  `docs/notes/outlier-sprint-2026-11-11.md`, then decide on ledger bedroom sets or a rule.
  Done in `docs/notes/zero-bed-apartments-2026-11-21.md`: 30 of the 53 are filled forms
  outside every 2026-11-12 class and 23 failed its rules' conditions. The text mark (638
  training rows) reads right on 0.79, the unit's-other-ads mark (12,646) on 0.04, since
  those ads mostly describe another apartment. Held-out excess is small (21 text-marked ads,
  mean gap +0.097 with ledger-named ads kept in). A blind read of all 195 rows that meet both
  marks agrees with the text on 181; 120 of those also have most of the unit's other counted
  ads agreeing and are drafted as ledger bedroom sets.
- [ ] Import the 119 drafted bedroom sets in
  `docs/notes/zero-bed-apartments-2026-11-21/candidate_rows.ndjson` with the next base refit
  (section 6 of `docs/notes/zero-bed-apartments-2026-11-21.md`). They overlap neither the
  commercial sweep's nor the building-level read's candidate files. Their agreeing ads are on
  the same page and in other fit units (`docs/notes/label-reuse-2026-11-21.md`), so check each
  set row's fit unit after the split runs. The 19 read as mixed were checked again on
  2026-11-21: 17 confirmed, one dropped as a 1-bedroom with a convertible living room, one
  kept (end of section 6).
- [x] Study unit labels reused across layouts: in 9 of 10 reads of 0 bed ads whose unit's
  other ads all code 2 or more, those ads describe a different apartment
  (`docs/notes/zero-bed-apartments-2026-11-21.md`, section 2). Done 2026-11-21
  (`docs/notes/label-reuse-2026-11-21.md`): every such pair lies on one page, so no
  label_units layer joined it and v18 splits none; unit-splits-v4 already separates them in
  the fit's units. No rule or ledger draft. Later marks from a unit's other ads should group by
  `split_unit`.

**From the broker read of the top 60 Deals of 2026-11-21** (`docs/notes/deals-top-read-2026-11-21.md`).
No fit was run for these. The readers' blocks held the asks, so each item is coded without rent
first.

- [x] A `deposit_net` Deals caution: a flat security deposit at least 2% above the page
  price, no coded free months, a deposit other than the first ask, and a deposit that fits
  the page price as a net rent over a 12 to 24 month lease. It would mark 88 of 6,502 live
  ads, 5 in the first 60 and 12 in the first 300. The deposit is in the records file the
  publish already reads for texts. Decide whether to require a ratio of 1.05 or more.
  - 2026-11-21: merged in #1508 with a ratio of 1.05 and published at 12:59 AM ET on Nov 21
    from range-m3 with the range-j backtest; 75 ads carry it.
    The texts table now keeps the chosen record's deposit; publish refuses one without it
    and `ops/deals-refresh publish` rewrites such a cached table. On `range-m3` it marks 75 of the 6,502 ads, 50 with no other caution, 4 in the
    first 60 and 11 in the first 300 of the default view.
- [x] A short-lease Deals caution for text that prices a lease under 12 months (one case
  in the first 60, "$17,500 for a 6-month lease").
  - 2026-11-21: `short_lease` on the "N-month lease" form, whose excess of low asks holds
    on both halves of the latest split's held-out buildings; one scan printed both halves at
    once, so half B was not held back (`docs/notes/short-lease-2026-11-21.md`). 8 live ads.
- [x] Extend the `beds` caution or the bedroom text reader to "convertible", "alcove
  studio" and "wall not yet installed" on ads coded one bedroom or more.
  - 2026-11-21: no caution (`docs/notes/flex-wording-2026-11-21.md`). Wording the reader
    misses is too rare to tell (80 held-out ads), and flagged flex wording is near the unmarked rate. Ads
    coded 1 bedroom or more whose text reads as a studio are 12.5% and 17.5% low on the two
    halves, but a third of the 24 live readings are reader errors.
- [ ] A term for a studio reading on an ad coded 1 bedroom or more, beside
  `ad:bed_text_smaller`, with `b0bedtext` fixes for amenity names ("wellbeats studio") and
  "the size of a ... studio". One change for the next base refit, with a note and
  predictions first (`docs/notes/flex-wording-2026-11-21.md`).
- [x] If the `deposit_net` caution goes in, decide whether a free-months and lease-term fill
  for exact fits (733 Lincoln, The Lightwell Dumbo) is worth a screen. It keeps the target
  net; a gross rent from the deposit would break it. The mark reads the page price, so it may
  screen or carry a caution and may not become a data rule (`docs/leak-free-scoring.md`).
  - 2026-11-21: no fill. `deposit_net` already hides these ads from the default view and its
    chip says why. A gross figure would add a number beside a ranking that stays on the page
    price, the model's target.
- [x] Test on held-out history, on two halves of the buildings: the elevator field by zone
  (7 text walkups in the top 60 against 1 in the middle), the virtual doorman against
  full-time (16 against 7), a text mark for a condo or co-op unit an owner rents out
  (7 against 1), and garden or ground-floor wording against the floor field (18 against 11).
  - 2026-11-21: walk-ups, the virtual doorman and garden wording hold no steady excess.
    Condo or co-op text holds a small two-sided one. Coded floor 1 runs low on both halves
    (8.3% and 8.0% low, gap -0.012 and -0.011), with or without the snapshot's garden flag
    (`docs/notes/four-traits-2026-11-21.md`). This confirms the first-floor level already in
    the list of terms for the next base refit (`docs/notes/duplex-scale-2026-11-18.md`).

**A latest split that holds still across builds** (2026-10-23). `splits.latest_split` draws its
held-out units with `rng.choice` over the sorted audit ids of every candidate unit, so a build
that drops a handful of rows shifts the position of every later id and reshuffles the draw.
After the #1235 corrections dropped 14 rows, about 70,000 held-out picks changed, and a
comparison of fits across the two builds could pair only 63% of held-out ads
(`docs/notes/building-zones-floor-asof2-2026-10-23.md`). The fix I have in mind keys each
candidate on a hash of its unit id and holds out the units whose hash falls under the target
share, so a unit keeps its side of the split whatever else enters or leaves the build. I'm
leaving the current split in place until the conference comparisons are done, since every
fit in them was scored on it. Switching it changes every latest-split score, so the board
needs refits of the served model and its rivals on the new split at the same time.

**Data items still open from October** (moved from the list before 2026-11-10).

- [ ] **Data (once Brooklyn is collected): remap the Brooklyn ads filed under Manhattan buildings**
      (Ben, 2026-10-14). quarantine-v17 holds out 35 such rows with the reason code
      `brooklyn_misjoin`. For each one, `config/reviews/brooklyn-misjoins-20261014.jsonl` records the
      address StreetEasy shows, the address the agent typed, the ad phrase that places it in Brooklyn,
      the agent and a candidate Brooklyn address. Match each candidate to a collected Brooklyn
      building, move the row there, and release it from the next quarantine version. Run
      `frontier/scripts/brooklyn_screen.py` on every new dataset in the meantime.
      Checked 2026-10-17 against the pipeline's drop-lot lane, where the file now has 63 rows. All 63
      sit in Manhattan buildings, and the pipeline ledger excludes them. 11 ads, at 9 addresses, match
      exactly one collected Brooklyn building: 316 and 357 7th Avenue, 509, 805 and 809 8th Avenue,
      126 4th Avenue, 109 5th Avenue, 43 Irving Place and 80 Lexington Avenue (11238). The others name
      streets outside the collected area, such as East 17th to 21st Streets in Flatbush, or give no
      address. The unit ledger can move a whole building (`move_building`) or split ads within one
      building, but it has no change for moving one ad to another building, so remapping the 11 waits
      on such a change. Table: `/data1/apartments/tmp/suspect/bkremap/brooklyn-matches-20261017.csv`.

- [ ] **Data: `text:renovated` misses "remodeled"** (2026-10-15). The 1 Patchin Place ads
      3848319 and 4404993 say "remodeled" and get no renovation flag. On NB9, 519 ads say remodel,
      remodeled or remodeling without any form of "renovat". Widening the pattern is a new feature
      version, so the existing pattern stays as it is.
      Measured 2026-10-15 from the description files: 387 ads say remodel without "renovat"
      (Stuyvesant Town left out). A Haiku read of 80 of them found 53 about the apartment, 19
      about the building only and 8 unclear. The served `text:renovated` term is +1.0%, so
      flagging about 390 more ads at two-thirds precision predicts a LOO change far under the
      2 SE bar. Held for a fit that tests other text changes, not a Modal fit alone. Sample and
      labels: `/data1/apartments/tmp/suspect/remodel/`.
