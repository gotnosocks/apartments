# Pipeline rebuild: closing report

October 17, 2026. This covers the rebuild of the raw-to-fit-ready pipeline on API records.

The rebuilt pipeline turns each API export into checked, fit-ready rows with no step done by hand. Every done criterion has a measured result below. Two pieces of the original task stay open:

- **The page parser itself.** The collector, top-up and pipeline no longer use it (#968). About 100 files remain, used only by the page crawler and the September research code. Removing them goes with the crawler owner's own PR.
- **Scored unit matching (lane D).** The matcher is measured, but nothing goes into the ledger yet, because about 3 in 10 of the joins it would make may be wrong. See [Unit matching](#unit-matching).

## Service changes

Both were applied on Ben's word at about 09:50 ET, with no restart.

1. **Out-of-memory setting:** the Claude service on thelio now has `OOMPolicy=continue`, so an out-of-memory kill takes only the job that caused it.
2. **Friday city fetch:** before each run it now checks out the current master and runs the script from there, like the dashboard build. If the fetch fails, the run uses the copy as it was. The next run is Fri Oct 23 at 04:00 ET. The repo's copy of the unit is brought in line in #1011.

## Done criteria

| Criterion | Result |
|---|---|
| Four-region table matches the chain | Met. Every comparable row matches; the 92 extra rows are explained. |
| Page-crawl areas agree | Met. 350,974 shared rows agree in every value. |
| Planted errors caught, with the count | Measured. Most kinds are caught in full; ask ×10 and whole-ad bedroom flips are the gaps. |
| City records agree | Met, with causes for every kind of disagreement. |
| Friday top-up is incremental and equals a full build | Met, byte for byte (#958). |
| Fixture runs the whole pipeline in tests in under a minute | Met: 6.7 s. A one-step change lists all its effects in 6.1 s. |
| Before/after time, memory and dollars | Measured from systemd and the Modal ledger. |

### 1. Four regions

The chain's four regional datasets of Oct 15 hold 1,396,053 rows. I left out 101 rows of units answered after the chain read the archive at 13:10 ET.

Each of the other 1,395,952 rows matches a row in `analysis.rows` in every field compared: unit, page, building, ask, layout, baths, size, floors, area, amenities, exposures, first ask and latest ask.

The pipeline holds 92 more rows. The old collector dropped these ads because they had no unit page; the pipeline places them from their own records.

### 2. Page-crawl areas

The 350,974 rows in both agree in every value.

- The chain's dataset has 2,232 Noho rows that the export files under manhattan-below-59th. The pipeline keeps them there with the same values, so a fit should select them by neighbourhood.
- The pipeline has 13 more rows, for the same unit-page reason as in item 1.
- Against the served dataset (latest-ask-v8), every difference on the 277,633 ads in both has a cause in the docs' list. The check on the 23:39 build found 3 more, on ads whose descriptions changed in records fetched at 23:29 ET.
- All 43 frontier datasets loaded the same after the page rewrite was deleted (#967).

### 3. Planted errors

I planted 50 of each kind of error in a 3% sample.

- **Caught in full:** all 100 planted price changes, every flipped latest bedroom count, every future ACTIVE answer and every ask multiplied by 100.
- **Asks multiplied by 10:** 7 were dropped before the rows, and the ask check flagged 41 of the 43 that reached them, so 2 got through unflagged.
- **Bedroom counts flipped in every record of an ad:** 49 reached the rows, uncaught. Nothing in such an ad contradicts the flip. A screen against the unit's other ads would drop about 4 good rows for every bad one. A Sonnet read of 30 rows that screen would flag found 6 wrong, 14 flex or unclear, 4 real changes, 4 right and 2 from another unit. So bedrooms get no screen.

### 4. City records

70,139 of 70,144 buildings have a lot. They cover 1,746,259 of the 1,746,791 rows.

- **Units above the legal count:** of the 66,892 lots with ads, 1,580 have more units with an ad in the 12 months to Oct 16 than their legal count, and 62,165 are within it. A unit here is a unit page, so an apartment listed under two labels counts twice. Of 20 lots read, 17 were unit splits or relabels, 1 was a city record behind the building and 2 were other. None was on the wrong lot. Unit matching takes these up.
- **Above the lot's floors:** 8,203 rows, of which 306 are also above StreetEasy's count. All 20 read were city records out of date.
- **Lots with no apartments:** of 20 rows read, 8 were on the wrong building, 9 were mixed use and 3 were other.
- **Three city records are wrong.** They are noted here rather than in the ledger:
  - Battery Park City lot 1000160100 at 5 floors, against StreetEasy's 34;
  - Carnegie Park at 13 floors, which looks like 31 with its digits swapped;
  - 235 Jackson St at 2 units, where the certificate of occupancy counts 6 and StreetEasy 8.

### 5. Building check (#971)

`analysis.ads` has a new `building_check` column. It flags 1,638 rows on 1,019 lots and drops nothing.

- On lots a reader labeled, the floor rule caught the wrong building on 29 of 40, and the zero-unit rule on 15 of 20. That works out to about 1,290 rows (0.07%) on a building their lot rules out.
- The check only catches mistakes a lot record can show, so 0.07% is a lower bound. I put the building matcher's error under 1%.
- DI's Sonnet readers went through 1,473 flagged rows on 949 buildings. They found 704 on the wrong building, 570 under an out-of-date city record, 71 mixed use, 25 with vanity numbers and 103 unclear.
- Running PAD on each ad's own address: of the 704, 544 land on the flagged lot itself, so the address gives no backing for a move. Only 8 land on another lot with apartments, and those still need their own backing.
- Modeling chose to keep these rows and set their lot's building facts to missing, leaving the mixed-use rows as they are. DI listed 1,274 ads in #975, and Modeling's lot features (#976) read that list.
- 1446 Bergen St links to its lot by address alone, with the placeholder BIN 3000000. 560 buildings link by address alone, and 167 of them have a placeholder BIN. Those 167 hold 1,412 rows; 44 of them also have an address score of 0, holding 422 rows.
- **Update, later on Oct 17:** the corrections ledger can now take a lot away from an ad when a reader judged it wrong and the city records back that up (#1010). An entry goes stale, and stops applying, if the building later gets a different lot. DI's 1,274 reviewed lots and a second batch of 152 (#1013) are in. On the latest build, 1,256 entries are live and 170 are stale, all of them buildings the pipeline has since moved to their other lot (#1006). The building check's list fell from 1,434 rows to 187, exactly the rows where the reader kept the lot. The rows file is unchanged.

### 6. Top-up equals a full build (#958)

On runs 1 to 16, a full build of runs 1 to 11 followed by a top-up of runs 12 to 16 gave the same rows file (1,746,791 rows) and the same ads file, byte for byte, as a full build of runs 1 to 16. The top-up re-read 93,898 ads for 22,298 new answers.

### 7. Fixture

A test builds the fixture's export end to end in 6.7 s. For any edit, `diff.py` lists every table's changes in 6.1 s on the fixture and 18.5 s on the 1% sample. The pipeline suite passed all 214 tests in 207 s on two workers.

### 8. Retired (step 9)

Deleted or stopped:

- the page-capture rewrite (#967);
- the captures (#949);
- the site's reads of the chain (#945), now on the ads and rows files;
- the builders' reads (#961 to #965), now on the records file;
- the collector's use of the page parser (#968).

The page parser itself remains, with its tests, as described at the top.

## Before and after

| Measure | Before (Oct 15) | After |
|---|---|---|
| Scrape to checked rows | Manhattan about 1.7 h after the scrape; Brooklyn none by 16:30; two threads ran 18 scripts by hand | 8.4 min after the last API call (23:38 ET last night), no hand steps |
| Build time | — | Top-up 152.5 s, full build 785 s (#958 proof) |
| Peak memory | Hand-run steps up to 8.1 GiB; two ran out of memory | 3.9 to 4.5 GiB, under a 5 GiB cap with swap off |
| Modal spend for the pipeline | — | $0; it runs on thelio |

- **Friday top-up, Oct 16:** it took 47 minutes, 42 of them waiting for the GPU lock. #957 freed the build from that lock.
- **Last night's top-up** rebuilt every ads model in 339 s, because #958 hadn't merged yet.
- **Dollars inside fits:** data preparation inside a Modal fit is unchanged, because fits still read the chain's datasets. Over the last 15 settled fits (Oct 13 to 16) it took a median 191 s, 6.3% of the GPU container's time, about $0.13 a fit. That changes once fits read a rows file by name and hash.
- **This morning's full build:** I started it by hand at 05:16 ET so Modeling could fit the new rows sooner. It was a full build because #958, #970, #971 and #980 changed its models. The script took 711 s (223 to plan, 465 for the records step). The unit used 12.3 minutes of wall time and 27.8 of CPU. The script peaked at 4,182 MiB. Its cgroup reached the 5.0 GiB cap with no swap, because the cgroup counts page cache, which the kernel trims at the cap.
- **The 07:15 timer build** ran on master with #985, #991 and #994. It read no new records and rebuilt the 17 models that depend on the two ledgers. The script took 173 s; the unit used 3.1 minutes of wall time and 6.7 of CPU, peaking at 4,213 MiB. Its rows file has 1,746,778 rows. Against the 05:28 file it lost the 15 rows #994 excludes, six rows changed bedrooms and five changed unit, as predicted. No other value changed.
- **Records step from an empty cache** (parsing every API record): 273 s.

## Unit matching

Unit matching isn't finished. No join goes into the ledger yet.

- Normalising labels (dropping "apt", leading zeros and the spellings of PH) joins 4.3% of unit pages, but only takes the lots above their legal count from 1,580 to 1,544.
- Most of the excess comes from brokers relisting an apartment every week or two under a new label, with the same layout and ask, each ad starting as the last one ends. The matcher links two unit pages of a lot when an ad of one starts within 7 days of an ad of the other ending, with the same bedrooms and baths and an ask within 3%, gross or net of free months. A merge is refused when ads on the two sides ran side by side for over a week at different asks. At 69 Mother Gaston Blvd, two chains ran side by side at $5,950 and $4,600, and they are two apartments.
- The matcher's count is a little looser than the city check's and puts 1,735 lots above their legal count. Joining every chain leaves 781. Joining only the 4,814 links whose ads also share a photo (used by at most 3 of the lot's units) leaves 1,467. Of the 17 labeled lots with splits or relabels, 10 fall within their count after the chains.
- Sonnet readers judged 60 sampled pairs:
  - 20 chain links with shared photos: 19 the same apartment, 1 not.
  - 20 chain links without shared photos: 12 the same, 1 not, 7 unclear.
  - 20 pairs that shared photos with no chain: 7 the same, 9 not. So shared photos alone are weak evidence.
- Floors in the labels give an independent check. Two linked labels give the same floor 66% of the time, against 37% for two alike units of the same lot. If the readers are right that 95% of the photo-backed links are true, the links without shared photos come out about 68% right (71% if every photo-backed link were true, 62% if 85% were). Floor plans give a lower figure: on the 3,237 links where both pages have a plan, 36% share one, against 53% of photo-backed links and 12% of alike units, which puts them about 56% right.
- **Next:** build the matcher into the pipeline as its own step, photo-backed links first. Each row will carry a relist unit beside its unit page, so a fit can choose to read it, and no unit page changes. The ledger's evidence rules stay as they are, since a shared photo or a relist isn't backing under them. The 22,112 links without shared photos need another signal, such as floor plans or stated sizes.
- **Update, later on Oct 17:** the relist step is in the pipeline (#1008). It runs only on lots with more apartments on StreetEasy than MapPLUTO counts, and joins two unit pages when their ads share a photo that rarely appears anywhere else. On the latest build it makes 3,533 joins, giving 2,603 relist units. Sonnet readers judged 50 sampled units from the ads alone: 92% of the units they could decide were one apartment, but only 67% of units with 4 or more pages were. The rows file carries each unit's page count, so a fit can keep only units of 2 or 3 pages. The pipeline suite passed all 218 tests.
- **A second signal, tested (#1027):** on lots over their count, 47,347 candidate pairs pass every relist test except the shared photo. Neither description text nor unit labels can join them. Brokers reuse descriptions across apartments: 26% of pairs judged to be two apartments have nearly the same text. Counting rare 4-grams (found on 2 or 3 unit pages of a lot), 28% of photo-joined pairs share five or more, against 3.0% of two-apartment pairs, so up to about 1,280 of the 2,765 unjoined pairs with that much shared text could be two apartments. Unit labels match in only 173 pairs (0.4%). The next try is a perceptual hash of listing photos, piloted on a small sample, to catch the same picture re-cropped or re-encoded under a new photo key.

### Photo-hash pilot (Oct 17, on Ben's OK)

The pilot fetched 2,917 photos through Oxylabs, about $3.33, with no retries or failures. Images were hashed in memory and none were stored. A match means two photos under different keys whose 64-bit hashes differ by 4 bits or fewer. The distances split cleanly: among unjoined pairs, 52 fall at 4 bits or fewer and the next is at 6.

| Pairs | Testable | Share a key | Hash match, no shared key |
|---|---:|---:|---:|
| Unjoined (pass every relist test but the photo) | 140 | 5 | 52 |
| Two-apartment controls | 100 | 8 | 4 |
| Readers' "same" | 27 | 22 | 2 |
| Readers' "different" | 10 | 7 | 1 |
| Readers' "unclear" | 5 | 2 | 0 |

- Leaving out pairs with a shared key, 52 of 135 unjoined pairs match (38%), against 4 of 92 controls (4.3%).
- Scaled to the 13,063 testable unjoined pairs, that is about 5,000 new joins. If every one of those pairs were two apartments, about 570 would match by chance, so at most about 11% of the new joins would be wrong, before the relist step's other tests. For description text that ceiling was nearly half. Only 92 controls stand behind the 4.3% rate: its 95% interval is 1.2% to 10.8%, which puts the ceiling anywhere from about 3% to 28%.
- The readers' judgments add little: they judged from text alone, and they called 7 pairs "different" even though the two ads share a photo key.
- Reach is limited: only 28% of unjoined pairs (13,063 of 47,347) have a usable photo on both ads.

**Full run options (withdrawn after the bigger pilot below; none is recommended):**

- 3 photos per ad: about 37,200 requests, $42, about 11 hours at 55 a minute. In the pilot, 44 of the 52 matches appear within each ad's first 3 photos.
- 10 photos per ad: about 85,500 requests, $97, about 26 hours.
- 3 photos per ad with controls (recommended): adds the 6,396 testable two-apartment pairs to pin down the false-match rate. About 52,000 requests, $59, about 15.5 hours.

The run would go in chunks of about 20 minutes, releasing the Oxylabs lock between them so collectors don't wait. Hashes would be stored as a dated table (photo key, SHA-256 and the two hashes, no images), and the relist step would treat a hash match like a shared rare photo. This adds data derived from images, which goes beyond the brief's rule of API records only.

The pilot is written up under "Photo hashes" in `docs/data/pipeline.md` (#1057), with the control rate's interval.

Ben asked (20:57Z) how the plan handles amenity and neighborhood photos. As planned, one hash match is enough, so a re-uploaded amenity photo, or one floor plan shared by stacked units such as 4A and 5A, could join two apartments. The controls measure this but nothing filters it. On Ben's word, a bigger pilot of about $10 (hard stop at 9,000 requests) tests a fix. It fetches every photo on a sample of lots, so a hash on several apartments' ads counts as a building photo, and adds same-lot, same-layout controls including stacked units. Each matched photo gets a label (room, amenity, exterior, street, floor plan). It compares four rules: one match, building photos removed, two or more matches, and floor plans excluded.

A free check on the first pilot's matches (`lanes/photo-hash/check.py`, `check.out`) scored three rules already, among 135 unjoined and 92 control pairs with no key in common, with exact 95% intervals:

| Rule | Unjoined | Controls |
|---|---:|---:|
| Any one match | 38.5% (30.3–47.3) | 4.3% (1.2–10.8) |
| Two or more distinct matching photos | 30.4% (22.8–38.9) | 1.1% (0.0–5.9) |
| Ignore photos whose key is on a third unit page | 19.3% (13.0–26.9) | 2.2% (0.3–7.6) |
| Both of the last two | 13.3% (8.1–20.3) | 1.1% (0.0–5.9) |

- Unjoined matches share a median of 4 photos, and 41 of the 52 share two or more. The two-photo rule drops the reader-"different" pair and keeps both reader-"same" pairs.
- The third-page rule halves the unjoined matches. The third page may be another stray page for the same apartment, so the rule is too blunt until the pilot fetches every ad on the lot.
- The API gives no photo type or caption, only keys under photos, floorPlans, tour3dUrl and videos. No match used a floor-plan key, but a plan uploaded as a photo can only be caught by the pilot's labels.

The $10 pilot's selection (`lanes/photo-hash-lots/select.py`) is 29 lots over their legal count with unjoined pairs, 7 in Manhattan and 22 in Brooklyn: 22 small lots of up to 300 photos and 7 larger buildings of 300 to 1,200. It fetches every ad on those lots, 1,505 ads at up to 25 photos each, plus their floor plans: about 7,090 requests, $8.10 and 2 h 10 min. The lots hold 469 unjoined pairs, 157 controls (same bedrooms and baths, on the market together, 32 of them stacked units) and 92 pairs sharing a rare key as a reference. A photo matching the ad's own floor-plan image counts as a plan. A hash cluster on more than 3 unit pages, or on ads of two apartments known to differ (leaving out the pair being scored), counts as a building photo. A photo on 2 lots counts as one too.

### Bigger photo pilot: result (Oct 17, 5:11 to 7:32 PM ET)

It sent 7,087 requests (6,886 photos, 201 floor plans), every one returned an image, and it cost $8.08. It scored the 657 pairs on the 29 lots where both ads had photos. Scores and scripts are in `lanes/photo-hash-lots/`.

**Ben's concern holds.** Within a building, 74% of pairs of different apartments share a matching photo, about the same as unjoined pairs. In 84 of the 88 matching two-apartment pairs, every matching photo also appears on other apartments' ads. The first pilot's 38.5% against 4.3% came from pairs across the city and does not hold within a building.

Match rates, exact 95% intervals:

| Rule | Unjoined (415) | Different lines (119) | Stacked (29) | Rare-photo pairs (91) |
|---|---:|---:|---:|---:|
| 1. Any matching photo | 74.2% (69.7–78.4) | 73.9% (65.1–81.6) | 55.2% (35.7–73.6) | 93.4% (86.2–97.5) |
| 2. Building photos dropped | 7.0% (4.7–9.9) | 3.4% (0.9–8.4) | 6.9% (0.8–22.8) | 47.3% (36.7–58.0) |
| 3. Two or more matching photos | 62.2% (57.3–66.9) | 68.9% (59.8–77.1) | 48.3% (29.4–67.5) | 84.6% (75.5–91.3) |
| 4. Floor plans dropped | same as rule 1: no matching photo was a floor plan | | | |
| 5. Rules 2 and 3 together | 5.1% (3.2–7.6) | 2.5% (0.5–7.2) | 0 of 29 (0–11.9) | 33.0% (23.5–43.6) |

Three pairs of apartments with the same label matched under no rule.

- A full run would add joins only for pairs with no key in common. There rule 5 matches 17 of 220 unjoined pairs, 7.7% (4.6–12.1), against 0 of 62 two-apartment pairs (0–5.8). Rule 2 matches 25 of 220, 11.4% (7.5–16.3), against 3 of 62, 4.8% (1.0–13.5). Pairs on one lot share photos, so the real intervals are wider: the 17 rule-5 matches come from 7 lots, 6 of them from one lot.
- Rule 5 finds only a third of the rare-photo pairs. Taking the two-apartment upper bound of 5.8% against 7.7%, up to three quarters of its new joins could be two apartments.
- The building filter also drops real matches. In 35 of the 85 matching rare-photo pairs, a matching photo also shows on two apartments known to differ, which fits brokers reusing one unit's photos for another.

**Decision:** no full run, and photo hashes stay out of the relist join. On Oct 18 Ben closed the photo approach: no labels and no further photo fetches.

### Buildings over their legal count (Oct 18, rows-8dee810f)

Ads on the market from Oct 17, 2025 to Oct 16, 2026 (173,195 ads on 28,241 lots), against MapPLUTO 26v2's residential units. 199 lots with a count of 0 or blank are left out (45 in NB9). Script output: `lanes/overcount/lots.csv`.

- By unit page over all ads: 1,742 lots (115 in NB9); over the fit's kept ads: 1,400 (80).
- By current unit (after the ledger, label joins, history splits and relist joins): **1,217 lots, 72 in NB9**, with 6,495 units of excess (630 in NB9). Over by 1: 376 (17); by 2: 217 (9); 3 to 5: 306 (21); 6 to 10: 184 (9); more than 10: 134 (16). Half the excess sits on 146 lots (9 in NB9).
- All 1,217 hold 16,658 unit pages and 20,409 ads; the 72 NB9 lots hold 1,536 pages and 2,040 ads. The median over-count lot has 8 pages (13 in NB9), and the 90th percentile 25 (38 in NB9).
- Not all are duplicates. On 45 lots a DOB certificate covers every unit seen (347 units of excess; 5 lots and 146 units in NB9), and only 313 of the 1,217 have a certificate in our tables. 36 lots hold more than one StreetEasy building (525 units; 6 lots and 227 units in NB9). 27 were built in 2023 or later (806 units). Top lots with a legal count of 1 to 8 and 30+ units look like wrong lot links.
- Ben was offered a manual review page (one card per lot, marks becoming unit joins with his review as evidence) for the 72 NB9 lots, the top 25 or the top 146. The NB9 page is up at https://claude.ai/artifact/QFuSudrqHjauwHtZ3wn8W5 (private to Ben): 62 single-building lots without a covering certificate first, then the 10 explained by certificates or shared lots. Marks save to the page; nothing enters the ledger until Ben says a batch is done, then it goes in as a PR with a row diff.
- **#1136 (merged Oct 18):** when an ad's latest change fails the building check, the pipeline now takes the last change from the row's day on that lies within half to double the first ask, instead of falling back to the first ask. 72 of 1.74 million rows move.
- **#1139 (merged Oct 18), from Data improvements:** ads with free months are kept, and each row's latest ask becomes a net effective rent: ask × (lease term − months free) / lease term, from the ad's latest terms; asks from before the concession began are unchanged. Rows in the ten NB9 neighborhoods with West Chelsea go from 348,968 to 378,838 (+8.6%), almost all from 29,959 concession rows coming back. The median cut is one month in twelve (8.3%), the 90th percentile 20%. On 354 NB9 rows (1,175 citywide) StreetEasy's net effective rent matches none of the ad's prices, so the concession is counted from the last price. Review found 53 ads (17 in NB9) whose listed price already equals the net effective rent; they keep their ask. Modeling's 18:26 ET rebaseline runs on a clean NB9 folder built from master at 10:59 ET. Website is switching the site's current listings to net prices before Monday's 07:15 ET build, the first that can show these ads; that build also reparses every record once (about 17 minutes extra). Labels for the 1,735 matching photos (about $2 more, $10.06 in all) would show whether a rule on room photos alone could separate apartments. They wait on Ben's "add the labels"; without it the pilot is written up as is. The write-up is merged as #1088.

### Rebuild for DI's corrections (Oct 17, 4:55 PM ET, on Ben's word)

The build ran from 4:55:05 to 4:58:15 PM ET (3 min 10 s wall, 7 min 5 s CPU) from master fd80453d. systemd reports a peak of 5 GiB, which is the unit's cap and counts page cache; the build script's own peak was 4,174 MiB. Output: `rows-a70904579c373791.parquet`, sha256 a70904579c3737914684263c63d0c291ab3392c1dbf8c5df9059d5f0e8e7fc7f.

Against the 7:17 AM build, it has the same 1,746,778 listings, none dropped or added. DI's ledger PRs #1036 to #1063 change:

- full and half bath counts on 1,593 rows. The `bathrooms` column keeps the ad's own figure, as the old chain did, so a fit reading it misses these;
- bedrooms on 183 rows (196 corrections less 13 withdrawn);
- square footage on 71 rows, by a median of 150 sq ft down;
- the latest ask on 5 rows with a placeholder price such as $4,444 or $9,999.

A new relist unit column puts 7,241 rows from 3,526 unit pages into 2,597 relist units. Modeling and DI have the path and hash.

## Also merged since last night

- **#1079** (commit 232c33d7, Oct 17 evening): when a building's address points at a lot whose building came down, the building stays on that address lot instead of moving to the neighbouring footprint. A date check suggested by Data improvements applies it only when every ad ran before MapPLUTO first showed the lot without apartments. On the current export 26 buildings and their 340 ads change lots, with the row count unchanged. Without the check it would have covered 36 buildings and 415 ads, including 8 newer buildings whose ads came after the old building was gone. The lots step takes 2.3 s and now reads the ads tables, so an ads-only update also rebuilds the two lot steps (about 12 s more). Modeling has been told.
- **#970:** an ad's layout, amenities, views and windows now merge only up to its last ACTIVE answer. 7,891 ads have one, and 657 rows change, mostly in their record counts. 12 conflicts between records resolve to the ACTIVE value.
- The rental flags (furnished, short term, concession) still merge over every record, because a closed record can be the only one that states the terms behind the ask. Ad 5178211 asked $4,595 in its ACTIVE records; only its DELISTED record gives $5,017 with a month free on a 12-month lease, which nets to $4,595.
- **#969:** descriptions are cut at the same point. On runs 1 to 16, StreetEasy had cut the latest description of 1 listing among the 343 with an ACTIVE record. 57,689 of the cohort's 58,032 listings have no ACTIVE record, because the backfill fetched them after they closed, so they keep the latest text.
- **#980** brings DI's latest-ask-v9 into the pipeline. A price change dated more than a week after an ended ad's off-market day drops out, unless the ad came back on the market after that day. Brokers reuse an old ad's record for a later ad of the same apartment, so such a change carries the later ad's ask. In DI's run the rule changed 9,601 of 1,751,152 rows. In the 05:16 build it changed the latest ask of 9,526 rows. In the fit's nine areas 2,678 rows changed, and 2,664 of them match DI's run with the same ask; the other 14 belong to ads the chain's datasets lack. Modeling has the new rows for a fit of their own.
- **#985** makes the window for stale price changes a setting. The served build keeps v9's 7 days. At -1 it follows DI's latest-ask-v10, which drops every change dated on or after an ended ad's off-market day, with v9's exceptions. On the Oct 16 export, a build at -1 moved the latest ask of about 105,000 listings against v9. It agreed with DI's v10 run on all but 7 of the 104,979 listings either one moved, and changed 40 more that the run lacks.
- **#991** brings DI's reviews of 870 Broadway and 444 West 20th Street into the unit ledger. Three splits give 870 Broadway's larger apartments units of their own, and a join puts 444 West 20th's garden page and page 1 in one unit. A split can now point into another split of its building, so the ledger gives the same unit IDs as DI's rules. Five rows change unit.
- **#994** (merged 06:40) imports quarantine-v34 and v35 and bedrooms-ad-v10 into the corrections ledger. It drops 15 rows, gives six rows at 68 Clinton Street three bedrooms, and changes nothing else.

## Next

- Modeling agreed the order for moving the chain's rules into the pipeline.
  - **#1090 (merged, two reviews):** an unknown elevator or pet policy is filled from the ad's own description, as the chain's elevator-from-ad-v1 and pets-from-ad-v2 did. Against master's rows with the two chain rules applied, only elevator and pets differ. 81 of NB9's rows differ (0.027%), under the 0.25% bar, so no refit. Across all scraped areas, 96,800 rows differ (5.54%), because the chain rules only ever filled NB9; those fills are new data. Modeling's fit for them takes about 3 hours, over the 1-hour cap, so it waits on Ben's approval or a redesign.
  - **#1093 (merged):** the West Coast wing rule is a new `split_building` entry in the unit ledger. Its three-digit units get the building name the-west-coast-west-wing and keep the building ID, so the lot is unchanged. On the Oct 17 build, 321 of the building's 527 rows (377 of its 617 ads) move to the wing. Evidence: Ben's floor plans of units 620 and 9L and the Landmarks Preservation Commission's 2003 Gansevoort Market report. It reproduces the chain exactly: 0 of 350,202 served rows differ, so no refit. Review found that a pattern Python accepts could crash DuckDB, so each entry is now checked in DuckDB when read, with tests.
  - **#1094 (merged, two reviews):** the chain's unit-labels-v17 rule. Labels join on each ad's page unit, before the ledger's splits, as the fit does. On a fresh build, 734 of 350,202 rows change unit (0.210%) once the fit's other unit rules run on both sides, under the 0.25% bar, so no refit. 599 of those rows only take another ID. The 88 extra floor-word joins (about 26 likely false, by a Sonnet sample) stay a separate measured change.
  - **#1095 (merged):** the chain's unit-splits-v4, cutting units by bedroom history. With v4 alone on both sides it matches the chain on all 350,202 rows. With all of the fit's unit rules, 4 rows differ (0.0011%), all at 249 West 29th Street 3E. The chain's review splits off a 2017 studio ad there, but no other ad, size or floor plan backs it, so the ledger holds it back. No refit. The pipeline applies building-joins-v1 and unit-reviews-v5 itself, so a fit on its folders can drop them; that changes only the one held row.
  - That completes the ports Modeling agreed on Oct 17. No fit config reads a pipeline folder yet, so the served model's data is unchanged. The handoff note is updated in #1098.
  - **Floor joins (closed as a miss, Modeling agreed):** in two fresh random samples of 50 and 30 floor joins, Sonnet readers found 1 false join in 80 clear reads. Each guard tried (two ads live at once, a size gap, a bedroom-median guard) splits more true joins than it fixes, so `analysis.label_units` stays as it is. The earlier 14 of 40 came from a selected group: the 88 units the pipeline joins and the chain keeps apart.
  - `fields-review-v3` needs no port: it leaves rows unchanged and only takes v1's 16 corrections out of the fit's rules, and the pipeline never read v1. Both are recorded in the handoff and pipeline docs (#1099).
  - **#1103 (merged Oct 18, 2:31 ET):** when the export hasn't changed, the records step reuses the file it already wrote, instead of spending about 90 s of a 185 s build rewriting and hashing the same 3.4 GB records file.
  - **#1107 (merged Oct 18, about 3:15 ET):** the unit-month check now runs a second time, on label units after the corrections ledger. Before, two pages of one apartment (often two brokers' ads) could each keep a row in the same month, so a fit counted the apartment twice. It touches 0.354% of NB9's rows and 0.612% across all scraped areas, above the 0.25% line, so it gets its own fit.
    - Sonnet readers checked 30 random months with two bedroom counts: 23 were one apartment (18 with a flex room or changed layout, 5 with a miscoded ad), 6 were false joins and 1 was unclear. The chain's rule is kept: a month with two layouts drops all its rows.
    - In a month with several ads the check keeps the ad posted last. That ad has the month's last ask in 93.6% of such months; otherwise a dropped ad cut its price a median of 11 days later, by a median of 2.2%.
    - Modeling agreed. The NB9 fit queues behind P1, which waits on budget; an all-areas fit exceeds the one-hour cap and is recorded as blocked. The 7:15 ET production build picks up the merge.
  - **#1116 (merged Oct 18):** ledger files are keyed by name and SHA-256 instead of absolute path, and the models find them through `PIPELINE_LEDGER` at run time. A build from a second checkout on the same state now rebuilds 0 of 62 models in 46 s, where it rebuilt 24 (about 3 minutes). Review caught that SQLMesh restores the environment after loading `config.py`, which would have stopped every production build; `build.py` now sets the variable around its plan, with a test that builds with it unset. The 7:15 ET build rebuilds the ledger models and everything downstream once (about 3.5 minutes) with rows expected unchanged. A hand-run `sqlmesh plan` needs `PIPELINE_LEDGER=$PWD/pipeline/ledger`, as `docs/data/pipeline.md` shows.
  - **Oct 18 07:15 ET production build (passed, finished 07:39):** the first with the ported rules, #1107 and #1116. It wrote `rows-8dee810f` with 1,736,330 rows, 10,448 fewer than the build before, mostly from the label-month check. Row by row it matches the ledger-names lane build except for the 10 bedroom counts that #1113 and #1118 added since and 9 rows that move to another piece of their unit as a result.
  - It took 24.6 minutes (script peak 4,673 MiB) instead of about 3: the record parse took 1,040 s because #1090 changed the parser, and the records step re-read all 2.18M records in 293 s because #1103 changed its code. Both are once per code change. One lasting cost: a full parse now takes 14 to 17 minutes, against about 7 before #1090, so a later parser change costs that once; top-ups parse only new records. Handoff updated in #1117.
  - **#1124 (merged Oct 18):** the elevator and pet readers skip any description with none of the words their patterns need, which halves the ad-text reading time (1,252 s to 594 s of CPU). On all 1,730,238 distinct descriptions in the export, no reading changed. Review found the tests missed some words, so each word now has a case that fails if it is dropped; 290 pipeline tests pass. Monday's 07:15 build reparses every record once (about 15 minutes), with rows expected to match Sunday's apart from ledger changes.
  - Modeling's NB9 rebaseline folder, with #1123's 318 East 19th join, is `lanes/loader/out/nb9-chelsea-named-rows-7db2b8e7-e6660181` (348,968 rows). It already applies the data rules, so the fit passes no `--data-rules`.
- `analysis.lot_facts` should read DI's file of 1,274 ads to take off their lots (in `config/reviews` since #975), before fits read the rows file. Modeling gets notice before it merges.
- Then DI's suggestion: drop a late change to a repeated-digit ask, such as $9,999, when it moves the ask by 1.2x or more.
- The docs update (#998) is in review.

## Corrections to earlier messages

- I said earlier that a top-up's OxyLabs spending needed your OK. Your standing permission of Oct 15 covers it.
- #957 merged at about 01:08 ET, not 01:20.
