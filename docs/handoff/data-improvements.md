# Data improvements — handoff

Updated 2026-10-17 12:15 ET, after the never-built drop-lot reviews (#1024). Thread owner: the Data improvements project thread (bridge session on thelio).

## 2026-10-17 13:40 ET

- #1039 adds `pipeline/ledger/2026-10-17-z2-unit-sqft.ndjson`, 71 square-footage sets. The screen
  (`/data1/apartments/tmp/suspect/sqft/screen.py`) keeps an ad when at least 2 other ads of the same unit with the
  same bedroom count, within 730 days, agree within 5% and the ad sits 30% or more off their median. That gave 160
  ads. Sonnet read all of them with the unit's other ads (`r0..r3.jsonl`): 111 wrong, 28 unclear, 14 right, 7 a
  different unit. 82 of the 111 reads gave a size inside the other ads' range. Review dropped 11 of those 82: one ad states a
  third size, five may count a basement or roof deck in the larger figure, and five sit in a mixed size history.
  `ledger.py` in the same folder writes the file.
- #1043 proposed retracting the #1039 set on ad 1399109 (754 E 6th St 6E, 975 to 1860), since its ads also
  describe an 850 sq ft roof deck. Review found the 4BR duplex's 21 by 35 ft great room can't fit in 975, and no
  ad says 1860 includes the deck, so #1043 was closed and the set stands. The sqft-units-v1 review kept 975 only
  through a mechanical rule on outdoor-space mentions. A unit-page match against
  `config/reviews/sqft-units-reads-20261015.jsonl` found no other overlap with #1039.
- A bedroom-count screen (`/data1/apartments/tmp/suspect/beds/screen.py`) keeps an ad when the unit's other ads
  within 730 days all agree on another count, with at least one before and one after. That gives 7,909 ads, 1,398
  of them with sizes that agree. Sonnet read a 40-ad sample of the 1,398 (`sample.jsonl`, `sample-r.jsonl`): 21
  flex or convertible, 8 wrong, 7 unclear, 4 a different unit. At about 20% wrong, a full read of the 1,398 would
  yield roughly 280 corrections. That waits behind other work, and its entries would need a check against the
  bedrooms-ad rule family first.

## 2026-10-17 13:15 ET

- #1036 adds `pipeline/ledger/2026-10-17-z-unit-baths.ndjson`, 492 bath-count sets. The screen
  (`/data1/apartments/tmp/suspect/baths/mech.py`) looks at ads of the same unit with the same bedroom count within
  730 days. It keeps an ad when all those ads agree on another count, at least one comes before it and one after,
  and its own text states no bath count. That left 616 ads. Sonnet read all of them (`reads*.jsonl`,
  `p3/r*.jsonl`): 530 were wrong, and 503 of those reads gave the count the other ads show. Review dropped 11 of
  the 503, where a backing ad's text states the row's count, which leaves 492.
  `ledger.py` in the same folder writes the file.
- The regex in `mech.py` misses hyphenated counts such as "1-bath". A wider screen would start from all 2,873 ads
  with 2 or more disagreeing ads, before the strict filter, and relax the before-and-after condition. Sonnet read a
  40-ad sample of the 2,873 (`packets.jsonl`, `reads.jsonl`), and 15 of the 28 ads outside the strict filter were
  wrong.
- The 80 unclear drop-lot rows from the 11:40 entry stay as they are. HPD violations, rent stabilization counts and housingdb hold
  nothing that decides them.
- #1033 notes 11 Brooklyn misjoins (9 addresses) that match one collected Brooklyn building. Moving a single ad
  to another building needs a ledger change that doesn't exist yet.

## 2026-10-17 12:15 ET

- #1024 adds `drop-lot-20261017-neverbuilt.jsonl`, 239 wrong_building lines on 33 lots. Every one of the 40 MapPLUTO
  releases from 11v1 to 26v2 gives these lots no building area and no apartments, and no 2026 footprint stands on them.
  They are parks, parking, rail and vacant land, such as 1485 Broadway in Brooklyn (63 ads). The evidence uses city
  records only. Scripts and tables are in `/home/ben/.cache/di-neverbuilt/` and
  `/data1/apartments/tmp/suspect/bcheck/never-built-20261017.csv`.
- The pipeline thread's #1025 adds a `never_built_lot` reason to `analysis.building_check`. On the drop-lot lane
  it lists exactly these 239 rows. Three of them were already listed by zero_unit_lot. The import of #1016, #1021
  and #1024 (253 lines) waits on Ben's word in the pipeline thread.
- On the registry side, 133 buildings sit on a never-built registry lot while the pipeline links them to the
  neighboring lot by footprint. Their StreetEasy year and apartment count don't back the neighbor lot
  (`/home/ben/.cache/di-neverbuilt/reg2.csv`), so they get no registry override.
- A screen comparing advertised units with the lot's apartments doesn't work, because `ads.placed` holds 2 to 3
  unit ids per real apartment in large buildings.

## 2026-10-17 11:40 ET

- #1016 adds `config/reviews/drop-lot-20261017-lowfootprint.jsonl`, 8 wrong_building lines. Each ad's unit
  label names floor 2 or higher, and its lot holds a single one-story nonresidential footprint of 11 to 20 ft.
  The source table is `/data1/apartments/tmp/suspect/bcheck/footprint-height-20261017.csv`.
- #1021 adds `drop-lot-20261017-shortbuildings.jsonl`, 6 wrong_building lines on three walkups of 31 to 37 ft
  (958 Halsey, 126 16th St, 792 Kent). The ads put the apartment on floors 5 to 9. The source table is
  `short-building-20261017.csv` in the same folder.
- The pipeline thread imports both files into the ledger. Its permission check refused the #1016 write from
  another thread, so that import waits on Ben's OK, and #1021 may too.
- #1018 adds `pipeline/ledger/2026-10-17-takedown-asks.ndjson`. It sets the latest ask of 5 repeated-digit
  takedown asks (3333, 4444, 5555, 9999) back to the ask in another ad for the same unit. That ad has to be
  within 3 years and at least 15% lower. The other 33 of the pipeline's 38 rows have no such ad, so they stay.
- 80 drop-lot rows remain unclear (`/home/ben/.cache/di-bcheck2/unclear.csv`), 29 of them on church or school
  lots. Certificates of occupancy gave no units for them, and footprints decide only the short ones.
  32 Remsen #5B (58 ft footprint) and 440 E 9th St (9 ads whose labels may not name floors) stay.

## 2026-10-17 10:30 ET

- #1007 re-judges five Oct 16 building-identity reviews with MapPLUTO, HPD and footprints. The address class
  now scores 33 right, 4 wrong and 3 unclear.
- #1006 (pipeline) gives `buildings.lots` the lot with apartments when the address lot and the footprint lot differ.
  #1010 imports the 1,274 reviews of `drop-lot-20261017.jsonl` as `drop_lot` ledger entries: 1,104 live, 170 stale
  (their building moved lots under #1006).
- #1012 adds `config/reviews/drop-lot-20261017-check2.jsonl` for the 339 rows the check still flagged after #1010.
  - Sonnet readers worked from packets holding the ad, the lot's MapPLUTO record, HPD registrations on the lot,
    the `buildings.lots` choice and the PAD lot of the StreetEasy address. Scripts: `rows.py`, `packets.py`, `write.py`
    and `PROMPT.md` in `/data1/apartments/tmp/suspect/bcheck/`, labels in `reader-labels-2.jsonl` there.
  - 152 rows drop their lot (79 wrong_building, 73 city_record_wrong). A reviewer moved 2776355 and 2329076 to
    unclear, because only their ad text pointed away from the lot.
  - 187 rows keep their lot: 90 unclear, 80 mixed use, 12 ad floor errors, 5 vanity floor numbers.
- The pipeline thread's #1013 imports the file as `pipeline/ledger/2026-10-17-wrong-lots2.ndjson`. On its lane copy,
  `building_check.csv` in `/data1/apartments/tmp/pipeline/lanes/drop-lot-build/` holds exactly the 187 kept rows.
- The 90 unclear rows could take floor plans or a second ad for the same unit as evidence. Mixed-use rows
  stay on their lot.

## 2026-10-17 08:30 ET

- The pipeline thread ran PAD 26c over the empty-lot list (`/data1/apartments/tmp/pipeline/lanes/emptylots/pad-buildings.csv`,
  from `padbuild.py` there).
  - Of the 43 left after #1000, PAD gives the old registry lot for 36, so they stay.
  - Of the other 7, #1003 moves 165 Concord St, 59 Grand St (Brooklyn) and 401 West Broadway
    (53 rows) in `registry-overrides-20261017-emptylots3.json`, where PAD matches at rank 0 and the lot holds apartments.
  - The Smile stays because its PAD lot holds 0 apartments. 74 North 1st, 402 East 65th and 24 Frost
    stay because PAD matches them only at rank 4.
  - For the 415 buildings where the registry and pipeline lots agree (the 296 never-built lots among them), PAD gives the same lot.
    They stay as they are.
- The HPD other_lot list (`/data1/apartments/tmp/suspect/bcheck/other_lot_pad.csv`, 48 listings in 32
  buildings) is checked against PAD.
  - The csv's `bbl` column holds the pipeline's `buildings.lots` lot, and `pad_is = registry` marks PAD agreeing with it.
  - For 35 listings, PAD gives the pipeline's lot. The all-scraped registry holds that lot too, except at 1614 Fulton St
    (registry 3016990030 by reverse geocoding, PAD rank 6 only), which stays.
  - For 4 buildings (445 E 9th, 2178 2nd Ave, 236 Congress, 453 3rd Ave), the registry
    already holds the HPD lot, and only the pipeline's `buildings.lots` disagrees. The pipeline thread has the list.
  - #1004 moves 245 Sumpter St off a school lot (`registry-overrides-20261017-hpdpad.json`, 1 row).
  - 194 Broadway has no PAD match and stays.
- The next all-scraped registry revision should list #996, #1000, #1003 and #1004. It still waits on the 1-hour cap.

## 2026-10-17 07:45 ET

- #1000 adds `config/reviews/registry-overrides-20261017-emptylots2.json`, 20 more of the 63
  relotted empty-lot buildings (1,334 all-scraped rows, One Manhattan Square 923 of them).
  18 have the pipeline lot under their own street address in MapPLUTO 26v2. One Manhattan
  Square (225 Cherry St condominium, 72 floors) and the Belnord (2360 Broadway) were read one at
  a time. Scripts: `tier2.py`, `write2.py` and `big.py` in `/data1/apartments/tmp/suspect/emptylots/`.
- No feature set uses #1000 yet. An all-scraped registry revision with #905, #996 and #1000 waits
  until an all-scraped fit can run within the 1-hour cap. NB9's registry now has 16 overridden
  buildings pending (la-botanica added), still a few hundred rows; Modeling was told.
- The other 43 are mostly footprint-only links to the house next door, plus 74 North 1st St
  (296 Wythe, 55 apartments against 38), the Smile (a 0-unit condominium lot on E 125th) and
  1010 Bedford Ave (a 1961 lot on Skillman St). They wait on the pipeline's PAD lookup, which
  gives address ranges per lot.
- Also waiting on PAD: 296 buildings (1,016 all-scraped rows) whose registry lot and pipeline lot
  agree on a lot that never had building area, mostly V0, V1, G7 and QG. StreetEasy's own
  building record calls most of them vacant too.

## 2026-10-17 07:30 ET

- #996 adds `config/reviews/registry-overrides-20261017-emptylots.json`. It moves 41 buildings
  (3,682 rows) off parks, garages, vacant land or condo unit lots, onto the lot that the
  pipeline's `buildings.lots` matches by address. The new lot must agree with StreetEasy's year
  (within 2) and apartment count (within 10% or 2). Old lots that ever had building area are left
  out, and so are footprint-only matches. Scripts are in `/data1/apartments/tmp/suspect/emptylots/`.
- #997 adds `all-scraped-lots4-v1`, which is `all-scraped-v1` on registry
  `20261017-2c61ff1-all-lots4`. The registry applies the #905 and #996 overrides (54 buildings),
  and the set carries MapPLUTO and PLUTO releases for the new lots. Modeling has it queued for a
  fit paired against all-scraped-v1 and stays on the v1 line: on NB9, lots3 was +20.8 paired LOO
  (SE 19.0), under the 2 SE bar. An all-scraped fit runs about 3 hours, past the 1-hour cap, so
  lots4 stays queued until a redesigned fit comes in under the cap or Ben grants an exception.
- 15 of the 54 buildings are in NB9's registry `20261016-104dfa2-mw-api` (11 in lots2's
  `20261015-a959a8c`), with a few hundred NB9 rows in all. That is too small for an NB9 refit by
  itself. Carry them into the next NB9 registry revision.
- Next registry revision: the rest of the 523 empty-lot buildings. The pipeline gives 104 of them
  a lot with a building. The other 63 of those 104 failed the year or unit rule, or matched by
  footprint only, and they need review one at a time.

## 2026-10-17 06:20 ET

- #987 adds `data.TRIAL_RULES`. `autoselect.current_rules` skips the versions listed there, so
  latest-ask-v9 stays current while latest-ask-v10 waits on the fit that tests it. When a v10 fit
  wins, the PR that serves it takes v10 out of the set and says how the fit was judged (scored on
  shared rows). Without v10, the incumbent differs from the current rules on 3,894 of 296,176
  rows, which is still over the 0.25% bar.
- The pipeline thread's v10 loader rows agree with changed.csv on every row both changed. The 7
  listings that disagree all have records fetched after the chain read the archive (Oct 15 13:10).
- Unit reviews:
  - v3 (#988) splits the 870 Broadway lofts off the 30 E 18th St one-bedrooms.
  - v4 (#989) adds an optional `into` on split_listings and puts the #2 loft ad into the #3
    loft's unit.
  - v5 (#990) joins 444 W 20th #1 and #GARDEN. The 2011 GARDENDPLX ad has no record, so it
    stays apart.
  - The pipeline thread mirrors all three in #991.
- quarantine-v35 (#992) drops 4853056, a Bushwick ad filed under 124 DeKalb #3. Its copy matches
  4839783 at 1248 DeKalb #3L.
- Closed without a change: the 90 Hull St placeholder ads. Their one-word descriptions explain
  nothing, but nothing in them is wrong.
- Open: the HPD other_lot conflicts, waiting on the pipeline's PAD lookup.

## 2026-10-17 05:40 ET

- #983 adds `latest_ask.CLOSING_STALE_DAYS = -1` and the rule `latest-ask-v10`, which drops every
  change dated on or after the off-market day (on-market-day changes and ads that went ACTIVE
  again keep theirs). `build_v10.py` in `/data1/apartments/tmp/suspect/ask-jumps/` repriced v9:
  104,984 rows change (22,043 NB9, 82,941 API), median log change -0.045. Table and changed.csv:
  `/data1/apartments/external/latest-ask/20261017-c201c11-all-closing/`.
  - Modeling's NB9 refits read pipeline loader rows. The pipeline thread builds a v10 lane
    (`PIPELINE_STALE_DAYS`, `/data1/apartments/tmp/pipeline/lanes/v10/`) and sends the
    `nb9-chelsea-named-rows-v10-*` path to Modeling and me. It mirrors v10 in `ads.kept_changes`
    only if the fit wins. If that path hasn't reached Modeling, relay it.
- #984 adds `quarantine-v34` (v33 plus 15 rows) and `bedrooms-ad-v10` (v9 plus 6 rows), from
  Sonnet reads in `/data1/apartments/tmp/suspect/q34/` (packet.json, packet2.json):
  - 8 Brooklyn storefronts and offices from the drop-lot review, the Ridgewood ad 2638365 joined
    to 18 Bleecker, the $21,545 Bed-Stuy studio 2121710, 3 Carlyle hotel stays and 2 lottery units
    at 9 Cook St;
  - 68 Clinton #4A and #4B "5 room duplex" ads recoded to 3 bedrooms, backed by the same units'
    3 bedroom ads.
  - 3221486 stays: its text says Park Slope, which matches its zip.
  - The pipeline thread imports both files into its ledger (asked 08:00 ET).
- Open from the mixing review (`/data1/apartments/tmp/suspect/mixing/labels.jsonl`): the 870
  Broadway unit split by stated size, the 444 W 20th alias (#1 is #GARDEN), 124 DeKalb 4853056's
  Bushwick text, the Brooklyn placeholder ads. Also open: the HPD other_lot conflicts, waiting on
  the pipeline's PAD lookup.

## 2026-10-17 05:20 ET

- #974 lets the frontier fetchers skip buildings with no BIN. #975 adds
  `config/reviews/drop-lot-20261017.jsonl`, 1,274 ads whose lot rules out their building, and
  Modeling's lots3 fit reads it. The pipeline-form copy for the pipeline thread is
  `/data1/apartments/tmp/suspect/bcheck/drop-lot.jsonl`.
- Some listing records carry price changes dated long after the ad left the market. Brokers
  reuse an old ad's record for a later ad of the same apartment. In 346 W 36th St, 12 such rows
  drove Modeling's R-hat 1.63 failure. I wrote the findings up in
  `/data1/apartments/tmp/suspect/ask-jumps/off-day-changes.md`.
  - #977 adds `latest_ask.STALE_DAYS = 7` and the rule `latest-ask-v9`. A change dated more than
    7 days after the off-market day is dropped unless the record's statusChanges show ACTIVE
    after that day.
  - `build_v9.py` in the same folder reprices V8 with the rule: 9,601 of 1,751,152 rows change,
    and V8 matched the old price on every one. The table and changed.csv are in
    `/data1/apartments/external/latest-ask/20261017-dba39e0-all-stale/`.
  - Modeling queues the v9 fit (a rule swap on DATASET_ALL) behind lots3. The pipeline thread
    mirrors the rule in `ads.kept_changes` and moves `observations.py --latest-ask` to v9.
  - Changes dated on the off day up to 7 days after stay as they are. Modeling may take those up
    later as latest-ask-v10 with its own fit.
- The next quarantine version also takes the 8 commercial ads, the 2 Queens ads and the 9 PAD
  move candidates noted in `pending-next-quarantine-notes.jsonl`. No independent
  evidence backs the PAD moves yet, so each needs a second source before it goes in.

## 2026-10-17 03:10 ET

- I reviewed the pipeline's reader PRs #961 to #965, which move latest_ask, descriptions,
  listing_extras, lister and listing_outcomes onto the pipeline's records file. All five merged.
  - On #963 and #964 I first asked for changes: the readers took in 11,336 listings whose latest
    record was a draft and 436 under review. The pipeline added a filter that skips listings the
    ads file marks no_dated_own_active_event, and I approved after the rerun.
  - #963 stores collected_at to the microsecond, which changes the row hash of 1,321,845 rows
    once. I accepted that.
  - #965 counts a still-listed ad's days_listed to the record's last fetch. For a censored
    duration that is the right end point, with still_listed kept as the censoring flag.
- At 00:57 ET an uncapped pyarrow read of the 3.4 GB records file reached 11.6 GB, and the global
  OOM restarted every Remote Control session. Any ad-hoc read of large parquet now runs in a
  `systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0` scope, preferably with duckdb
  from `/data1/apartments/venvs/pipeline`. Bigger jobs run as a `di-*` unit in light slot 1, and
  the pipeline build (#957) waits for those.
- `/data1/apartments/tmp/suspect/api5/screens/merge/pending-next-quarantine-notes.jsonl` holds
  two items for the next quarantine version:
  - cite the same-day twin ad 2580707 as evidence for 2491440;
  - move 2121710 from the latest-ask-v8 correction (21545 to 2150) to an exclusion as
    tenfold_ask_unbacked. Only the ad's own text gives 2,150, which matches the pipeline
    ledger's exclusion in #951.
  Neither is worth a refit alone, so they wait for the next batch of quarantine reads.

## 2026-10-16 15:00 ET

- `bedrooms-ad-v8` (#917) merged. Modeling put it and `pets-from-ad-v2` into the all-scraped fit
  started at 1:35 PM ET (bc7dc099). The NB9 lines are paused, so `quarantine-v33` stays on hold.
- The pipeline wrote its first ads file, `ads-237af093fc58af00.parquet` (2,140,578 ads, beside
  `rows-04fe7ad81836fed2`). It carries coded fields, fates and reasons but no ad text, so a text
  screen still needs the descriptions from the export.
- In that file pet_policy is null on 79% of kept rows. The pipeline's own scan
  (`attribute_evidence.py`) has no pet-fee pattern, so I sent the PET_FEE pattern and the #3E
  correction to the pipeline thread through the coordinator.

## 2026-10-16 13:30 ET

- Ben (12:57 ET, relayed) read any pet fee in an ad as pets allowed in some form. The old pets
  reading set aside "no pet fees" and a pet fee in a list of charges. Rows with a code and such
  wording turned out to be coded allowed in 1,065 of 1,066 cases, which backs his reading.
- I wrote `pets-from-ad-v2` (its file is adfills/20261016-0674409). It fills 1,205 more unknown NB9
  rows as allowed, and leaves every other value the same as v1. It gets used when Modeling's next
  dataset revision picks it up. It doesn't call for a refit by itself.
- #907 fixed the PLUTO releases fetch, which had skipped the Queens lots in the Brooklyn registry.
  I'll rebuild releases at the next registry revision, together with the #905 lot overrides.
- The pipeline thread will write ads-<hash>.parquet next to rows-<hash>.parquet. Rule rounds read
  those two files, in place of new granular runs, once the first one exists.

## 2026-10-16 04:35 ET

I read the 83 held bedroom corrections against independent evidence and merged the result into the
pipeline ledger (#888, owned by the pipeline session).
- For each held correction, `/data1/apartments/tmp/suspect/held83/packets.py` built a packet with
  the row, the unit's other ads and the same-line units. Sonnet readers then judged each one backed,
  refuted or unbacked. 12 came back backed, and the other 71 stay held in
  `ledger-held-2026-10-16-chain.jsonl`. Separately, the pipeline's revised stated-size rule restored
  11 sets it had held earlier.
- 2536308 keeps 2 BR. Ben's floor plan shows 2 BR, and the other ads coded 3 after a conversion.
  The reader had called it refuted. The ledger now tags it `floor_plan`.
- 3691335 (unit 1D, ground floor) stays at 0. Units 2D to 5D are 1 BR, which doesn't settle 1D.
- No `bedrooms-ad-v8` is needed.

The pipeline's ask check (#937) flags ads asking far from their building's median. A Sonnet
reader read the 40 flagged ads with each apartment's other ads
(`/data1/apartments/tmp/suspect/askcheck/reads.jsonl`). From those reads I wrote:

- `latest-ask-v8`: v7 with 5 tenfold typos corrected. Each figure comes from the ad's text or the
  apartment's ad with the same bedrooms within 3 months.
- `quarantine-v33`: v32 plus 5 stores and restaurant spaces, a $33,333 2 bedroom, and the 3
  short-stay offers from the API keep reads.
- `bedrooms-ad-v9`: Trump World Tower 53B and 63B as 3 bedrooms, backed by their other ads at
  2,854 square feet.

Every other flagged ad stays, including the Oriana 3 bedroom at $1,061 and 53 E 64th at $1,200:
only their price looks wrong. Typos without a backed figure also stay. After the merge I tell the
pipeline the v33 and bedrooms-ad-v9 file names, for `ops/pipeline/ledger_import.py`.

#939 merged, and the pipeline's ledger PR #941 imports v33 and bedrooms-ad-v9. #940 added v9's
provenance. Each provenance covers only the rows its own version adds, so a reader walks
`base_rule` back for the earlier rows and their dataset. For 2491440 ($33,333), the pipeline found
a same-day twin ad (2580707 at $338,700) and two price changes to $33,333 seven seconds apart.
I'll cite them in the next quarantine version's entry; the note is in
`/data1/apartments/tmp/suspect/api5/screens/merge/pending-next-quarantine-notes.jsonl`.

On the all-scraped set, furnished, short_term, concession and floors_above_ground are null on every
row, crawl and API alike. pet_policy is null on 80%, hvac_type on 74%, doorman_type on 57% and
elevator on 49%. The pipeline's ads file carries furnished, short_term and concession, so they
come with the step 9 move below.

Step 9 (Ben approved it for the pipeline thread): the pipeline deletes the page-capture rewrite and
the page parser, which it plans for Mon Oct 19. Before that, it opens PRs that move my builders
onto its catalog files, and I review each one:

1. ads file fields;
2. latest_ask and descriptions;
3. listing_extras, lister, listing_outcomes and cohort;
4. granular_slice and granular_export.

Each PR has to show every builder's output hash on the Oct 16 export, before and after, and name
any changed row.

API unit spelling aliases: after unit-labels-v17, 69 history-confirmed groups (339 rows, about 0.1%)
stay split, mostly `4` against `4fl`, `4th` or `2nd-floor`. That's too small to refit for, so
they go into the next unit-labels version.

The pipeline found 12 ads whose latest ask is a tenfold typo, corrected on the ad's last day
(its fix is #930). `latest-ask-v7` (#932) is v6's file with those 12 rows set to the ad's page
price, for Modeling's next all-scraped fit. Two of the rows are in NB9 (2220272 at Helena 57 West,
3281623 at Hudson Landing), and they wait in
`/data1/apartments/tmp/suspect/api5/screens/merge/pending-next-latest-ask.jsonl` for the NB9 lines.
The pipeline's lasting fix to latest_ask.py is #933. A scratch rebuild with it equals v7 on every
row, so no new latest-ask version is needed.

I answered the pipeline session's questions for its whole-city building linking (steps 6 and 7):
- Our fetchers are registry- or box-scoped; only `mnreleases` keeps every Manhattan lot per release.
- The registry override files and `building-joins-v1` serve as known answers. Brooklyn MISJOINS
  serve only as negatives.

## 2026-10-16 00:40 ET

#885 screens the API rows of `DATASET_NB9_API`.
- The ad-fit and Brooklyn screens flagged 822 of the 58k added rows. Sonnet readers read
  them (`config/reviews/ad-fit-reads-20261016-api.jsonl`). I moved 16 non-keep calls back to keep
  and moved the 82 Irving Pl keeps to Brooklyn.
- `quarantine-v32` is v31 plus 118 API rows. `bedrooms-ad-v7` is v6 plus 4 rows
  (426 W 58th 3 to 2, 58 E 1st 0 to 1). `brooklyn.MISJOINS` gains 18 rows. Both screened
  lists name the API cohort.
- `bedrooms-ad-v8` is v7 plus 333 W 56th St #3E as a studio on its 3 rows coded 1, from Ben's
  reading of its floor plan and photos (#917). Not served until the next dataset revision.
- Modeling relabelled its API line q32ad7, on v32 and v7, waiting on #878 and #885.
- Recorded only: a unit-split read (unit-splits-v4 already splits it) and a square-feet read
  (sqft-units isn't served).
- Next: a regex second pass over the 700 keep reads, whose reasons are generic. Also still
  open: the API rows' null fields and the unit spelling aliases on the API datasets.

## 2026-10-15 22:40 ET

The pre-fit prep is done, and I told Ben.
- #874 merged the three Brooklyn sets. Each built in about 9 minutes with no constant columns.
- #878 merged NB9 extended by the API re-read of the page-crawl areas:
  - `data.DATASET_NB9_API` keeps NB9's 296,953 rows and adds 58,146 API rows for listings NB9
    lacks. `cohort extend` built it, skipping Noho and West Chelsea (2,787 rows) and 49
    unit-month duplicates.
  - `latest-ask-v5` covers both crawls. NB9-mw's dataset and `latest-ask-v4` are unchanged.
  - `nb9-nostuy-api-v1` reads the merged registry (7,703 buildings), lot sources under
    `20261016-104dfa2`, the merged extras, and four added description files, one per region-5
    slice, because the whole granular OOMs at 6G.
  - A trial build under the served rules with v5 and `quarantine-v31` kept 354,328 rows, 117
    columns, none constant, in 133 s.
- Modeling queued unitnu4 on `nb9-nostuy-api-v1` third, after whole-floor and the AR twin.
  No whole-floor twins of the API set until that fit wins.
- Open: the added rows have not been through NB9's audit_id-keyed review rules, and about 28
  fields are null for them (furnished, short_term, price_basis, ...).
- Open: the generic screens and unit spelling aliases on the API datasets.

## 2026-10-15 17:30 ET

Four-region API backfill, getting it ready for Modeling's fits. Ben asked for an update when
the pre-fit prep is done.
- The crawl `api-granular-20261015-canonical-url-v1` holds 1.69M ads. It is too big for one
  history build, so I cut it into 16 building slices
  (`/data1/apartments/archive/datasets/api-granular-20261015-building-slices-6064263`, built
  by `rentfrontier.granular_slice`) and built a cohort per slice. Six fit datasets come from
  those: `/data1/apartments/frontier/datasets/api-<region>-analysis-20261015-6064263`, named in
  `data.DATASETS_API`.
- Per-slice descriptions sit in `/data1/apartments/frontier/descriptions/api-<slice>-20261015-dd5bdb5`.
  Listing extras (#857, `--crawl/--tag`) and latest asks for the crawl are under
  `external/listing-extras/20261015-dd5bdb5-api` and `external/latest-ask/20261015-13f5968-api`.
- #858 added retries to the Socrata fetches after 500s and 503s killed them. The Manhattan
  pluto, footprints and lpc were refetched at dec4944. HPD for Manhattan still failed and is
  not needed by the NB9 base.
- #859 added the rule `latest-ask-api-v1` and three sets, `api-manhattan-{below-59th,
  west-59th-110th,east-59th-110th}-v1`. Each takes the NB9 lots2 base without its
  neighbourhoods, adds StreetEasy area indicators against the dataset's largest area, and drops
  base columns constant over the dataset. Modeling has the merge commit (c266ad21).
- The frontage and street-facing terms read only WEST streets and the numbered avenues, so they
  come out missing on the Upper East Side and east of Fifth. A grid-wide version would be a new
  feature set.
- #860 makes the basemap land layer and PLUTO release reads follow the registry's borough.
- Open: the Brooklyn registry (`data-api-registry-brooklyn` unit, `--tag api-brooklyn`), then the
  Brooklyn pluto, footprints, lpc, basemap and plutoreleases, then the three Brooklyn sets.
- Open: the generic screens and unit spelling aliases
  (`api-granular-20261015-unit-spelling-aliases-v2`) on the API datasets.
- Open: the search-API re-read of the page-crawl areas (Ben approved 2026-10-15 3:50 PM ET),
  running as `apartments-streeteasy-reread-crawl-areas` into the region
  `manhattan-page-crawl-areas` of `archive/crawls/api/archive.sqlite3`. Its records need merging
  with the page-crawl records before a fit can use them.

## 2026-10-15 12:30 ET

More misfiled listings: quarantine-v29 (#841) and quarantine-v30 (#842), both merged.
- v29 holds the 2016 and 2019 listings of 1 Fifth Ave #MEWS. Both pages link one floor plan
  image titled 64 Washington Mews. With v28 this unit's four rows under 1 Fifth Ave are all held.
- I looked for plans on the other listings of the 14 history-only groups' units (scratch
  `/data1/apartments/tmp/suspect/dupfp/unitplans.py`). 6 plans in 3 groups turned up, and none
  prints an address, so those groups stay in.
- Of the 684 open duplicate-ad groups, 345 have no shared unit label and buildings more than 10
  house numbers apart. 39 of them ran in the same month at the same rent and bedroom count
  (scratch `/data1/apartments/tmp/suspect/dupad/twinpk.py`, `twins.parquet`). Sonnet readers
  called 4 misfiled, 14 separate apartments sharing copy and 21 undecided
  (`config/reviews/duplicate-ad-twin-reads-20261015.jsonl`). v30 holds 3 of the 4. Review
  dropped 404 E 12th St #2 because the building's other ads describe a new elevator building,
  which contradicts its PLUTO lot (QG, 0 units). The registry join for 404 E 12th St may be
  wrong and is worth a look.
- Open: the other 306 far-apart groups with no shared label, which differ in month, rent or
  bedrooms, and the 339 near-neighbor groups.
- Modeling knew before each merge. It asked that quarantine merges skip 13:50 to 14:05 ET, when
  its 2 PM fits read the queue.

## 2026-10-15, after #839

Floor plans for the history-only groups: quarantine-v28 (#839), merged.
- I fetched the floor plans linked from the stored pages of v27's 18 history-only groups
  (scratch in `/data1/apartments/tmp/suspect/dupfp`; images in
  `/data1/apartments/archive/floor-plans/<listing id>/`). Only 5 listings in 4 groups had a plan.
  Sonnet readers transcribed them into `config/reviews/duplicate-ad-floor-plans-20261015.jsonl`.
- v28 holds 3 rows as location conflicts: 313 W 29th #D, whose plan is titled 339 West 19th
  Street, Unit D, and 1 Fifth Ave #MEWS in 2022 and 2024, whose plan is titled 64 Washington Mews.
  The other two plans carry no address.
- Open: the same 1 Fifth Ave #MEWS unit has 2016 and 2019 rows still in, and listing 2867212
  (2019-09) mirrors 64-washington-mews/twnh 2867438. They need backing other than price.
  14 history-only groups have no plan, and the 684 groups with no shared label or with
  near-neighbor buildings are still unread.
- Modeling knew before the merge and switches its queued NB9 lines to quarantine-v28.

Whole house and full floor indicators: #838, merged as the NB9 feature set
`nb9-nostuy-wholefloor-v1`. Whole house flags 149 rows in 78 buildings, and full floor flags
about 4,380 rows in 938 buildings. Modeling queued it as its own fit on the unitnu4 base. I
predicted a small or null paired LOO gain, with a new-building explained share for the layout
group above the permutation null.

StreetEasy `propertyId` unit merges: closed as negligible. The NoMad probe found 1 rename in
3,384 units, and the API backfill covers no NB9 area.

## 2026-10-15 00:28 ET

Same ad under two buildings: quarantine-v27 (#823), merged.
- I hashed every NB9 ad of 300 characters or more after normalizing its text (scratch in
  `/data1/apartments/tmp/suspect/dupad`; `screen.py`, `pick.py`, `packets.py`, `final.py`,
  `build.py`). 804 hashes appear under more than one building. Most pairs are next-door sister
  buildings sharing a landlord's copy, which costs little.
- `pick.py` keeps groups where a unit label appears under two buildings
  that are not within 10 house numbers on one street. 120 groups and 276 rows remained. Many are
  a dropped or mistyped digit in the address (14 E 23rd filed as 14 E 2nd, 315 W 46th as 315 W
  4th).
- Sonnet readers saw the ad, PLUTO facts for each building and the unit's history in each.
  v27 holds 50 rows, each backed by the address or a landmark in the ad, or by a building that
  cannot hold the unit. 9 of them were in v3 to v9 and released in v10. 70 groups stay in: 18
  decided from unit history alone, 18 that are one building under two slugs, and 34 undecided.
  Reads are in `config/reviews/duplicate-ad-screen-reads-20261015.jsonl`.
- Left open: the 18 history-only groups (floor plans could decide some), and the 684 groups
  with no shared unit label or with near-neighbor buildings.
- Modeling has been told about v26 and v27.

## 2026-10-15 00:20 ET

Midtown West place and use screen: quarantine-v26 (#821), merged.
- Before this, Hell's Kitchen had 2 location conflicts and Hudson Yards had none. I ran the
  `quarantine_v13_screen` terms over both. For far streets I used west streets 1 to 24 or 72 and
  up, plus any east street, because the script's far-street check is set up for Chelsea. That
  gave 422 rows in 391 groups (scratch in `/data1/apartments/tmp/suspect/mw-q`), and Sonnet
  subagents read every group.
- v26 holds 5 rows. Each has backing beyond its own ad:
  - 1330577 (414 W 44th) and 5081524 (438 W 52nd) are location conflicts. Their ad text also
    appears in listings for 411 E 6th #2B and 53 Leroy C1A, and no other listing carries it.
  - 1727387 (461 W 43rd, PLUTO commercial area), 2128488 (unit label OFFICE) and 4300273
    (447 W 36th, PLUTO class O8 with 1 apartment) are offices.
- I kept 10 flagged groups, with reasons in
  `config/reviews/midtown-west-screen-reads-20261015.jsonl`. Two use "Clinton" for Hell's
  Kitchen, six have only the ad text, and one is joined to a vacant lot. The tenth is a Worldwide
  Plaza townhouse with a W 49th St address, which is where those townhouses have their entrances.
- A scan of NB9 text for Queens, Bronx and New Jersey place names gave 13 hits. All of them were
  false alarms, such as an agency's office address or a price comparison.
- Modeling's slopemin3 NB9 fit uses quarantine-v26.

## 2026-10-15 00:00 ET

Brooklyn listings under Manhattan buildings, wider pass: quarantine-v25 (#818) and the screen
change in #819, both merged.
- I widened the screen by hand over NB9 (scratch in `/data1/apartments/tmp/suspect/bk9`; `build.py`
  writes the misjoin entries). quarantine-v25 holds 8 rows as `brooklyn_misjoin`:
  - 7 at `317-east-19-street-new_york`, where seven ads for seven units name 319 and 323 E 19th
    St, Ditmas Park and the B/Q at Cortelyou.
  - 346 E 9th #1R, whose ad describes a four-family house while PLUTO lists 21 apartments.
- I dropped 2961745 (312 E 21st #5H, filed under 344 2nd Ave) from v25 because only its own ad
  backs the Brooklyn reading. Its audit id is in `config/reviews/brooklyn-read-kept-20261015.txt`,
  which `brooklyn.READ` includes, so the screen skips it.
- The registry joins 344 2nd Ave and 317 E 19th St to W1 school lots with 0 units. I don't count
  lot class there as evidence.
- #819 makes `brooklyn.NEAR` match "Ditmas Park", "Prospect Park South" and "Cortelyou Road" on
  their own. On NB9 the only new unread hit was 2961745. The v24 and v25 tests now read their
  lists by file name.
- Modeling has been told about both. It reported that its NB9 queue lines use quarantine-v25.
  #819 changes no rule, so it needs no refit.

## 2026-10-14 23:45 ET

quarantine-v24 (#815, merged) answers Modeling's check of three buildings where NB9 C mixed slowly.
Scratch is `/data1/apartments/tmp/suspect/ess3`.
- 222 E 17th St 3B and 3BB: one Brooklyn ad ("elevator laundry building", Prospect Park South) on a
  lot PLUTO lists as a 4-story, 4-unit walk-up. Both rows are in `brooklyn.MISJOINS`, with a new read
  list. `brooklyn.NEAR` misses "prospect park south location"; widening it is open.
- 318 E 15th St 20C (two listings): PLUTO gives 12 stories, so no 20th floor.
- 4 Perry St 2E stays: nothing beyond the odd label contradicts PLUTO (3 stories, 5 units).
- Modeling was told the rule is ready; 4 rows is negligible, so the refit is its call.
- For building lookups, note that the NB9 registry is `features.NB9_REGISTRY_FILE` with `NB9_PLUTO_FILE`; the
  default `REGISTRY_FILE` covers only the 1,129 old Chelsea and West Village buildings.

## 2026-10-14 23:35 ET

Square feet against the unit's other listings: sqft-units-v1 (#813, merged).
- On NB9 under the current rules, 227 sized rows sit more than 1.5x off the geometric mean of the
  same unit's other sized rows (946 rows past 1.25x, 32 past 2x). Scratch is
  `/data1/apartments/tmp/suspect/sqft9` (`screen.py`, `line.py`, `tight.py`, `final2.py`).
- 43 had a size to take, from at least 2 other listings of the unit or 2 other units of its line
  with the same bedroom count, agreeing within 10%. After the reviewer's points we refused rows
  whose backing repeats one ad's copy, counts a terrace or a total, or whose new size is no nearer
  the bedroom count's median than the recorded one. A Haiku pass and then a Sonnet pass with
  exact quotes read the ads. 12 rows take the new size; every candidate's outcome is in
  `config/reviews/sqft-units-reads-20261015.jsonl`.
- 12 rows is far under `autoselect.NEGLIGIBLE_SHARE`, so the served fit stays eligible and
  Modeling has been told. No fit is needed for it.
- Left open: the 184 conflicts with no backing either way, mostly pairs of two listings. A floor
  plan or a stated size would decide some of them, if the size term ever shows these rows matter.

## 2026-10-14 23:30 ET

Studios above the one-bedrooms (branch `data/bedrooms-ad-v6`): bedrooms-ad-v6 and quarantine-v23.
- `adfit.bedroom_conflicts` now also flags a studio asking more than its building's 1BR median
  plus 0.1 (log rent, after the area adjustment) or more than its 2BR median. On NB9 that flagged
  719 studios outside v4's reads and v22's hold-outs; Sonnet readers read every ad in full. Scratch
  is `/data1/apartments/tmp/suspect/bd6` (`final.py` writes the config files).
- 13 studios take the ad's count: 12 backed by a stated size or another ad for the unit, 1 by the
  plan on the listing's own page (10 plans fetched). Two ads with flex wording ("convertible", "set
  up as") keep 0. Studios with a described bedroom but no count keep 0, as in v4.
- 56 blank or placeholder studios are held out on v22's test (v23).
- The 5 flagged rows left unread after v6 (327 W 21st, The Archive, Casa 155 W 21st, 209 E 4th,
  Hydra Place) were read later: each stays as coded, with 3 matching the code and 2 with no count.
  Reads are in `/data1/apartments/tmp/suspect/bd7/reads.jsonl`.
- The #809 reviewer suggested a stricter size test (size nearest the new count among all levels).
  It would undo most size-backed rows in v4 to v6, such as The Archive lofts at 1,008 to 1,362 sq ft
  and 57 5th Ave, because a size above both medians shows a large unit and not which larger count it
  has. I kept v4's comparison of the coded and claimed counts.
- `text:renovated` misses "remodeled": measured and held (see `docs/TODO.md`).

## 2026-10-14 22:00 ET

Floor plans (branch `data/bedrooms-ad-v5`): bedrooms-ad-v5.
- Ben, 2026-10-15 01:35Z: I may fetch the floor plan images linked from stored pages for listings
  under review, and Sonnet or Haiku reads them. The permission stands for later reviews too.
- Plans live in `/data1/apartments/archive/floor-plans/<listing id>/`. The stored page JSON is
  escaped, so I unescape it before parsing `"floorPlans":[{"key":...}]`; the image is
  `https://photos.zillowstatic.com/fp/<key>-p_e.webp`. Scripts are in `/data1/apartments/tmp/suspect/fp`
  (`find.py` finds keys, `fetch.sh` fetches 10 s apart).
- Of v4's 64 unbacked rows, 15 had linked plans (16 images). A clear plan on the listing's own page
  backs 4 rows. The two Sky 605 W 42nd plans show 1 bedroom, the coded count. Plans from building
  unit pages back nothing, since they may show another period's layout (96 Avenue A #1A changed
  from 1 bedroom to 2).
- Next: the widened check for studios priced above their building's 1- and 2-bedroom rows, using
  the same plan fetch.

## 2026-10-14 21:45 ET

Bedroom review (branch `data/bedrooms-ad-v4`): bedrooms-ad-v4 and quarantine-v22.
- The ad-fit bedroom check (`beds_price_bldg`) flags 1,499 NB9 rows priced out of line with their
  building's other units. Sonnet readers read every one in full, plus 71 rows an earlier draft of
  the screen flagged (1,568 reads remain after v21's hold-outs). Scratch and scripts are in
  `/data1/apartments/tmp/suspect/bd4` (`final.py` writes the reads, corrections and v22 files).
- Ben, 2026-10-15: an ad's stated count needs an independent signal before a count changes.
  `final.py` accepts another ad for the unit with different copy, a stated size nearer the new
  count's median than the coded count's, or a plan, photos or video Ben reviewed. Same-line peers
  don't count, since Ben confirmed 448 W 46th #3FW as a studio in a line coded 1 bedroom.
  Reposted broker copy isn't another ad.
- Result: 22 corrections, 64 stated counts left as coded (bucket d), 146 placeholder studios held
  out in quarantine-v22.
- Follow-up for Modeling: widen the check to studios priced above the building's 1- and
  2-bedroom rows (870 Broadway, 1 Sheridan Sq have no 3-bedroom rows to compare with).

## 2026-10-14 19:20 ET

- **Ad-text fills on master** (Ben lifted the hold at 22:23Z: the fits should work with Midtown
  West included, and the served C may go stale).
  - `elevator-from-ad-v1` (#778, `395d53e7`) fills 6,397 of 296,627 NB9 rows.
  - `pets-from-ad-v1` (#794, `6597bb69`) fills 17,888 NB9 rows on top of it. #782 had been
    stacked on #778's branch and merged into that branch, so #794 carried its diff to master.
    Check a PR's base before merging a stacked one.
  - Both fill files read the cd891c8 NB9 dataset and descriptions. A new dataset needs them
    rebuilt (`python -m rentfrontier.adfills elevator|pets`) and new rule versions.
- Modeling has master `6597bb69`, set nb9-nostuy-v1 and the full rule set for the NB9 C. It
  waits on Ben's go-ahead in its own thread and on the Modal balance.
- **quarantine-v18** (#792, the 110 W 26th thread) keeps v17's 326 rows and corrects the five
  110 W 26th reasons to `quarantine_product_scope`. That thread checks version numbers with us
  before each new version. quarantine-v19 (#800, `e3cfac7d`) holds out 54 more rows from its ad-fit reads; next free: quarantine-v20, unit-labels-v18.
- `data/110w26-release-split` (`510b0eaf`) is dropped. Deleting the branch needs Ben's
  permission, so it still exists on origin.

## 2026-10-14 18:05 ET

- **#789 (merged `50d019ee`): `quarantine-v17`**, the Brooklyn standing filter (Ben). StreetEasy
  files some Brooklyn ads under the Manhattan building with the same number and street name.
  - v17 keeps v16's rows as they are, recodes its 28 Brooklyn rows to `brooklyn_misjoin`, and adds
    7 more (326 rows). NB8 drops 6 rows, NB9 drops 7, both far under `NEGLIGIBLE_SHARE`.
  - `config/reviews/brooklyn-misjoins-20261014.jsonl` records each row's evidence and a candidate
    Brooklyn address for the remap once Brooklyn is collected (backlog line in `docs/TODO.md`).
  - On every new dataset, run `frontier/scripts/brooklyn_screen.py DATASET OUT.jsonl`, read each
    unread hit's whole ad, and add the dataset's cohort to `config/reviews/brooklyn-screened.txt`.
    `test_every_registered_dataset_is_screened_for_brooklyn_ads` fails on any `DATASET_NB9` or
    later missing from that list.
- **110 W 26th St** belongs to its own thread now. Branch `data/110w26-release-split` (`510b0eaf`)
  holds a release of v16's five rows there and a unit-labels-v18 split. It stays unmerged, with no
  PR. That thread finds 4 of the 5 ads give 112 W 26th St, the same tax lot.

## 2026-10-14 14:45 ET

- **`tune-westcoast-split-v2`** swaps v1's names. Modeling found that v1 put each label scheme on
  the wrong BIN, and I confirmed it:
  - the footprints give BIN 1012154 (the-west-coast in the registry) a roof at 122.6 ft and BIN
    1012155 (97-horatio-street-new_york) one at 91.9 ft;
  - floor-and-letter labels run to floor 10, three-digit labels stop at floor 7.
  - v2 sends floor-and-letter rows to the-west-coast and three-digit rows to 97-horatio. The units
    group the same way, so only the building-level features change. Modeling's next split C fit
    reads v2, with no refit on its own account.
- **`building-joins-v1`** (#769, merged) folds StreetEasy's `97-horatio-street-new_york` page into
  the-west-coast at Modeling's request. Ben's floor plans show one complex, and the footprints put
  BIN 1012155 (about 6,700 sqft) inside BIN 1012154's outline (about 52,400 sqft) on the Horatio
  side. The rule moves 8 rows, so the served fit needs no refit.
  - It must run before any `tune-westcoast-split-` rule, and `apply_rules` raises otherwise.
    `autoselect._rule_order` sorts it first by name.
  - Under v2 the page's other labels ("7", "26") now join the-west-coast.
- A v3 split, which would give the three-digit wing a group name of its own mapped to BIN
  1012154, waits on Ben's answer. I haven't written it.

## 2026-10-14 11:15 ET

- **#758 (merged `75b7d1a4`): `latest-ask-v3`.** StreetEasy numbers sales and rentals
  separately, and the crawls capture both, so 1,653 ids belong to a sale and a rental.
  `latest_ask.py` and `listing_extras.py` took an id's last capture of either kind, and on 210 NB8
  rows that was a sale. Both builders now keep rental records only, like `lister.py`.
  - `latest-ask-v3` reads `/data1/apartments/external/latest-ask/20261014-9ae2b6e/` and moves 92
    rows to their last rental ask (median 4.4%, at most 23%). That is under `NEGLIGIBLE_SHARE`, so
    no refit. Modeling was asked to list v3 on its next latest-ask fit.
  - Rebuilt extras `listing-extras/20261014-9ae2b6e` differ from `NB8_EXTRAS_FILE` on some NB8
    rows (outdoor types 86, room count 170). The nb8 sets keep the hashed file. A set reading the
    new file needs a new name.
- **Midtown West (still held for Ben's opt-in; no PR).** Branch `data/nb9-midtown-west`, head
  `2496aae4`, worktree `/data1/apartments/tmp/suspect/wt-mw`, master merged through #758.
  - `areas.py` takes a crawl argument (`SPLITS`); areas `20261014-cd891c8` split Hell's Kitchen
    (1,116 buildings) from Hudson Yards (234).
  - `DATASET_NB9` (296,953 rows), NTA and lister `20261014-cd891c8`, blocklots `20261014-5352472`,
    `NB9_EXTRAS_FILE` `listing-extras/20261014-717ad9c`, `latest-ask-v4` (v3's rows unchanged plus
    Midtown West's).
  - Sets: nb9-nostuy-v1, -sizefill-v1, -nta-v1 (NB8 folds; no new fold needed), -lister-v1. All
    build on current rules with no NaN or constant columns. Tests in `test_nb9.py`.
  - Still missing before a fit: Midtown West unit-label merges from Data collection's alias table
    (`midtown-west-granular-20261014-unit-spelling-aliases-v2`), a quarantine and price-screen
    read, and an nb9 riverparks twin.

## 2026-10-14 10:30 ET

- **#745 (merged `625fb9e0`): `tune-westcoast-split-v1`.** It splits The West Coast (95-97
  Horatio, lot 1006430001) by label scheme: floor-and-letter labels go to the registry building
  `97-horatio-street-new_york` (BIN 1012155), three-digit labels to `the-west-coast` (BIN
  1012154). The rule must come before the unit rules in a run's list. No ground truth places a
  unit in either structure (ads, DOB and the mixed 97-horatio rows), so it stays a tuning rule.
  Modeling fits it through modalq-c.
- **Full suite on master `ba9cb6d4`:** the 3 GB single-process run hit the OOM killer at 44%.
  One file per process under 6G, all 66 frontier test files pass.
- **Midtown West (held for Ben's opt-in; the coordinator is asking).** Built, nothing on master:
  - history `midtown-west-history-20261014` (as_of 12:20Z: the builder refuses a cutoff before
    `complete.json`'s finished_at, 12:19Z; the last capture is 11:09Z), analysis cohort
    `midtown-west-analysis-20261014-ca9dbf6e` (81,797 rows, 1,247 buildings, 37,727 units),
    descriptions `midtown-west-20261014-ca9dbf6`, covariates `/data1/apartments/tmp/suspect/mw/buildings.csv`;
  - registry `20261014-ca9dbf6` and the merged NB9 snapshots at `20261014-5352472` (registry,
    pluto, footprints, basemap, hpd, lpc, storefronts, plutoreleases, parks, blocklots);
  - no building, unit, listing or audit id overlaps NB8.
  - Building page titles put every building in Hell's Kitchen (64,675 rows) or Hudson Yards
    (17,122), the plan for its `neighbourhood` values, as Flatiron and Gramercy Park were split.
  - Left for the NB9 PR (code): `listing_extras.CRAWLS`, lister, NTA, the descriptions source,
    the combined dataset, `DATASET_NB9` and the nb9 sets. Scripts in `/data1/apartments/tmp/suspect/mw/`.

## 2026-10-14 05:55 ET

- **#730 (merged `bcaac064`):** `latest-ask-v2` reprices every NB8 row at its listing's latest
  on-market ask, from `/data1/apartments/external/latest-ask/20261014-003dd7d/latest-ask.parquet`
  (`python -m rentfrontier.latest_ask`, clean tree only). 79,791 of 215,156 rows change, median
  4.9%. It supersedes `tune-latestask-v1` (#706) and `tune-finalask-v1` (#700/#704); the
  reconciliation by cause is in the PR body and `docs/analysis/latest-ask-2026-10-14.md`.
  - Placeholders: a change on or after the off-market day is skipped when more than 2x or under
    half the ask before it, or a raise of over 20% to exactly $10,000. If the screen turns up
    another typed placeholder value, extend `record_latest` in a new builder build and a
    `latest-ask-v3`; keep v2's file as it is.
  - `quarantine-v13` = v12 + 2 rows from `frontier/scripts/price_mismatch_screen.py` (factor over
    3 against both unit and building leave-one-out medians); the 11 rows over 2.5 are in the read
    list.
- Ben (2026-10-14): price may be used to detect anomalies; data corrections toward a known ground
  truth merge without waiting on model updates; no refit for negligible data changes. The latent
  per-apartment ask model is a backlog item in `docs/research-plan.md` (#732), not current work.
- Modeling's C refit runs under `latest-ask-v2` and `quarantine-v13`; Modeling owns the queue and
  Ben's fit hold still applies to this thread. The Repo state cleanup thread stacks
  `quarantine-v14` and `unit-labels-v16` on #730. The per-event price table and a pets-from-ad
  rule were both dropped.

## 2026-10-10 21:05 ET

- **Pre-registrations (#672, merged `49d6c1c6`):** predictions for retail, noise, trees, crime, hpd
  and petsfill are in `docs/model/predictions-nb8-data-2026-10-10.md`, following the Fable review's
  framework. When Modeling sends results, score each fit against its prediction: paired ΔELPD ± SE,
  whether it clears ~2 SE, and medians with intervals.
- **21 W 12th (Ben, via the coordinator):** the mixing failures are model-side. It is a two-tier
  townhouse with 34 of 36 sizes missing, and C mixes it. The one real defect was a single apartment
  listed under four labels (2, 2B, 2F, 2R).
- **#687 (merged `e76570bb`):** fixes that defect by amending `unit-reviews-v1` in place, by Ben's
  decision ("treat it as the same dataset"). There is no v2.
  - Runs that recorded the old file's hash rebuild with it, as the hidden rule
    `unit-reviews-v1@20261007` (`data.RULE_AMENDMENTS`, `data.amended_rule`).
  - Ledger: `docs/data/rule-amendments.md`. Use the same mechanism for any future in-place amendment
    Ben asks for.
  - Both Modeling sessions were told before and after the merge.
- #542 (quarantine-v11) stays held.

## 2026-10-10 15:45 ET

- Ben (19:07Z, 19:16Z) asked for the structured pet field to be updated from the description text.
  The prompt was 225 W 12th: its pets field is coded unknown on 76 of 79 rows, but its ads say
  "no dogs". For pets only, this is an exception to the 2026-10-04 rule that ad text must not
  override coded fields.
- #666 `nb8-nostuy-petsfill-v1` (merged, `bf2937a0`):
  - Classifier: `petstext.classify` sorts ad text into no_pets, no_dogs, case_by_case, allowed or
    none, with the most restrictive class winning. It does not read "no pet fee(s)/deposit(s)" as a
    ban, and it reads a size limit as case by case.
  - Building fill: `asof_pets` falls back to the building's latest class from strictly earlier days.
  - Overlay: `overlay_pets` keeps a known code, except that "allowed" becomes `no_dogs` when the
    row's own ad says no dogs. An unknown code takes the mapped text class (allowed, approval_required,
    not_allowed, or a new `no_dogs`).
  - Effect: unknown pets falls from 171k rows to 50k. The model gains one column, `pets=no_dogs`.
  - Status: I sent Modeling the set name and SHA, and they queue it after the amenlevel fits.
- Measurement: where the coded field is known, the text agrees on 43k rows. It is more specific
  (allowed vs cats only) on 30, and contradicts it on none.
- #663 (the version with parallel columns) is closed. #666 also added bigbed and amenlevel to
  `NB8_ONLY` in test_nb8.py, which Modeling asked for.
- Possible v2 for pets: a place phrase such as "no pets above the store" reads as case by case
  (rare). Descriptions are the last captured text.

## 2026-10-10 13:20 ET

- #645 `nb8-nostuy-hpd-v1` (merged, `3be06e9d`): `hpd_v1` (Class B and C housing-code violations in
  the past year, per apartment, "a few" or "many") on the nb8 base. It reads the HPD snapshot
  `/data1/apartments/external/hpd/20261010-b5c71cf`, which was fetched for the NB8 registry.
- #651 `nb8-nostuy-elevfill-v1` (merged, `e49d9e5d`): `elevfill.asof_elevator` fills an unstated
  elevator with the building's latest stated value from strictly earlier days, and the base is rebuilt
  on the filled field, with an indicator for filled rows. elevator=unknown goes from 43% to 18% of
  rows and elevator=no from 7% to 29%. I told Modeling this is the nb8 set most likely to move LOO.
- Modeling now has seven nb8 sets: lines, retail, noise, trees, crime, hpd and elevfill. I told
  Modeling each set name and SHA.
- Dropped: an nb8 walk-up hinge (`walkup_v1`). The base already has `log_floor_x_no_elevator`, and
  the hinge is non-zero on only about 1.5% of rows.
- Next ideas: doorman could be filled the same way (31k rows have an earlier stated value), but the
  stated values are mostly "virtual", which is ambiguous, so it is held. The other nb5 sets not yet on
  nb8 are loc, parks, water and unical.

## 2026-10-10 11:05 ET

- Merged two more nb8 feature sets, each its own PR on the `nb8-nostuy-v1` base, with no rule changes:
  #642 `nb8-nostuy-trees-v1` (`trees_v1`) and #643 `nb8-nostuy-crime-v1` (`crime_v1`, master
  `ed40acad`; `CRIME_FILE` covers every nb8 registry building). I told Modeling both set names and SHAs.
  Modeling now has five nb8 sets to fit: lines, retail, noise, trees and crime. Modeling owns the
  queue, and the sets wait on its #641 base (Modal) and the gate.
- The 423 E 12th rear rule is withdrawn. A general rule (lots with at least two footprints, one set
  back from the curb, `R`-labelled units) would move 742 rows in 70 buildings. But `R` units elsewhere
  are not smaller than the building's other units (median size ratio 1.01), so `R` mostly means
  rear-facing, not a separate rear building. 423, the-west-coast and the-everett-building are model
  issues (size filled from the building median across two size clusters), and Modeling has them.
  The script is `ev/rear4.py`; the setback cache is `ev/fp_setback.parquet`.
- #542 (quarantine-v11) stays held.

## 2026-10-10 10:05 ET

- **#636 (90f03f5):** `fetch_noise` pages each year by `$offset` in `unique_key` order. A year with
  more than 50k complaints no longer stops the fetch.
- **#638 (0e3d4a6e) `nb8-nostuy-noise-v1`:** `noise_v1` on `nb8-nostuy-v1`, reading
  `NB8_NOISE_FILE` (noise311/20261010-90f03f5, 642,911 complaints, boxed on the nb8 registry).
  - Street/nightlife mean: EV +0.89 doublings, GV +0.60, Chelsea −0.56, Gramercy −0.82.
  - Per Modeling's message (about 10:00 ET), the set is in its test queue behind lines and
    retail. Tests start only once a base passes the gate, and Modeling says each launch needs
    Ben's OK. #638 itself queues no fit.
- **Terms:** the nb8 base is `nb8-nostuy-v1`, the 8-area base set. The sizefill base is the
  candidate base with `sizefill_v1` (`sizefill.asof_size`: size as of the day, from the unit,
  the line or the building).
- **423 E 12th St:** Modeling reported that the nb8 base fit failed the group gate with R-hat 1.48,
  mostly from this building, and asked for a label check. My checks are below; the scripts are
  in `/data1/apartments/tmp/suspect/ev/` (`b423b.py`, `b423c.py`, `rear.py`).
  - Lot 1004400048 holds two buildings: BIN 1076986 at the front (42.7 ft) and BIN 1076987 at the
    rear (34.9 ft). The registry maps the address to the front BIN only.
  - Labels are clean: front `1f`–`4f` (~800 sqft, $4–5.5k) and rear `1re`–`4re`, `1rw`–`4rw`
    (~300 sqft, $2–3k). The 0/1BR flips are on the rear units.
  - Not a stabilized mix: 4 stabilized units in 2007, 1 in 2015–18.
  - Sizefill gives most rear rows 300 from the unit or line. Early rows get the building median.
  - Candidate rule, decided by labels and footprints and never by rent: on lots with ≥ 2 footprint
    BINs, rear-labelled units (`r`, `re`, `rw`, `rr`, `rear`) become `<building>-rear`. It covers
    21 buildings and 205 rows.
  - It needs registry rows for the rear buildings, since features reindex the registry by slug,
    plus new nb8 sets. Held until the sizefill base reports (Modeling's estimate: about 14:30Z). Build it only
    if 423 still fails, and tell Modeling before merging.
- **the-west-coast (521 West St):** Modeling reported a narrow gate failure here. My checks
  (`westcoast.py`, `zeropad.py`) found no data fault. I called it a model issue, and Modeling took it.
  - PLUTO lists 2 buildings. The footprints list both BINs on the lot: 1012154 at 122.6 ft and
    1012155 at 91.9 ft, both built in 1930.
  - It mixes 3-digit and floor-letter labels. Zero-padded aliases are already merged by
    unit-labels-v15, all but 7.
  - Only about 10% of rows are sized.
- **Next:** the 423 result from sizefill. Then trees on nb8, if worth a test.

## 2026-10-10 09:45 ET

- **Runs resumed (Ben, via the coordinator).**
- **Coordinator note, 12:46Z:** Modeling owns the fit queue and runs our sets one at a time on the
  nb8 base. We queue no fits. Message Modeling with the set name and merge SHA when a set merges,
  and before any rule merge.
- **#630 (a533dd0) `nb8-nostuy-lines-v1`:** `lines_v1` on `nb8-nostuy-v1`.
  - 27% of East Village rows have no line within 8 min (Chelsea 12%, WV 11%).
  - The nb8 registry prices the J/Z.
  - `tests/test_nb8.py` has an `NB8_ONLY` set for sets without an nb7 twin. They still get the
    snapshot asserts.
- **#632 (31b6a05) `nb8-nostuy-retail-v1`:** `retail_v2` reads `STOREFRONTS_SNAPSHOTS[id]`, and
  `run.feature_sources` records that path.
  - `retail_v1` reads `STOREFRONTS_FILE` (20261006), which mostly misses EV, NoMad and Gramercy.
    Median storefronts within 150 m: EV 5 vs 39, NoMad 3 vs 44, Gramercy 0 vs 23.
  - The NB4/6/7 storefront snapshots were never read. No base set reads retail, so served and
    base fits are unaffected.
- **Dropped:**
  - DOB certificates of occupancy: EV has 3.1% of rows in buildings with yearbuilt ≥ 2010,
    against Chelsea's 13.1%, so #608's picture holds.
  - East River Park closures: 37 rows.
- **Coverage audit, no fit:** the nb8 base reads only nb8 snapshots. The trees, crime and noise
  files cover EV. Points in a ~150 m box around EV buildings: median trees 340 (Chelsea 281),
  felonies 2,214 (2,269), noise 311 calls 9,180 (6,047). Only 2% of EV buildings, at the south
  edge, are outside the noise file's box. So only retail had the gap.
- **Next:** nb8 twins of the quiet (noise) and trees terms if they are worth a test on EV. `lines.py`
  and `retail.py` docstrings are stale (J/Z priceable on nb8; per-set storefronts). Leave them:
  editing changes the module hash.

## 2026-10-10 08:45 ET

East Village opt-in, as relayed by the coordinator on 2026-10-10 at 07:27 ET. Builds only: no
fits while Ben's run pause holds. Modeling was told before each rule merge, has the SHAs, and
plans its base fit as `nb8-nostuy-v1` on the final rules once Ben lifts the pause.

- **Quarantine v12, #622 (c1b2e6c).** Adds the staged NoMad rows, East Village's screen rows and
  the held Harlem row.
- **Unit labels v15, #624 (94d308d).**
  - The alias table `wv-gv-fgp-stuy-nomad-ev-20261010.jsonl` is v14's 2,807 lines unchanged
    plus 1,162 East Village rows. Only the 405 history-confirmed groups are mapped, per the
    relay.
  - The history pairs (`history-20261010.jsonl`) add 448 EV pairs.
  - On the NB8 rows, 359 East Village rows change unit (84,134 units become 83,992).
  - The served fit stays eligible: same_rows is True against c1b2e6c.
- **NB8 sets, #625 (cb38e88).**
  - `data.DATASET_NB8` (`...-nomad-ev-analysis-20261010-3ebfea0`) has 215,156 rows: NB7's
    148,673 plus East Village's 66,483.
  - The sets are `nb8-nostuy-v1` plus the sizefill-v1, nta-v1 and lister-v1 twins, on rule base
    nb5-plutoasof-v3. Per-area snapshots are at 20261010-b5c71cf.
  - `NTA_FILE`, `BLOCKLOTS_SNAPSHOT` (20261010-c90ddbd) and `LISTER_FILE` (20261010-b5c71cf)
    are supersets that keep the nb7 rows unchanged.
- **NTA folds (Modeling's review).** `nb8-nostuy-nta-v1` uses the new `nta_v2`, which folds the
  Stuy, East Village and Greenwich Village NTAs into the Chelsea-Hudson Yards reference.
  - East Village's NTA level equalled the EV indicator.
  - The West Village and Greenwich Village NTA levels summed to those two neighbourhoods'
    indicators. `nb7-nostuy-nta-v1` still has that ridge (its code is hashed).
  - A test checks the NTA levels, neighbourhood indicators and intercept are independent on the
    NB8 rows.
- **No nb8 twins:** stab, stabopen-v2 and explain were left out (not in the post-pause plan).
  Riverparks was also left out: the new park Pier 42 makes `parks.places` raise because
  `riverparks.OPENED` doesn't date it.
- **Next:**
  - A new module dating the East River parks: Pier 42 finished 2024-07-03 (interim use from
    2013-05-04); East River Park closed for reconstruction from 2021. Then the nb8 riverparks
    twin.
  - #542 (quarantine-v11) stays held.
- **Scratch:** `/data1/apartments/tmp/suspect/ev/` (`smoke8.py`, `smoke8rank.py`, `elig15.sh`,
  the PR bodies). The `ext*.sh` scripts built the EV externals.

## 2026-10-09 13:45 ET

NoMad opt-in, as relayed by the coordinator at 09:13 ET. Builds only: no fits while Ben's run
pause holds. Modeling was told before #611 merged (the only rule change) and after #615.

- **Unit labels v14, #611 (59f03bf).** Adds the NoMad alias table and history pairs: 107 of the
  113 groups, the history-confirmed ones. The served fit stays eligible: `autoselect.eligible`
  returns the same set on master and the branch.
- **NB7 sets, #615 (3baf5cb).** `data.DATASET_NB7` (`...-nomad-analysis-20261009-d3b4050`) has
  148,673 rows: the NB6 rows (139,387) plus NoMad (9,286 rows, 171 buildings, 3,157 units).
  - The sets are `nb7-nostuy-v1` plus the stab-v1, stabopen-v2, explain-v1, riverparks-v1,
    sizefill-v1, nta-v1 and lister-v1 twins. All are on rule base nb5-plutoasof-v3, and all 8
    build in 275 s with no NaN columns.
  - Per-area snapshots are at 20261009-dcee63b.
  - `NTA_FILE`, `BLOCKLOTS_SNAPSHOT` and `LISTER_FILE` now point to supersets that keep the NB6
    rows byte-identical. Only the nb6 source hashes change.
  - Smoke script: `/data1/apartments/tmp/suspect/nomad/smoke7b.py`.
- **Quarantine screen v13, #618 (cefc1bf).**
  - Screened areas: Chelsea, West Village, Stuyvesant Town and NoMad.
  - When a far NTA part is also a word in a screened building's name ("madison-parq",
    "kensington-house", West Village's Bedford St buildings), it matches only with its borough
    or inside the far NTA's whole name and short forms (Bed-Stuy).
  - Compared with v12 it drops 22 false positives and adds none.
  - Use it for East Village. Add EV's centre to `CENTRES` and its description source to the
    `SOURCES` tuple.
  - Reviewer nit, not fixed: when two far NTAs share a dropped part, only the first gets its
    whole-name spellings. Today only Bedford-Stuyvesant does.
- **v12 staging.** 10 NoMad rows are in `/data1/apartments/tmp/suspect/nomad/screen/v12-nomad-staged.jsonl`:
  3 location conflicts, 3 non-residential and 4 short-term. The reasons for the 40 kept are in
  `NOTES.md`. Hold them with the Harlem row until East Village lands.
- **Checked, no change:**
  - Beds and baths: the disagreements are building boilerplate, so the coded fields stand.
  - Boundary: Flatiron covers 14th–25th St and NoMad 25th–31st; they share only 25th St.
- **Surprises:**
  - The 69th Regiment Armory (unitsres 0) has 3 rows.
  - 6 buildings have placeholder BINs.
  - NoMad is 84% Midtown South-Flatiron NTA, with a low stabilized share.

## 2026-10-08 21:50 ET

Research-review items, relayed by the coordinator at 20:26 ET. Frame and data only; no fits while
Ben's run pause holds. Modeling has been told about each new set.

- **1. Concessions by building size:** checked; answered in the thread.
- **2. Lister type, #600 (08d4767).** Set `nb6-nostuy-lister-v1`
  (snapshot lister/20261009-24e19c9).
- **3. `first_listing_of_unit`:** already as-of; nothing to change.
- **4. Sqft completeness, #602 (c1d47e2).** `sizefill.py` and set `nb6-nostuy-sizefill-v1`:
  a size from the row itself, else from the unit's, then its line's, then
  its building's earlier rows, with a source flag.
- **5. 2020 NTAs, #603 (25f343d).** `nta.py` and set `nb6-nostuy-nta-v1`
  (snapshot nta/20261009-a944359).
- **6. Dated parks, #604 (11e9abe).** `riverparks.py` and set `nb6-nostuy-riverparks-v1` on
  nb6-nostuy-v1 (snapshot riverparks/20261009-6f20a5f). Its three terms:
  - log walk minutes to the nearest park, which now includes the Hudson River Park esplanade
    (2003-05-30);
  - High Line within 5 min;
  - river-pier park within 10 min: Little Island 2021-05-21, Pier 57 rooftop 2022-04-18 and
    Gansevoort 2023-10-02.

  A place counts from the month after it opened. `parks.py` is unchanged; Andrew Haswell Green
  Park is dated 2023-12-19 in the module. The pier term covers 16% of 2024–26 rows.
- **Floor-plan OCR:** blocked. The crawls kept only image keys, fetching images from StreetEasy
  needs Ben's OK, and tesseract isn't installed. Asked Ben; nothing paid runs meanwhile.

## 2026-10-08 19:15 ET

- **Open share v2, #572 (8d5de8b).** Sets `nb6-nostuy-open-v2` and `nb6-nostuy-stabopen-v2`
  (the v1 sets are not to be fitted).
  - Lots are joined into a union when a lot's MapPLUTO point lies in another lot's footprint on
    the block, built by the listing year, using the new `blocklots` source
    (blocklots/20261008-d93eec2: 5,814 lots on 219 blocks).
  - The covered area counts the union's footprints; the denominator is the union's lot area.
  - Up to 1.10× (OPEN_SHARE_OVERHANG) reads as 0 open; above that the share is missing and
    `open_lot_share_unknown` is flagged.
  - Real data: unknown 96, zeros 286, Stuy 0.74, median 0.24.
- **Single-owner complex, #575 (851e71b).** Sets `nb6-nostuy-owner-v1` and
  `nb6-nostuy-explain-v1` (stabopen-v2 plus the owner flag).
  - A building is flagged when one normalised DOF owner name holds at least 3 buildings and 300
    units on its block. Placeholders and billing lots (lot ≥ 7501) are excluded.
  - 73 listing buildings: Stuy 38, PCV 19, London Terrace 10, Penn South 2, Maestro 2,
    NYU 110 Bleecker 1, NYCHA 1.
  - Today's owner is applied to every year; the ledger notes this limit.
- **Dated owner: checked, not built.** I pulled `mnreleases` (#580, 4eb5659):
  - every Manhattan lot in all 44 archived MapPLUTO releases, at
    mnreleases/20261008-049237a, 1.89M rows;
  - owner names, units, buildings and State Plane coordinates (latitude/longitude only from
    20v1);
  - 22v2 has no publication date and is never read.

  Per release, the owner rule flips only on record noise: NYCHA name variants, a 375→36 unit
  drop, a split Penn South name, a one-release blip at 95–97 Horatio. Maestro is flagged from
  15v1, the year after it was built. So today's owner leaks nothing real (comment on #575).
  Modeling was sent the path for its new-supply vs bedroom-curve check.
- **On resume** (model runs paused, Ben 16:07Z): Modeling compares `nb6-nostuy-explain-v1` and
  `nb6-nostuy-stabopen-v2` against the reference `nb6-nostuy-v1`.

## 2026-10-08 18:00 ET

- **Stuy Town indicator replacement sets (builds only, nothing queued).** Each candidate goes in
  place of the indicator on `nb6-nostuy-v1` (no indicator; its rows take Chelsea's level):
  - #562 (81d6f1e) `nb6-stab-v1` (stabilized share beside the indicator), `nb6-nostuy-stab-v1`.
    The share is year-before DOF bill units over MapPLUTO units; a bill counts for at most 3 years
    (`STAB_CARRY_YEARS`, the reviewer's fix). The snapshot was re-fetched at
    rentstab/20261008-b487c8a, with the same rows as 6b42fe8.
  - #567 (3e3a538) `nb6-nostuy-open-v1` (lot's open share), `nb6-nostuy-stabopen-v1` (both).
    Open share = 1 − footprints built by the listing year ÷ MapPLUTO lot area, clipped to [0, 1].
    Stuy 0.73, PCV 0.75, Penn South 0.84, median lot 0.24. About 10% of buildings clip to 0
    (a footprint spanning lots), which is a measurement error. Fix it before fitting (coordinator
    relay 21:56Z): use the union of the lots sharing a footprint, else leave it missing with a
    flag. A building demolished later is missing (a small leak). `footprint_area` rebuilds the
    grid per footprint (about 15 s).
  - On resume (Modeling and Ben plan it): after the nb6-plutoasof-v3 base, compare
    `nb6-nostuy-stabopen-v1` and the single-term sets with the base; `nb6-nostuy-v1` is the
    reference. Age and type are in the base (building era, class, log units). Single
    ownership is not: try a "large single-owner complex" indicator from a public owner field
    (HPD registration or DOF owner name).

## 2026-10-08 17:30 ET

- **Stuy Town rent-blind screen: no rule yet.** `/data1/apartments/tmp/suspect/stuy/screen/`
  (`screen.py` runs quarantine_v10_screen's checks with the centre moved to 1st Ave and E 20th St,
  rules with unit-labels-v13). 3,628 rows give 56 hits, all far_place. 55 are "in stuyvesant"
  (Bedford-Stuyvesant's NTA part). For the EV/NoMad screen, change the check (not a row pick): a far
  name that is part of a local name (Stuyvesant Town) must match only in its full NTA form. One is real: audit
  `50f8ccd4…` (listing 2595533, 312 1st Ave, 2018-12), an ad for "beautiful studio in Harlem".
  Hold it for the next quarantine version with the EV and NoMad screens; tell Modeling first.
- **Stuy Town ad fixes: none.** The ads' bedroom counts agree with the coded ones, except "convertible
  2BR" and "1 bedroom flex" ads, where the coded count stands (ad text doesn't override). 46
  rows on 14 units are 5 bed / 2 bath in every listing from 2014 to 2025, so they are taken as real.

## 2026-10-08 16:45 ET

- **Stuyvesant Town/PCV (coordinator relay 20:04Z): builds only, no fits.**
  - #557 unit-labels-v13 merged (365cbc8): v11 plus Stuy Town's 535 alias rows and 276 history
    pairs. Not in the current rules (CR still has v11); Modeling plans it with the NB6 base.
  - #558 (approved; suite running) adds DATASET_NB6 (139,387 rows, 3,628 Stuy Town), the NB6_*
    snapshots, `PLUTO_RELEASES_SNAPSHOTS`, and nb6-plutoasof-v3 (nb5-plutoasof-v3 plus a Stuy Town
    indicator). Modeling has the dataset path; the NB6 base fit and FRONTIER_DATASET reset are
    theirs to plan with Ben on resume.
  - Registry: StreetEasy gives the complex one centroid, so 43 pages are geocoded from their own
    slug address (`config/reviews/registry-overrides-20261008-stuy.json`). 346 and 330 1 Avenue
    share BIN 1082865.
  - Not fetched for NB6: noise311 (a year fills a page; split the query) and places (Overpass
    504). Needed before any nb6 noise or places set. An nb6 parks, places or HPD set also needs
    its own PARKS/PLACES/HPD_SNAPSHOTS entries (the NB6 loop doesn't copy those).
  - Floors: "10H"-style labels already read as floors through `row_floor`. The remaining 23% of
    Stuy Town rows are "M"/"0M" units (743) and "0T" (82), with no floor in records or ads. Left
    unknown; no rule.
  - **The Stuy Town indicator is a placeholder** (coordinator, 20:38Z, after Ben's 16:16Z
    preference). Candidates to replace it: the rent-stabilized share (DOF bills: lot 1009720001 has
    8,634-8,770 stabilized units a year since 2011, lot 1009780001 about 2,480, close to all units),
    one landlord, campus open space, building age and type. nb5-stab-v1 was null (#435) on five
    neighbourhoods, but Stuy Town is the first near-all-stabilized complex in the data.
  - Next: rent-blind quarantine screen for Stuy Town, ad-based fixes, then an nb6 stab test.
- **Light and air: null.** The within-building residual slope for the share of facade clear above
  facing roofs is +0.96% ± 0.16% (all sides), +0.4% ± 0.25% (own windows); floor and facing
  terms already carry it. No set. Scratch: `/data1/apartments/tmp/suspect/light/`.
- **Places map and subway timetable: already dated where it matters.** STOP_OPENED gives
  34 St–Hudson Yards from 2015-09-13. The model reads the weekday-morning timetable, and the
  L-train work was nights and weekends. Places OPENED covers Lenox Health (2014-07) and the
  Gansevoort dog run (2023-10). Drop-in centres are undated, and St. Vincent's closed in April 2010.
  Neither source is in the base.
- **#554 merged (8e40d3f):** final_ask, n_cuts and days_listed on the frame, never features.

## 2026-10-08 15:47 ET

- **Model runs are paused** (Ben, 16:07Z: "Let's pause model runs. I want to collect more data
  (in progress scrapes) before doing more iterations"). Builds go on; Modeling holds a resume
  queue. When the NoMad, East Village and Stuy Town scrapes land: neighbourhood splits, rent-blind
  quarantine checks, ad-based fixes. Tell Modeling before merging any rule change.
- **Explanatory single-feature sets** (Ben, 16:16Z: explanatory features over neighbourhood
  premiums), each on nb5-plutoasof-v3 and queued by Modeling for the resume:
  - #539 nb5-trees-v1 (a90fbea): street trees within 100 m, latest census published + 7 days.
  - #548 nb5-crime-v1 (053277a): felonies within 250 m reported in the year before the
    listing's New York day (`rentfrontier.crime`, table 20261008-c17e0ae).
  - #552 nb5-hpd-v1 (140a44b): hpd_v1's past-year building condition from `NB4_HPD_FILE`
    (five neighbourhoods; it had been unread). Retests the September Chelsea/WV null.
  - Left: light and air. Schools stay deferred.
- **#543 claims (840cf57):** nb5p3-claim-v1 and nb5p3-claimnolabel-v1, the area an ad says it is
  in, on both sides of the location/label split. Queued.
- **Concessions: no drop rule.** StreetEasy coded concessions from 2020, and the cohort drops
  those listings; before 2020 only ad text records them (5.6% of rows match the flag). Modeling's
  no-fit check: text:concession is −1.1% in the served fit and flagged residuals are under 0.3%,
  so the asks are mostly gross. Of 4,785 "net effective" ads, 366 ask the figure next to the
  phrase (about 0.27% of rows), too few for a rule. #551 nb5-concera-v1 (9631c96) adds the flag
  for 2020 on beside the base's. Queued. Scratch: `/data1/apartments/tmp/suspect/conc/`.
- **Held:** #542 quarantine-v11 (approved) until Modeling's v10→v11 swap fit passes. #478 permit:
  suite passed 472; merge only if its fit wins.
- **Coordinator relay items still open:** final_ask, n_cuts and days_listed on the frame (never
  features); date or restrict the places map and subway timetable to 2010; first_listing_of_unit
  against year (replace with log_months_since_last_listing if it moves).

## 2026-10-08 10:58 ET

- **#523 nb5-plutoasof-v3 merged (b8b7e44).** This is point-in-time MapPLUTO, per Ben's
  13:59–14:07Z directions relayed by Modeling: "Serve plutoasof-v3 on passing the gate, as the
  new base."
  - nb5-coded-v2 plus every field from the latest release with published + 7 days ≤ the
    listing period (`released_lots` in features.py), falling back to the earliest release.
  - Today's values stay for yearbuilt, location and address, for fields a release lacks, and
    for releases older than the building.
  - Snapshot `/data1/apartments/external/plutoreleases/20261008-bdb9e67/`: 44 releases, 3,406
    lots; provenance.json holds each date's primary source and URL.
  - Dates are the server Last-Modified unless it is the 2023-10-15 re-upload; otherwise the end
    of the month after the release's own documents. 22v2 is undated, flagged and never read.
  - On the latest split, features change on 27,564 of 135,540 rows beyond the uniform
    re-centring shift.
  - Later sets inherit the dating via `NB4_SETS[x] = "nb5-plutoasof-v3"`.
  - v2 is dropped unfitted. Modeling queued `frontier-modalq-pluto3` (launches about 13:15 ET)
    and will send the gate result and ΔELPD against the current-rules refit.
  - Close #439 (v1) as superseded once v3 is fitted.

## 2026-10-08 06:20 ET

- **#498 quarantine-v10 merged (c1a3a19).** It makes the Chelsea/WV quarantine rent-blind too.
  It holds v9's 95 GV/GP/Flatiron rows plus 124 Chelsea/WV rows from the same screen
  (`frontier/scripts/quarantine_v10_screen.py`, centre W 14th and 8th Ave, no v6), every hit read
  blind, for 219 rows. 91 of the 124 were already in v6; the 191 other v6 rows come back.
  Short stays count only when the ad calls itself short-term only or offers under 6 months.
  Modeling queued it as `frontier-modalq-nb5q10` (`…nb5-ul11r1s4q10`) after nb5q9. Whichever
  serves is decided by the paired dry run on shared rows, not by version order.
- **#502 nb5-plutoasof-v2 merged (2b2d262).** v1 (#439) dated every MapPLUTO field and lost
  (−71.1 ± 20.4, gate passed). The dated size fields differ on 8–10% of rows but almost never
  because the building changed (`/data1/apartments/tmp/suspect/pluto/drift.out`), so they are
  revision noise. v2 dates only yearalter1/2 (never from a release older than the building);
  `altered_since_2000` differs on 3,137 rows. `AS_OF_SETS` already drops alterations after the
  listing, so expect a small effect. Queued as `frontier-modalq-nb5pluto2` after nb5q10.
  Close #439 once v2 is fitted.
- **Record when they land:** nb5q9, nb5q10, nb5pluto2 in `hand_tests` of feature-tests.json.

## 2026-10-08 05:00 ET

- **#494 quarantine-v9 merged (b8aeed0).** It replaces v7 (#481) and v8 (#485). Both are held
  and not fitted: v8 picked its candidates by the served model's residual, and v7's detector had
  the same problem. v9 is v6's 282 rows plus 95 GV/GP/Flatiron rows from a rent-blind screen
  (`frontier/scripts/quarantine_v9_screen.py`). The screen uses NTA place names over 2.5 km
  away, generic category words and a guard against terms fitted to v7/v8 rows. Every hit was
  read blind. That gives 377 rows. The ledger records v7 and v8 as held and v9 as queued.
  - Modeling queued it as `frontier-modalq-nb5q9` (label `…nb5-ul11r1s4q9`, current rules with
    quarantine-v6 swapped for v9). It runs after nb5permit2 and ahead of the singles filler.
    Record the paired result in `hand_tests` when it lands.
- **Next: a rent-blind Chelsea/WV replacement.** v1 to v6 were partly picked by rent
  (divergence reviews, unit effects, residuals over 0.3). `/data1/apartments/tmp/suspect/q10`
  runs the v9 screen over Chelsea and WV without v6: 86,819 rows give 749 hits, 93 of them
  already in v6. Four blind readers have `review_[a-d].json`; 40 groups are read twice
  (gid 1000+) as a consistency check, and `key.json` maps gids to rows. The plan is a new rule
  (new file and id) that replaces v6's rent-picked rows with blind-confirmed hits. It gets its
  own full fit via Modeling.

## 2026-10-08 02:40 ET

- **#481 quarantine-v7 (open, approved by a reviewer subagent, head a9dc5f5).** This is the first
  quarantine review of Greenwich Village, Gramercy Park and Flatiron; v1 to v6 read only Chelsea
  and WV. It keeps v6's 282 rows and adds 45 (27 ads for another address, 9 short stays only,
  9 shops or offices), for 327 in all.
  - Not merged: the full suite (`/data1/apartments/tmp/suspect/q7/suite.out`) is unconfirmed
    because the auto-mode check refused a read of it. Ben has been told.
  - Once merged, ask Modeling for its own Modal full fit with quarantine-v6 swapped for v7.
  - Scratch: `/data1/apartments/tmp/suspect/q7` holds `detect.py` (loose cues, 3,121 hits),
    `tight.py` (338 candidates) and `mkv7.py`.
- **#478 nb5-permit-v2 (open, stacked on #437).** It reads every apartment of an ad's list. Room
  counts, ordinals and PH-words are no longer read as labels. It flags 2,442 rows to v1's 1,785.
  Modeling queued it last (`frontier-modalq-nb5permit2`). Merge it after #437 if it wins.
- **#435 nb5-stab-v1 closed.** The result is a null (−1.1 ± 2.5) and has been recorded in
  feature-tests.json.
- **Next overlay work.** fields-review (bedroom and bath field errors) also covers only Chelsea
  and WV (16 rows).

## 2026-10-08 01:10 ET

- **Geospatial retests on five neighbourhoods.** The ledger marks older-dataset tests as due for
  a retest. These are the data-side ones, best prior first. Each is the nb3 set on
  `nb5-coded-v2`, listed in NB4_SETS, and runs as its own Modal full fit on DATASET_NB5 with v11
  rules.
  - #472 (c9f0e1b): `nb5-lines-v1`, `nb5-loc-v1`, `nb5-walkup-v1`, `nb5-noise-v1`
    (`NB4_NOISE_FILE`). Modeling queued them in that order as `frontier-modalq-nb5retests`, after
    stab, plutoasof, bedtime6, v12, s5 and permit.
  - #473 (d1868aa): `nb5-water-v1` and its base `nb5-parks-v1`, queued as
    `frontier-modalq-nb5parks` after the four.
- **Manhattan-only parks.** The NB4 parks snapshot reaches across the East River to Brooklyn and
  Queens parks acquired after 2000 that `parks.SECTIONS` has no dates for, so `parks.places`
  refuses it.
  - `external parks --borough M` keeps one borough's properties.
  - `NB5_PARKS_FILE` = `external/parks/20261008-f63bf6c` (180 parks; the NB4 snapshot has 204).
  - `features.parks_file()` follows `PARKS_SNAPSHOTS` for the set being built.
- When the retests land, record each in `hand_tests` of feature-tests.json against the nb5 base.

## 2026-10-07 23:45 ET

- **Five neighbourhoods are on master (#460, 5789d79):** Chelsea, the West Village,
  Greenwich Village, Flatiron and Gramercy Park.
  - `rentfrontier.areas` splits the FGP crawl into Flatiron and Gramercy Park, each building
    taking the area named in its StreetEasy page title. Snapshot:
    `external/areas/20261008-6027acc` (480 Gramercy Park and 327 Flatiron buildings; one Park
    Slope building left out).
  - `cohort areas` relabels each row's `neighbourhood` to its building's area. No rows or rules
    change.
  - `DATASET_NB5` = `datasets/chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057`.
    Rows: Chelsea 52,614, WV 34,205, GV 18,425, GP 18,333, Flatiron 12,182.
  - `nb5-coded-v2` = nb3-coded-v2 plus Flatiron and Gramercy Park indicators (`hoods_v1`); it
    is in NB4_SETS.
  - Map check: two contiguous areas. One Union Square South keeps StreetEasy's Flatiron label.
- **Every queued test now runs on five neighbourhoods.** The nb4-* ids are gone from the
  branches. Modeling queues each as its own full fit on DATASET_NB5, after the nb5-coded-v2 base
  fit (launched 23:20) and its bedtime6 test.

  | PR | Test | Head | Unit |
  |---|---|---|---|
  | #435 | nb5-stab-v1 | 0233ec5 | frontier-modalq-nb5tests; suite passed |
  | #439 | nb5-plutoasof-v1 (`hoods_v1` over nb3-plutoasof-v1) | 8af14dc | frontier-modalq-nb5tests |
  | #420 | unit-labels-v12 | 881b345 | frontier-modalq-nb5rules |
  | #425 | unit-splits-v5 | d478a5b | frontier-modalq-nb5rules |
  | #437 | nb5-permit-v1, DOB `external/dob/20261008-4e1948c` (50,420 jobs) | e935808 | frontier-modalq-nb5permit |

- **The DOB fetch now retries 5xx errors and uses smaller queries** (25 BINs per request, pages
  of 10,000), on the #437 branch.
- **Run test suites with `JAX_PLATFORMS=cpu XLA_PYTHON_CLIENT_PREALLOCATE=false`.** A suite
  held 6 GB of the GPU and made Modeling's m0-base baseline fail with a GPU OOM.
- **PR bodies:** read them with `gh pr view` from inside a worktree. Run outside one, it prints
  nothing, and a PATCH built from that wipes the body. #437's body was restored from its
  userContentEdits history.

## 2026-10-07 22:20 ET

- **Flatiron + Gramercy Park data is on master:**
  - #447 adds unit-labels-v11 (FGP aliases and history pairs). This is now the current rule.
  - #451 adds the nb4 snapshots: `NB4_*_FILE` in features.py, `_NB4_DESCRIPTIONS`, and
    `descriptions.FGP_SOURCE`. Storefronts are now fetched one reporting year at a time. The
    pre-squash commit e78c6fd is kept in archive/pr-451.
  - #452 adds `DATASET_NB4`: 135,759 rows, 30,515 of them FGP; 135,477 pass the master rules.
  - In listing extras, 165 nb3 listings now take FGP's later capture. That touches 39 CWG rows.
- **Modeling's part:** Modeling builds nb4-coded-v2 in its own PR and queues one full fit of the
  served design on DATASET_NB4. DATASET, `ops/modal/fit.py` and `config/main-analysis.json` stay
  on CWG until an nb4 fit is served.
- **The queued tests are rebased onto v11** so their fits stay servable.

  | PR | Test | Head |
  |---|---|---|
  | #420 | now unit-labels-v12: v11 plus merging spelled-out labels | dc65ba3 |
  | #425 | unit-splits-v5 | 65260da |
  | #435 | stab | 5bd6e4b |
  | #437 | permit | a941744 |
  | #439 | plutoasof | bbc0805 |

  The queue is frontier-modalq-data11. The first fit starts about 06:30 ET and the rest follow
  about every 2.4 h. Merge #420 only if its fit passes. Bump no other rule version mid-queue
  without telling Modeling first.
- **Possible follow-up:** RULE_SOURCES for v11/v12 records only the alias file, not
  history-20261007.jsonl. Ask Modeling before changing it.

## 2026-10-07 21:45 ET

- **Policy (Ben, 22:27Z, relayed):** every test is its own Modal full fit through Modeling's
  queue and is served if it passes the gate. There are no thelio exploration pairs and no
  bundling. The Modal balance is capped at one day's accrual (#433). Merge a feature PR only once
  its fit passes the gate.
- **Open-data survey (#434, merged):** it is at the top of `docs/model/research-backlog.md`.
  Survey scripts and data are in `/data1/apartments/tmp/suspect/opendata/`. HPD owners and agents
  are not proposed.
- **Three features are queued with Modeling as their own Modal full fits:**

  | PR | Feature | Head | Snapshot | Rows affected | Fit |
  |---|---|---|---|---|---|
  | #435 | nb3-stab-v1 | 2c38a45 | rentstab/20261008-6b42fe8 | share > 0 on 73% | frontier-modalq-stab, about 08:30 ET 10-08; suite passed |
  | #437 | nb3-permit-v1 | 9fdd817 | dob/20261008-ab3d278 | 1,390 rows, 928 units | frontier-modalq-permit, about 10:55 ET |
  | #439 | nb3-plutoasof-v1 | 77c738e | plutohistory/20261008-931c6e8 | 23,352 rows | asked to queue after permit |

  - **nb3-stab-v1:** rent-stabilized share as of the tax bill of the year before the listing.
  - **nb3-permit-v1:** a DOB A1/A2 permit naming the apartment, issued in the 3 years before the
    listing month.
  - **nb3-plutoasof-v1:** nb3-coded-v2 with MapPLUTO from the release of the year before the
    listing. Today's year built is kept.
  - Each fit pairs against the 4500-draw serving refit, which passed the gate at 20:56 ET and
    which autoselect switches to.
  - After each fit lands: record it in `docs/model/feature-tests.json` `hand_tests`. If it passes,
    merge the PR (frozen heads; merge master in first), and tell Modeling and the coordinator.
- **Still queued with Modeling:** unit-labels v10 (#420, 2da098d) and v5 (#425, 98a146d).

## 2026-10-07 15:40 ET

- **quarantine-v6 and unit-reviews-v1 (#419, merged 9b6c16d) are current.** At 110 W 26th St,
  R and B are the same rear unit (Ben, 17:59Z: the R and B listings "both refer to the unit at the
  back of the building"): `config/reviews/unit-joins-20261007.jsonl` joins 4R/4B and 5R/5B. The
  five bare floor-number ads there are quarantined (`quarantine_unit_unknown`). `apply_rules` now
  refuses unit-reviews before unit-labels. Modeling re-pointed the v4 serving refit
  (frontier-modalq-sp4) to 9b6c16d. The cheap 2015 5F ad (https://streeteasy.com/rental/1566842)
  is a genuine renovation and relist (Ben, 18:44Z), so it stays in the unit.
- **unit-labels-v10 (#420, draft, head 2da098d) won its exploration pair:** +49.2 ± 21.9
  (2.2 SE; Chelsea +19.3, WV +22.8, GV the rest) against fa61d6c's coded-v2 arm on v9 + v4. Each fit's LOO
  MCSE is about 10. It joins spelled-out labels to short ones ("5 FL" = "5", "Penthouse" = "PH",
  126 groups, 262 rows, no bedroom guard: v4 splits bedroom changes). Modeling queued its Modal
  full fit after the v4 serving refit. Merge #420 only after that pair; merging makes v10 current.
- **Renovation split (coordinator relay 18:45Z): sized, not run as a split.** Sizing is in
  `/data1/apartments/tmp/suspect/renov/size.py`: 179 splits at a market-adjusted jump of at least 30%,
  93 with a broker change, 51 at 50% or more, about 80% precision. A price-gated split reads the row's
  own rent, so I proposed the leak-free feature instead: **nb3-renov-v1 (#422, draft)** flags
  4,008 rows whose ad says newly or gut renovated when the unit's previous ad did not. Its arm
  is unit frontier-renov-explore (`/data1/apartments/tmp/suspect/renovfit/`, rules q-v5, ul9, splits-v4,
  label ul9s4), paired with fa61d6c's arm through `pair_subsets.py` (see `prevjump/pair3.sh`).
- **Skipped or backlog:** loft flag skipped (Ben, 17:46Z); HowLoud sound scores to the backlog.

## 2026-10-07 14:10 ET

- **unit-splits-v4 (#414, merged 5f0a7f0) is current.** It is v3, but a one-bedroom change does not
  split when the earlier ad gave no square footage and the new one does. Why: v3 failed coded-v2's
  group R-hat gate at building 120 = 110 W 26th St, a loft building (split R-hat on level, bedroom
  slope and size slope 1.08, against 1.00 under v1). Five cheap footage-less "1-bed" ads
  ($2.4–2.6k, 2015–2021; probably room shares, no ad text) split its 1,400–1,650 sq ft units.
  v4 moves 619 rows of 314 units in 184 buildings back relative to v3. The attribution of
  v3-vs-v1's +953 put only +5.3 on those boundaries. Scripts: `/data1/apartments/tmp/suspect/rhat/`.
  Modeling queued frontier-modalq-sp4 (coded-v2, loc-v1, bedtime6 at 5f0a7f0, label
  a100-3600k9cb1-gv1006-ul9s4) to land about 00:30 ET 10-08. Autoselect switches if the gate passes.
  Modeling then sends the v4-vs-v1 pair and loc-v1's clean pair. Record both in the ledger.
- **nb3-loc-v1 ledger note (#415):** +9.2 ± 15.3, provisional until the clean pair on v4.
- **Lofts (Ben, 17:34Z: "a different category for these loft-style apartments?").** Sizing:
  MapPLUTO has no L class among our buildings. D5 (converted) covers 21 buildings and 2,111 rows.
  In 310 buildings at least half of all ads (any date) say "loft". In those buildings a 1-bed has a median of
  1,015 sq ft against 700 elsewhere, and units change bedroom count 25% of the time against 12.5%.
  Room shares: no rule. A spot-check of "roommate" text hits found whole apartments; most cheap
  footage-less ads were real studios. Scripts: `/data1/apartments/tmp/suspect/loft/`.
- **nb3-loft-v1 (#416, merged fa61d6c):** coded-v2 plus a causal loft flag (D5, or at least half
  of at least 3 strictly-earlier ads say loft), loft × (bedrooms − 1) and loft × size deviation.
  It flags 7,890 rows in 304 buildings (the causal rule is stricter than the sizing): D5 only 1,634, text only 5,779, both 477. Modeling's exploration pair is
  unit frontier-loft-explore (label x-2060-100w600d-gv1006-ul9s4, v9 + v4), due about 15:15 ET.
  If it gains, Modeling runs a Modal full fit. Record the pair in the ledger.

## 2026-10-07 11:00 ET

- **unit-splits-v3 (#408, merged 8f40c96) is current.** It splits a unit's history at any change of
  bedroom count (threshold 1, from #400's v2). When a count returns, those listings rejoin that
  earlier piece. Coded-v2 pairs on v9: v3 vs v1 +953.0 ± 98.0 (Chelsea +381.8, WV +339.0, GV the rest); v2 vs
  v1 +780.3 ± 101.5; v3 vs v2 +172.7 ± 42.6. #400 closed as superseded. I asked Modeling and the
  coordinator for the coded-v2 serving full fit on 8f40c96 in place of the v1-rules fit.
  Pair scripts: `/data1/apartments/tmp/suspect/prevjump/pair3.sh`.
- **text-v1 (Ben, 2026-10-07):** fair WV+GV score +43.7 ± 23.5 (1.9 SE); not restored. It is back
  in `docs/model/research-backlog.md` as text-v2 (#406). Ledger rows: `hand_tests` in
  `docs/model/feature-tests.json` (#404).
- **Yearnoise lead:** the gain is market scatter (residual SD about 9% from Sep 2020 to Feb 2021),
  not a data problem; no rule. Modeling takes a pandemic term per segment.
- Possible follow-ups: #408 reviewer nits (merge the duplicate isnan checks, test a multi-row ad
  with rejoin); ledger hand_tests rows for unit-splits v2/v3.

## 2026-10-07 09:00 ET

- **Prevprice jump audit** (asked by Modeling). The served fit's high-k rows with a big rent jump
  from the unit's previous listing are not from bad label joins: the share of jumps over 40% is
  8.2% for raw StreetEasy ids and 6.5–9.7% for the v5/v8/v9 joins. They come from bedroom counts
  that change inside one unit id. Change of 2 or more: 583 pairs, 63% big jumps, 5.8% high-k.
  No change: 6.8% and 0.6%. Scripts: `/data1/apartments/tmp/suspect/prevjump/`.
- **unit-splits-v1 (#397, merged 39c3c8a):** a unit's history splits where an ad's bedroom count
  differs by 2 or more from the previous ad with a count; 1,058 rows of 463 units. `apply_rules`
  refuses unit-splits unless it comes last. Exploration pairs (rows split, 69cb5c6, v8, splits
  vs base): coded-v2 +475.4 ± 56.4, prevprice-v2 +488.2 ± 57.6. In both, the moved rows gain
  about +210 and the rest comes from rows left in the original unit.
- **#394 (v9) merged** as 9c96f74. Modeling cancelled the v8 latest arm and will run one Modal
  trio on 39c3c8a from midnight ET 10-08: prevprice-v2 rows (the one to serve) and prevprice-v2
  and coded-v2 latest.
- A threshold of 1 for the split is untested: 3,871 pairs, 20.7% big jumps, 1,374 of them
  involving a studio. Alcove and flex coding make that noisier.

## 2026-10-07 04:40 ET

- **unit-labels-v9 (#394, draft, reviewer approved):** v8 plus number-word-and-letter labels
  ("fourb"/4B, "five-a"/5A) joined to their twins when bedrooms agree; 46 unit ids, 297 rows.
  Exploration pair vs v8 (coded-v2, rows, b50430b): +29.9 ± 20.0 overall, +22.5 ± 8.2 on the 261
  relabelled rows. **Merge only after Modeling decides v8** (its last v8 latest arm launches on
  Modal at midnight ET 10-08; latestselect refuses arms off the current rules). Modeling then
  queues the v9 Modal fits at the merged master commit.
- What's left of label splits after v9 is too mixed for one rule; 55 rows carry listing-id-like
  labels ("01226"), one-row units.

## 2026-10-07 01:00 ET

- unit-labels-v8 (#336) merged as 4d6e6f7 (paired full fit +279.6 ± 33.5 vs current rules, gate passed).
  Drafts #326 (v6) and #335 (v7) closed as superseded. Modeling queues the v8 full fits on Modal;
  autoselect decides serving. Served model before v8: nb3-prevprice-v2 (#392).

## 2026-10-07 00:00 ET
- **Retests on GV data** (yearnoise design, paired against nb3-coded-v2, 94,453 rows; none fully converged,
  R-hat 1.07–1.10): text-v1 +106.4 ± 32.8 (later: fails 2 SE on the fair WV+GV score, not served;
  back on the backlog as text-v2, Ben 14:21Z/14:30Z); null: noise +3.3 ± 14.3, water +0.7 ± 14.6, flagfix +0.1 ± 23.7,
  walkup −6.2 ± 14.0, attrs −7.5 ± 28.9. loc-v1 OOMs at the 7G GPU-job cap on thelio; it ran on a
  Modal A100 on 10-07 (+9.2 ± 15.3, provisional; ledger #415) and Modeling has it queued again after bedtime6. Results in `/data1/apartments/tmp/bridge/retest-pair-*.txt`. Don't relaunch
  scripts in that folder; it is Modeling's queue.
- **Exposure outlook (#382):** `exposure-manual.csv` has an `outlook` column ("wall"); 82-86
  Washington Pl 2B is the only row. Website shows no pill for single hand labels (Ben).
- **Facing-a-wall feature: dropped** (Ben, 2026-10-07 "don't build a facing-a-wall feature").
  The WIP stays on the local branch `data/wall-v1`, unpushed.
- **1 University Place J line:** Ben kept #2J coded 1BR (convertible unit; PR #386 closed). The
  other J units have one-bedroom plans (Ben). /best notes "can be set up as a 2-bed" (#387).

## State
- **Greenwich Village fold-in: done on the data side.** #292 (cohort, listing extras, alias table
  `config/unit-aliases/wv-gv-20261005.jsonl`, rule `unit-labels-v5`, feature sets
  `nb3-coded-v1` / `nb3-prevprice-v1` / `nb3-lineface-v1` on the three-neighbourhood snapshots
  dated 20261005) and #297 (three-name neighbourhood labels in term text, listing summaries and
  the rent map's area caveat). Snapshot names carry the pre-rebase commits 2d5b3b6 / 77068ea.
- **Modeling owns the GV fits** (units `frontier-gvfit`, `frontier-gvfrontier`,
  `frontier-gvrefit-early`; logs in `/data1/apartments/tmp/bridge/`). Plan for the night of Oct 5:
  GV explorations (lineface pair ~20:00 ET), served design + nb3-coded-v1 refit ~21:30 ET at
  3600 draws (4500 would overrun 2 h on 21% more rows), then nb3-coded-v1 vs nb3-prevprice-v1 on
  the latest split ~23:30–05:30, then a prevprice rows serving fit in the morning if it wins by
  more than 2 SE. Modeling reports the paired numbers to this thread.
- **Prevprice (pre-GV):** passed the leak-free latest-split gate (+75.5 ± 15.7 PSIS-LOO, ~4.8 SE)
  but its rows serving fit overran the 2 h cap (16:02 Oct 5); not served, not retried on the old
  data. Prevprice is slower per draw, so the GV serving fit is borderline on time.
- **LPC as-of (#307, merged):** `nb3-coded-v2` / `nb3-prevprice-v2` date the landmark and
  historic-district flags by the LPC's designation dates (`external lpc`, snapshot
  `/data1/apartments/external/lpc/20261005-8946d6f/`). This fixes 94 + 37 rows flagged for
  designations made after the listing, and puts 420 condo-lot rows in a district MapPLUTO leaves
  blank. Ben approved moving tonight's GV refit and the latest-split pair to v2 (unit
  `frontier-gvrefit-v2`, from ~21:00 ET).
- **Footprints as of the listing year: measured, NOT shipped.** Neighbours built after a listing
  change 708 rows' building sides, but only ~50 rows' facing features (side street versus rear).
  Dating them cost 154 s per feature build against 10 s. The patch (`nb3-coded-v3`,
  `building_sides_as_of`) is kept at `/data1/apartments/tmp/suspect/lpc/sides-as-of.patch` in
  case it is wanted later.

- **#167 revert (Ben, 2026-10-05 "Revert them"): PR #314 `fields-review-v3`**, approved and
  tagged, NOT merged. It is a no-op rule that takes `fields-review-v1` out of `current_rules()`.
  None of the 16 apartments has another listing to back its correction. Held until Modeling's
  `frontier-gvlatest48` prevprice pair lands (~12:15 ET) and latestselect has run; Modeling
  messages then. Merge with `gh pr merge 314 --squash --match-head-commit 8d81e7e`. Full fits
  after that use v3.
- **Exposure evidence table sent to Website** (`/data1/apartments/exposure/labels-evidence-20261006.parquet`
  and .csv; builder `/data1/apartments/tmp/suspect/exposure-evidence/evidence.py`). Logged in
  their backlog item 11 (#315); website features are on hold (Ben, 2026-10-05).
- **Prevprice on GV (v2 sets, latest split):** +92.5 ± 16.7 (5.5 SE), but both arms failed the ESS
  gate (380 and 334 < 400). They are being rerun at 4800 draws as `frontier-gvlatest48`.
- **Present-day MapPLUTO unit counts: measured, NOT worth a feature set.** Dated by the DOB housing
  database (`/data1/apartments/external/housingdb/20261002-f155dcc/`), 3,153 rows (3.0%) were
  listed before a unit-changing job on their lot completed, but only ~1% see a material change in
  units. The biggest apparent changes are new buildings whose final CO came years after leasing
  under a TCO, so a naive as-of count adds noise. Only one lot is plainly wrong: London Terrace's
  1007217501 records 2 units (4 building pages, 167 rows; its area per unit is already unknown).
  Buildings where we see far more units than MapPLUTO records (130) are unit-id fragmentation,
  not bad lots: 248 10th Ave has 9 units and 40 ids (`3`, `three`, `3a`, `a3`, `2b`, `2-b`).
  Notes and scripts: `/data1/apartments/tmp/suspect/pluto-asof/` (FINDINGS.md).

- **Wish features (coordinator relay, 2026-10-06 15:03Z):** Ben wants no separate preference
  model. Garden view, floor-through and quiet street become interpretable rent-model terms that
  Modeling recombines into pros and cons. Each has a per-apartment table in `/data1/apartments/wishes/`.
  - #328 `nb3-garden-v1` (merged): rear windows' openness from footprint rays. Fit `frontier-gvgarden`.
  - #329 `nb3-through-v1` (merged): one or two apartments per floor, plus the ad text. Fit `frontier-gvthrough`.
  - #330 `nb3-quiet-v1` (merged): busy road, narrow roadway, mid-block, plus the ad text. Modeling
    chains its fit after gvthrough (`frontier-gvquiet`).
  Each fit pairs the set with nb3-coded-v2 on PSIS-LOO; Modeling reports the paired numbers.
  Results (relayed to Ben): garden +11.8 ± 14.2, through +5.4 ± 15.7, quiet +8.1 ± 14.2, all
  noise. Coefficients: one apartment per floor +18.9% [+15.9, +22.0], two per floor +8.3%, ad
  says floor-through +0.9%; garden and quiet terms about zero. Suggested /best shows the
  floor-through premiums only.
- **Location features (coordinator relay, 2026-10-06 16:46Z, from Ben's /best feedback):** four
  wish sets on nb3-coded-v2, from free open data, all merged. Modeling runs them in `frontier-gvwish`
  (from ~14:15 ET, results ~16:30 ET) as reference + loud, transit, nearby, retail.
  - #344 `nb3-loud-v1`: which building sides front a busy road (`loud.py`).
  - #345 `nb3-transit-v1`: weekday-morning subway minutes to midtown from the MTA GTFS (`transit.py`,
    `external gtfs`, snapshot `20261006-6158e22`), as of the 7 extension (Sept 2015).
  - #346 `nb3-nearby-v1`: log metres to dog run, hospital, EMS, drop-in center, NYCHA, MSG
    (`nearby.py`, `external places`, snapshot `20261006-7c4c408`, NYC open data + OSM dog parks),
    as of `OPENED` dates. DHS shelters have no addresses, so they are left out.
  - #347 `nb3-retail-v1`: storefronts and food places within 150 m (`retail.py`, `external storefronts`,
    snapshot `20261006-5fd0c26`, 2019-2020 filings; vacancy left out as future information).
  Snapshot-writing commits are kept by `archive/snapshot-*` tags. Outside a build, set
  `features._LOTS` from `features.lot_files(set)`, or half the rows read the old registry.
- **Commute table (Ben, 2026-10-06; #353):** `rentfrontier.commute` writes
  `/data1/apartments/wishes/commute-<date>.parquet` and `.csv` (building, destination, address,
  minutes, transfers, walk_to_station_min, station), weekday 08:00-09:00 subway to the places in
  `config/commute-destinations.json` (default: office, 65 E 55th St). Ranking only, never a
  feature set (Ben is wary of over-tuning to him). Website reads the newest CSV at runtime for
  /best pills (#355); tell Website before renaming columns or moving the file.
- **Line and access wishes (Ben, 2026-10-06 18:34Z: "to price"):** #357 `nb3-lines-v1`
  (`lines.py`: a "<group> within 8 min" term for each line group that at least 1% of buildings
  have within an 8-minute walk; the 7, J/Z and G are too far away to price; PATH is not in the
  MTA feed) and #358 `nb3-access-v1` (`access.py`: log of the jobs within 30 min by walking and
  subway, from LODES8 WAC (`external lodes`, snapshot `20261006-e587e60`), lagged two years,
  stations as of the listing month). Travel times are our own Dijkstra on the GTFS with grid
  walks, not r5py or OSM. Modeling runs both in gvwish2 (results ~17:30-17:55 ET); Ben wants
  to know which lines come out positive. The amenity half of access (groceries, parks and gyms
  within 15 min) is a later PR.
- **Photo pilot (done 2026-10-06; Ben OK'd the fetch at 18:35Z):** 202 apartments, 680 images
  in `/data1/apartments/photo-pilot/` (answers/, key.json, QUESTIONS.md), 10 Sonnet readers,
  ~1.3M tokens (under $4). Windows street/rear: 65 unknown, and 68% agreement with our exposure
  labels where answered, so no full run. Floor plans: readers transcribe bedroom dimensions
  well (85/86 match the clearance rule), but 77/86 bedrooms fit a king. Any full run needs a new
  costed OK from Ben.
- **Bed size (Ben's mattress idea; #359):** `bedsize.py` reads the largest bed each listing's
  own ad states (king/queen/full; ~21% of rows), and `nb3-bedsize-v1` adds three 0/1 terms.
  The per-apartment table `/data1/apartments/wishes/bed-size-<date>.*` goes to Website for
  /best. I asked Modeling for an exploration fit.
- **Parks (amenity access, parks half; #364):** `parks.py` and `external parks` (NYC Parks
  properties enfh-gkve, snapshot `20261006-d208294`). `nb3-parks-v1` adds "log walk min to a park"
  (1+ acre, acquired before the listing month) and "High Line within 5 min". `parks.SECTIONS`
  dates the High Line (2009 / 2011 / Spur 2019; no Rail Yards in the source) and Bella Abzug Park
  (two south blocks, 2015-08-31); `places()` refuses large undated or post-2000 parks without
  sections. Hudson River Park (state) is missing. Groceries and gyms: no dated source (NYS food
  licences undated, storefront categories too coarse). Exploration fit requested from Modeling.
- **Wish-set verdicts (all exploration fits vs nb3-coded-v2; ledger docs/model/feature-tests.md):**
  only lines-v1 is worth carrying (+21.6 ± 17.2; N/Q/R/W +9.4%, L +2.6%, 2/3 +1.8%; 1, A/C/E,
  4/5/6 negative, all geography proxies). Null: loud −10.1, transit −7.4, nearby −1.3, retail
  +6.2, access −12.7, bedsize −25.2, parks −6.0 (High Line within 5 min +3.0%). Modeling refits
  lines and retail on the served design (gvnext). Location nulls get a retest after the
  Flatiron + Gramercy fold-in. Full fits now go to Modal (Ben 23:00Z, via Modeling); thelio's
  GPU is for exploration fits. DOT traffic counts: too sparse (89 one-year segments), dropped.
- **Performance review items:** rebuild memory measured (#351, 44 KB per row, no change);
  granular export row groups 8,192 (#352).
- **#326 `unit-labels-v6`** (draft) waits for a batch full fit.

## Next
- Fit the new sets (lister, sizefill, nta, riverparks; open-v2, owner, explain) once Ben
  resumes model runs; Modeling owns the queue.
- Floor-plan OCR if Ben approves the image fetch.
- Act on the stab, permit and plutoasof fits as they land (see 21:45 above), and on v10 and v5.
- Next quarantine rule, quarantine-v12, when the East Village crawl lands. The rule versions and
  the screen scripts are numbered separately: the rule is v12, and the screen to use is
  `quarantine_v13_screen.py`.
  - Screen EV with `quarantine_v13_screen.py`. Its building-name fix is new in v13; the screen
    script v12 has only the Stuyvesant fix.
  - Merge the 10 staged NoMad rows and the Harlem row (audit_id 50f8ccd4…) with EV's.
  - Tell Modeling before merging.
  - #542 (quarantine-v11) stays held.
- Then EV prep, as for NoMad: alias table, cohort, snapshots, NB8 sets.
- Permit follow-ups: read every label in a list ("APTS 2A & 3A" reads 2A only), and drop
  generic hits such as "HVAC UNITS" (harmless now).
- More open data: unused MapPLUTO fields and dated DOB certificates of occupancy (new-building
  unit counts).
- Flatiron + Gramercy: the data is done (see 22:20). Geospatial retests are queued (see 01:10).
- Backlog: bldgclass for condo conversions, Jane St registry fix, 13 excluded new-building
  rows, gross rent, relist gap.

## Rules that bind this thread
- Rule-based changes, one PR per change, no future information; descriptions never override coded
  fields; no new LLM calls, image downloads or scraping beyond what Ben approved.
- Bulk ad reading runs on Sonnet or Haiku subagents (Ben, 2026-10-15). The default model designs
  the rules, spot-checks about 30 verdicts and does the final sizing.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
