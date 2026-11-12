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
- [ ] Gate fits run 6 chains (three containers of 2). c1's 4 chains missed the gate by a
  tail event with a chance of 2.1% to 2.8% at b9's mixing, against 0.55% to 0.74% for 6
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
  runs -0.011, +0.010, +0.004 and -0.023 in 2019 to 2022 and -0.010 to -0.017 since, as a
  stabilized rent moves by the Rent Guidelines Board's increase while the market fell and
  recovered (the sprint note, "Residuals by text flag"). The term is a coefficient on the
  area path for flagged rows. Predicted: the coefficient lies between 0.3 and 0.7, the
  yearly gaps of flagged ads fall inside ±0.006, and elpd gains 20 to 80 on the latest
  split. Needs a note. The DHCR building lists are a source for the flag apart from ad
  text and should be joined first.
- [ ] A renovation step dated from the unit's own ads: a column set from the first ad of a
  unit whose text says renovated or gut renovated when an earlier ad of the unit lacked the
  words. Ads switching the words on sit +0.009 to +0.012 over the model, and ads dropping
  them sit at zero, so the step stays once taken. Predicted: a coefficient of +0.005 to
  +0.010 and an elpd gain under 40. DOB alteration filings by BIN can date the work
  without the ad text, and photos can confirm it.
- [ ] Text columns where the lister left the coded field empty: private outdoor space
  (+0.0154 where the field is false), penthouse (+0.0058), dishwasher (+0.0064), furnished
  (8,064 held-out ads say it, no training row has the coded field) and full floor (no
  column, +0.0124 within building). Each is a fit of its own. Predicted for each: a
  coefficient between half and the whole of the figure given here, and an elpd gain
  under 30.
- [ ] Free months parsed from ad text as an added column for the 5,502 held-out ads (and
  their training counterparts) with a concession in the text and none in the record. The
  ask stays as recorded: in most of these ads the lister typed the net rent as the price.
  Predicted: the group's mean gap moves from -0.011 to within ±0.004. This widens the
  parsing item under the Deals list.
- [ ] Diagnostics: take each held-out ad's previous ask from the same build and the same
  model unit as the fit. `prev_ask` in `site/diagnostics/ads.parquet` comes from the market
  build's history, which crosses the pieces of an apartment: in 40% of the ads whose
  adjusted previous ask sits over 0.3 above the model it belongs to another configuration,
  and of 79 market ads checked, 38 had their previous ad under another unit id in the other
  build and 28 had none in the market build.
- [ ] Size-fill rules in the pipeline. A size coded too large was found in 15% of 120
  large-unit ads read, with weighted error shares of 0.41 for line fills and 0.33 for unit
  fills against 0.11 for stated sizes (26 filled ads read, so the rule needs a wider read
  first). Proposed: do not carry a unit's size to an ad with another bedroom count or in
  another piece of the apartment, and do not fill from the line when no ad of the unit
  states a size and the fill is more than 40% over the bedroom median.
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
  2026-11-12 repair single pages until the next ad arrives on them.
- [ ] For Data improvements: a pipeline rule for ads posted with a blank form. Real Street
  Inc and M1 Ventures post ads with the form's fields empty, and the feed codes them as 0
  bedrooms, 1 bath and 1 room. The marks are a description of one to three characters or
  "Draft" for Real Street and legal boilerplate alone for M1, with 0 bedrooms, 1 bath and
  1 room coded. The ledger of 2026-11-12 decides the 768 kept ads of this kind by hand
  (22 take their building's count, the rest are excluded as `bedrooms_unknown`). The rule
  would treat the coded count of such an ad as missing when the ad arrives, so new ones
  need no ledger entry. Screen the other listers for the same marks first.
- [ ] Screen The Rheingold (10 Monteith St) and buildings like it, where brokers post ads
  for any unit of the building under arbitrary unit pages: 431 of its 592 pages with two
  or more kept ads hold two or more bedroom counts. Mixed counts alone do not mark the
  practice: 489 of the 4,002 buildings with 20 or more such pages have over half of them
  mixed (loft buildings lead the list, where listers code the same space as 0, 1 or 2
  bedrooms), and the shared-unit reads found no second apartment in 15 units flagged by
  bedroom counts alone. Screen on the ads' text ("any unit in the building") and on asks
  running at once on a page, then decide between leaving those unit levels and dropping
  them.
- [ ] L1: a noise scale by lease phase, a factor on the ad-level scale per group of months
  since the opening of the unit's previous ad (none, under 3, 3 to 9, 10 to 13, 14 to 21,
  22 to 25, 26 or more). The served intervals cover 0.752 of held-out asks at 3 to 9
  months against 0.841 at 10 to 13, and the model's width runs the other way. Predictions
  and the free checks are in the sprint note ("The lease cycle"; elpd +400 to +900).
- [ ] Y1: a noise scale by calendar year. Coverage is 0.745 for held-out ads of 2020 to
  2022 and 0.826 before and after; current intervals are 7% to 9% too wide by the free
  check. Predictions are in the sprint note (elpd +600 to +1,300). Before the fit, check
  the training rows' residuals by year from b9's saved draws, since each held-out ad is
  its unit's newest and the units last advertised in 2020 to 2022 may differ.
- [ ] L2: a level per lease phase on L1's winner (apartments back within 3 months come
  1.4% under the median). Behind it, a column for the previous ad's ending (delisted or
  paused against a deal), which needs the raw status histories carried into the dataset.
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
  "Observed attributes of large units"), so the scale comes first. Needs a dataset module
  carrying a size column (stated sizes and sizes agreeing across a unit's ads first).
  Predictions are in the sprint note (`gamma` 0.3 to 0.6, elpd +150 to +500).
- [ ] U3: a building-level coefficient on `max(0, log(sqft / 1000))`, on U1's winner.
  Different large units of one building share 25% of the persistent covariance (15% to
  37%), against 4.2% for the building attributes on record.
- [ ] U2: a Student-t distribution for the unit's lasting level, on U1's winner. Predicted
  to close with over 8 degrees of freedom and under 100 elpd.
- [ ] Read floor plans and photos of large units for the qualities the record lacks (a
  second level, a full floor, a renovation), on Sonnet or Haiku readers. No check in the
  sprint read them, and the recorded attributes leave the persistent sd of large units at
  0.091 against 0.026 for mid-sized units.
- [ ] Find the cause of the served median standing 0.47% above held-out asks (about 1% in
  2022 and 2023, near zero in 2026).

**From the Deals list of 2026-11-10** (`docs/notes/drift-2026-11-10.md`). Each is a change
of the model's inputs or sampler, so each needs a dataset rebuild or a fit of its own.

- [ ] A new market snapshot and refit. The Deals list is the market of 2026-11-09, scraped
  once on 2026-11-10, and goes stale as ads close. The three fits of the served model
  (`drift-building --level-dof 4`: latest split, market, backtest; three containers of
  two chains each, pooled) cost $33.02 on 2026-11-10, each container running 50 to 52 minutes. Launch
  the first container of a new commit alone, then the rest.
- [ ] Rewrite the text flags the model reads (`features.DESCRIPTION_FLAGS`, copied in
  `b0data.TEXT_FLAGS`). `income_restricted` missed 33 of the 55 income-restricted ads on the
  market of 2026-11-09 (a hyphen in "income-restricted", "income requirements", "HPD",
  "affordable unit") and 8 of its 30 hits quote a fee schedule. `shared_space` matches
  "roommates" in sales talk and found no room in a share. `rentfrontier.cautions` has
  patterns that were checked by reading.
- [ ] Parse free months written in words ("FIRST TWO MONTHS OF LEASE AND LAST MONTH ARE
  FREE").
- [ ] A caution for an ad whose text gives another bedroom or bath count than its record.
  Three of the first 40 ads shown on the morning of 2026-11-10 were of this kind (655
  Hart St 2F, 329 Decatur St 1I, 2246 Fulton St 5G) and one of the afternoon's (1390
  Madison St 1). A plain pattern was read and dropped: of 573 market ads whose text names
  only counts that differ from the record's, 10 of 80 read described the apartment
  itself (the note, "Cautions, round two"). A rule has to tell the apartment's own line
  from the building's mix of units. The real ones, somewhere between 40 and 125 at the
  sample's rate, are worth it.
- [ ] Studio-coded ads that are not studios. Of the 292,286 studio-coded training ads of
  the latest split, 1,596 in 908 buildings name two to five bedrooms in a text that never
  says "studio" (25 of 40 read were whole apartments, 11 studios), and 4,517 in 1,701
  buildings are placeholder listings (text under 30 characters or starting "draft", with
  `roomCount` 1) whose bedroom count of 0 is the source's default. Eight buildings of such
  ads are among the ten behind the building model's one failing R-hat (1259 Jefferson Ave, 310 Linden St, 866
  Knickerbocker Ave, 386 St John's Pl, 1030 DeKalb Ave, 1405 Lincoln Pl, 391 Greene Ave,
  662 Nostrand Ave). Write the rule on a reading, rebuild, refit.
- [ ] Sublets with an end date: the `takeover` caution leaves them out because "sublet"
  alone is a building's policy in most ads (6 of 28 read were a sublet on offer, 3 of
  them firmly).
- [ ] Tune or defend the 4 degrees of freedom: the levels' body looks normal and the tail
  is a few gross outliers, which sit 10 to 18 scales out under the t prior.
- [ ] A sampler move for a building in two states, if the two above leave any: new
  weights for the building's rows, accepted on its marginal likelihood with level, path
  and units integrated out.
- [ ] Carry an ad's concession through its price history, so a first ask can be put on
  the net basis exactly (`drift_deals.first_net` assumes the latest concession throughout).

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
