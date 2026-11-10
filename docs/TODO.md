# Project to-do list

Open items for the current model (`drift-building`, see [model/drift.md](model/drift.md)) and the
Deals page, and two data items from October. The aim is in the root [README](../README.md). The list as it stood before 2026-11-10,
with the Chelsea pilot's and the frontier line's items, is in
[archive/TODO-2026-10.md](archive/TODO-2026-10.md).

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
