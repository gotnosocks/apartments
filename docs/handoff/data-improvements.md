# Data improvements — handoff

Updated 2026-10-10 11:05 ET. Thread owner: the Data improvements project thread (bridge session on thelio).

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
  - PLUTO lists 2 buildings, but there is no footprint row for the lot.
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
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
