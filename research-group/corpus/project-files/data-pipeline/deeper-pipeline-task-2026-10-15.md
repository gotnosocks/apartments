# A deeper version of the data pipeline task

*Written 2026-10-15 for Ben. Sources: the repo at master `11863160` (read in a clean copy), the Data improvements and Data collection handoff notes, Data improvements' live status on the four-region build, and read-only measurements taken on thelio. Nothing was changed. Where something is my judgment rather than a checked fact, it says so.*

*Revised 2026-10-15 at about 20:25 UTC after Ben's feedback: the project moves to API data only, the implementation language is free, the scraper thread has agreed the boundary for the raw data format, and the pipeline runs after each backfill and incremental scrape rather than on a daily schedule. The answers below are updated where that changes them, and section 5 holds the revised task.*

Your task as written: *"Optimize the raw to fit-ready data transformation. Simplify and reduce the code, make it run faster and more cheaply, refactor and reorganize the code to be more agent friendly."*

## What the pipeline is today

From raw capture to a fit, the data passes through five steps.

1. **Capture archive.** One SQLite database per crawl plus gzip page bodies. Raw HTML and raw API JSON are both kept, with capture times. API answers are first rewritten to look like page-crawl captures, which takes about 7 ms an ad, or about 3 hours for the four new regions (`docs/data/graphql-collection.md`).
2. **Granular transform.** Parses the captures into Parquet tables. It took 15 minutes for the 1.71 million ads of the four new regions. It keeps each ad's whole StreetEasy record: description, every price change and status change, rented price, days on market, photo and floor-plan keys, and earlier listing periods. It also keeps 30.6 million history events, not yet deduplicated.
3. **History and cohort build.** Turns the transform into one row per unit and month, in memory. It needs about 44 KB of memory per row (`docs/TODO.md`, measured Oct 6). The four new regions (1.40 million rows) don't fit in thelio's 15 GB, so they were cut by hand into 16 building slices (#848). One slice stopped on the memory cap and had to be resumed.
4. **Side tables.** Each is a dated snapshot of its own: the building-to-lot registry, PLUTO, footprints, landmarks, descriptions, latest ask and the elevator and pets fills. The registry asks the city's GeoSearch service about one building at a time, and the new regions have 61,571 buildings. Several fetches are written for Manhattan only and need adapting for Brooklyn.
5. **The fit-ready table itself is never saved.** Every Modal fit rebuilds it in memory inside the GPU container. It loads the cohort file, applies the data rules, builds the feature set and prepares the model, every time (`frontier/src/rentfrontier/run.py:530-536`).

How it is organised:
- **Rules are code.** There are 76 data rules, each version its own Python function. That includes 30 quarantine versions, each a full cumulative copy of the last, about 15,000 lines across the quarantine files. No single place says why a given row was dropped or changed. You find out by searching each rule's file.
- **Features are one 5,200-line file.** It holds about 150 feature sets, chained up to 12 levels deep, with 103 hard-coded snapshot paths. The current NB9 chain uses about 12 of them. Nothing is marked retired.
- **Builds aren't commands.** Each new region's build is a hand-written shell script in `/data1/apartments/tmp`, not something in the repo.
- **Tests are mostly synthetic.** There are about 650 tests, mostly unit tests on made-up tables. There is no end-to-end test on a small real fixture, and the real-data tests skip anywhere but thelio.
- **Two of everything at the front.** Page and API parsers carry near-identical row logic, there are two transform runners, and legacy import paths and one-off migration tools are still wired into the command line.

One more thing it does: the cohort step drops every listing with a coded concession (a free month or a net effective rent, which StreetEasy codes from 2020). An earlier estimate put that at about 18,000 rows, dropped more often in large buildings (`modeling/next-actions-2026-10-13-workings/candidates/concession-rows.md`). The rules that run at fit time can only drop or change rows, so getting those rows back needs a rebuild.

## What it costs today

These figures were measured on thelio, read only, on Oct 15.

**Modal: little.**
- Data prep inside a fit (load, rules, features, model setup) took 221 s of the latest NB9 fit's 2,970 s. That is about 7%, or about $0.16 of its $2.19.
- Across the last 15 fits, data prep took 111 to 221 s.
- Most of it is the feature build. On thelio, starting cold, loading took 9 s, the 13 rules 39 s and the feature build 116 s, peaking at 2.4 GB.
- For comparison, the scoring steps after sampling (PSIS-LOO 472 s and variance shares 295 s) took 26% of the same fit. They're outside this task, but more of the Modal money goes there.

**thelio: hours, with memory near the ceiling.** The four new regions, step by step:

| Step | Wall time | Peak memory |
|---|---|---|
| Rewrite API answers as page captures | about 3 h (documented estimate, 7 ms an ad) | not recorded |
| Snapshot | 9 min | |
| Granular transform | 15 min | under a 3–4 GB cap |
| Collection audit and unit spelling aliases | 8 min | under a 3–4 GB cap |
| Slicing | 2 min | 3.1 GB |
| History and cohort (16 slices) | 35 min, plus 7 min after a resume | 6.4 GB with swap; 5.4 GB |
| Regions | 2 min | 8.1 GB |
| Latest ask | 3.5 min | 6.4 GB |
| Descriptions | 14 s | 7.0 GB plus 2.6 GB swap |
| Geocode Manhattan, 14,767 buildings | 54 min, 59 s of it computing | 90 MB |
| Geocode Brooklyn, 46,804 buildings | failed after 65 min; the rerun needs about 2.8 h | |
| Lot, footprint, landmark and PLUTO fetches | still running at 15:30 ET | |

The geocoder sends one request at a time with a 0.1 s pause, so it spends about 98% of its time waiting on the network. The memory peaks of 6–8 GB are on a 15 GB machine that also runs fits.

**People and calendar time: the real cost.**
- No step is one command. The four-region build is a 32-line script in `/data1/apartments/tmp/api-build-20261015` with its own copied code tree.
- Every step after the alias table was launched by hand as its own unit.
- This afternoon Data improvements spent its time slicing, resuming a slice that hit the memory cap, fixing a building name that stopped the Brooklyn geocode, and adapting fetches written for Manhattan.
- Disk: `/data1` is 83% full (163 GB free), and snapshots take 308 GB of that.

**Raw material on disk.**
- The API store keeps each ad's raw JSON, about 21 KB compressed. It includes dated price and status changes, rented price, net effective rent and months free, earlier listings of the unit, and photo and floor-plan keys.
- Page crawls keep raw HTML with photo URLs and price histories.
- No photos are stored anywhere. Floor plan images exist for 70 listings.

## 1. What a top professional would do that you aren't asking for

By "top professional" I mean the kind of research data engineer who builds the data behind a published price index or an economics paper. For them, the pipeline's job is a table whose every number can be traced to the evidence behind it, and which anyone can rebuild exactly. Small, fast and cheap follow from that; they aren't the goal.

1. **Fix the output before touching the code.** Write down what one fit-ready row is, what each column means, as of what date, and which capture it came from. Then hold every rewrite to reproducing today's tables exactly, or to explaining each difference by name. "Simplify" without that check is how silent data changes reach fits.
2. **Measure before optimising, and pick the right measure.** The numbers above show the money isn't where "cheaper" would look: data prep is 7% of a Modal fit. The cost is hours on thelio and an agent's afternoon. So the measure a professional would use is the time from a finished scrape to a checked, fit-ready dataset with no hand steps, along with peak memory. "Too big for memory" is usually fixed by a different data layout, not by more slices.
3. **Make corrections data, not code.** Keep one ledger of evidence-backed decisions in place of 76 rule functions and 30 cumulative quarantine copies. Each entry names the row, the field, the old value, the new value or a hold, the reason, and a pointer to the evidence. A rule version becomes a snapshot of the ledger. Then "why was this row dropped?" is one lookup, and your rule that corrections need independent evidence is enforced by the format itself: no evidence pointer, no entry.
4. **Treat identity as the main problem.** Most of the serious errors found this month were identity errors:
   - 14 towers joined to the wrong lot (about 3,900 rows);
   - Brooklyn ads filed under Manhattan buildings;
   - the same ad filed under two buildings;
   - 16,524 groups of unit spellings;
   - 20,900 ads dropped as unit mismatches.

   A professional makes the chain from ad to unit to building to lot its own step, with a recorded match score and a measured error rate, instead of patching misjoins as they surface.
5. **Keep each ad's whole life, and flag rather than drop.** Latest ask should be one view of an event log (listed, each price change, rented or withdrawn, days on market), not the only thing that survives. The new goal's market-reaction test, repeat-rent comparisons and the latent-ask idea all need those events, and the raw records already hold them. Exclusions such as concessions, furnished or short stays, price limits and quarantine holds should be flags with reasons that a fit filters on. Then a question like "what is a free month worth?" never needs a rebuild.
6. **Date every outside fact.** Every join to city data should be "as of the ad's date" by construction, using the release that was public then. Today's value is kept only where the city corrected a measurement and the building itself didn't change. That is the lesson of the PLUTO-as-of fits.
7. **Build once, read many times.** A fit should read a finished, hashed table that anyone can open and compare. This saves only about 3.7 minutes and $0.16 a fit; the bigger gain is that the table a fit read exists as a file. Only what changed should rebuild: fixing 14 buildings' lots shouldn't need hand-made "lots2 twin" feature sets.

Deleting dead code follows from these. Anything no current fit or check reads goes, and its results stay in the record.

## 2. The rawest material, instead of what has been digested

- **The API records themselves.** With the move to API data only, the raw material is each API response, kept verbatim with its capture time, and each ad's full record inside it. Don't start from the cohort file or the coded columns. Almost everything in that record is thrown away or reduced to a latest ask further down: the description, every price and status change, rented price, net effective rent and months free, days on market, earlier listings of the unit, its `propertyId` and `buildingId`, and photo and floor-plan keys. Read the records directly, without first rewriting them as page captures, which saves the 3-hour write and the page-crawl rules that come with it (unit-page stand-ins, superseded routes, gap observations). The page-crawl archives become a one-time reference for checking the move, then retire.
- **Photo and floor-plan keys, carried through.** No images are stored today, and floor plans exist for 70 listings. The pipeline doesn't need to fetch images, but it should carry each ad's keys through to its output, so condition and room measurements can attach later without anything being re-parsed.
- **Events as events.** The 30.6 million history events in the four-region build, deduplicated into one event log per listing, and accumulated across captures. StreetEasy shows only a fixed number of history events, so newer events push the oldest out (`docs/data/graphql-collection.md`). Each top-up's re-read adds what's new, and the log keeps what StreetEasy has since dropped. The boundary belongs between the collector and the pipeline: the collector keeps responses verbatim, and the pipeline derives events. That way a parsing fix never needs a re-scrape. The scraper thread agreed to this boundary (relayed by the coordinator, Oct 15). It already keeps every response verbatim with its request, run, region, fetch time and Oxylabs job. It will add an append-only export, one per run, of every ad record version, plus a request index that DuckDB reads directly, with the columns to be agreed when the task runs. The page-capture write step has two readers to move first: Data improvements' analysis inputs and the website's current-listings publish.
- **City records in bulk and with dates.** These replace one web lookup per building:
  - the Property Address Directory (PAD), which gives every address range's lot (BBL) and building (BIN) offline;
  - building footprints with BIN, so "one lot, two buildings" cases like The West Coast are handled by the data rather than by a special rule;
  - every MapPLUTO release with its publication date;
  - landmark designation dates;
  - DOB certificates of occupancy, which give legal unit counts and floors.
- **The pipeline's own leavings.** What each step dropped and why: the transform's exclusions, the collection audit and every quarantine hold. A table is only as good as what it silently leaves out.
- **The machines' own meters.** Use systemd's accounting of wall time and peak memory per step, the Modal ledger and each fit's recorded stage times, not estimates.

## 3. Methods and tools they would use

- **The language, chosen by fit.** Python was chosen for the modeling and stays there. Most of this pipeline is relational work: deduplicating, joining, windowing and joining as of a date. SQL on DuckDB does that in the fewest lines and works beyond memory. SQLMesh or dbt add the build graph, incremental runs, tests and column-level lineage on top. My recommendation is DuckDB SQL under one of those, with a small typed language only where SQL is awkward. A professional would settle it with evidence, not taste: build one real step (latest ask) in the candidate stack, and compare lines of code, wall time, peak memory and the answer against today's code.
- **Profiling.** `py-spy` shows where time goes, `memray` shows where memory goes, and systemd accounting gives each step's peak memory and CPU time.
- **Out-of-core column processing.** DuckDB (already a dependency) or Polars working over Parquet split by borough and building, in place of pandas row loops and JSON-lines files. History, cohort and latest ask become window queries over the event log. DuckDB spills to disk when memory runs out, so a region of any size builds on thelio without hand slicing.
- **Event sourcing.** Captures become deduplicated events, and events become views (latest ask, first ask, days on market, how the listing ended).
- **A declared build graph with caching by content.** Each step names its inputs and outputs and is keyed by a hash of its code, inputs and settings, so only what depends on a change rebuilds. Dagster's assets or Hamilton do this, and so does plain `make` with hash stamps. One catalog file names every dataset, snapshot, ledger version and feature set, replacing the hard-coded paths.
- **Data contracts.** A schema check (pandera, or DuckDB constraints) on every step's output, plus rules that must always hold:
  - one row per key;
  - asks within range for their bedroom count;
  - a unit's floor no higher than its lot's floors;
  - units per building no more than the legal count;
  - the ad's borough matching its lot's borough.
- **Record linkage.** Ads are linked to units first by the API's own keys (`propertyId`, the unit's listing history, `urlPath`), with spelling rules only as a fallback. Splink (the standard probabilistic matching method, running on DuckDB) covers what the keys leave open and links buildings to lots, storing a match weight for each link. Its error rate is measured on a random labelled sample. Lots and buildings come from an offline PAD lookup. My estimate is minutes for the 61,571 new buildings, against about four hours of web lookups. GeoSearch already reads PAD, so the matches should agree.
- **As-of joins.** DuckDB's `ASOF JOIN` or Polars' `join_asof` against each source's dated releases.
- **Golden-master and differential tests.**
  - Golden-master: rebuild today's tables and compare them row by row and column by column.
  - Differential: compute key steps such as latest ask a second, independent way and compare the two answers.
- **Planted-error tests for the checks.** Inject known errors into a copy of the raw captures and confirm each check catches them.
- **A small real fixture.** A few buildings' raw captures that run through the whole pipeline in under a minute in the test suite. This is what makes the code agent-friendly in practice: an agent can change one step and see every effect at once.

## 4. What, other than you or me, would show the result is right

1. **Today's code on the same input.** On the four-region API data, the new pipeline's table matches the current pipeline's, row for row and column for column. Otherwise every difference traces to a named ledger entry or a listed bug in the old code.
2. **Planted errors.** A copy of the raw captures is seeded with known mistakes: a building on the wrong lot, a studio priced like a three-bedroom, one ad under two buildings, one unit spelled two ways, a stale ask and a Brooklyn ad under a Manhattan address. The checks catch each one, and the number caught is the score.
3. **City records.** Units per building stay within the legal count from certificates of occupancy and PLUTO, unit floors stay within lot floors, and the offline lot and building lookup agrees with the current registry. Every disagreement is listed, and a random sample is checked against floor plans and the unit's other ads.
4. **StreetEasy against itself, once.** Before the page-crawl data retires, the API-built table for the page-crawl areas agrees with the page-crawl tables on the ads both have: the same unit, the same events and the same latest ask. Every disagreement is listed with its cause. The page crawls are an independent capture of the same ads, and this is the last chance to use them as one.
5. **The next real data.** The Friday top-up (first run Oct 16) goes through incrementally: only new and changed listings rebuild, and the result equals a full rebuild.
6. **The meters.** Before-and-after wall time and peak memory come from systemd's accounting, and dollars come from the Modal ledger.
7. **The model, last.** Moving the served model onto API-built tables changes rows, so it is a data change. It gets its own fit and is scored like any other rule, on paired PSIS-LOO under the evaluation framework, before it is served.

## 5. The rewritten task (revised)

> **Rebuild the raw-to-fit-ready data pipeline on API data: traceable, reproducible and incremental.**
>
> Rebuild the transformation that turns StreetEasy API captures into the table a fit reads, so that:
> - every value a fit reads can be traced to the API record it came from and to the evidence behind any correction;
> - the same inputs always give the same table;
> - a new backfill or top-up rebuilds only what it touches.
>
> Smaller, faster and cheaper code should follow from that design; they are not separate goals. "Agent-friendly" means an agent can change one step and see every effect in under a minute.
>
> The pipeline runs after each backfill and each incremental scrape (the Friday top-up today), not on a schedule of its own. The headline measure is the time from a finished scrape to a checked, fit-ready dataset with no hand-written steps, along with peak memory. For the four new regions, a 15-minute transform was followed by hand-sliced builds that peaked at 6–8 GB on a 15 GB machine, and by a geocode that looked up one building at a time (54 minutes for Manhattan, about 2.8 hours more for Brooklyn). Data prep is only about 7% of a Modal fit (about $0.16), so expect the savings in hours and attention, not Modal dollars.
>
> **Raw material: API records only.**
> - The project is moving to API data only, and the scraper thread is re-reading the old page-crawl areas through the API. The page-crawl archives become a one-time reference for checking the move, then retire. So do the page parser and the step that rewrites API records as page captures.
> - Each ad's API record holds every dated price and status change, rented price, net effective rent and months free, days on market, description, earlier listings of the unit, its propertyId and buildingId, and photo and floor-plan keys. Start from those, not from coded columns.
> - For lots and buildings, use the city's bulk, dated records: the Property Address Directory and building footprints (BBL and BIN), every MapPLUTO release with its date, landmark designation dates, and DOB certificates of occupancy.
>
> **Choose the language by fit.** Python is no longer required here; it stays for the model. Most of this work is relational: deduplicating, joining, windowing and joining as of a date. SQL on DuckDB does that compactly and works beyond memory. My recommendation is DuckDB SQL under SQLMesh or dbt, which provide the build graph, incremental runs, tests and lineage, with a small typed language only where SQL is awkward. Settle it with evidence: build latest ask in the candidate stack, and compare lines of code, wall time, peak memory and the answer against today's code.
>
> **Do this, in order.**
> 1. **Settle the raw layer with the scraper thread.** It has agreed to this boundary:
>    - The collector keeps every API response verbatim and never rewrites it. It already stores each response with its request, run, region, fetch time and Oxylabs job.
>    - It will add an append-only export, one per run, of every ad record version (listing id, capture time, hash, response id, run, region, verbatim record), plus a request index that DuckDB reads directly.
>    - The pipeline owns everything derived from there. Agree the columns first.
> 2. **Measure.** Measure the current pipeline end to end on thelio before changing it: wall time and peak memory per step from systemd's accounting, and each Modal fit's data-prep seconds. That is the baseline.
> 3. **Write the contract.** Say what one output row is, what each column means, its as-of date and its source. Freeze two references: the current pipeline's tables for the four-region API data, and the page-crawl tables behind the served and queued fits.
> 4. **Keep each ad's whole life.**
>    - Build one deduplicated event log per ad, adding events from every capture, so events that later drop out of StreetEasy's shortened history are kept.
>    - Latest ask, first ask, days on market and how the listing ended are views of the log.
>    - Exclusions become flags with reasons, not deleted rows: price limits, furnished, short stays, concessions and quarantine holds.
>    - Carry the photo and floor-plan keys through.
> 5. **Make corrections data.** Replace the versioned rule functions and cumulative quarantine copies with one append-only ledger.
>    - Each entry names the row, the field, the old and new value (or a hold), the reason, and a pointer to independent evidence: another ad, a floor plan, a stated size, matching units in the line, or a city record.
>    - The format refuses an entry with no evidence.
>    - A rule version is a snapshot of the ledger, and any row's changes are one lookup.
>    - Carry the existing holds and corrections across, keyed to API listing ids.
> 6. **Make identity its own step.**
>    - Link ads to units with the API's own keys (propertyId, the unit's listing history, urlPath) before falling back to spelling rules.
>    - Link buildings to lots and BINs offline from the Property Address Directory.
>    - Record a match score for each link, and measure the error rate on a random sample.
> 7. **Date every outside fact.** Join each one as of the ad's date. Keep today's value only where the city corrected a measurement and the building itself didn't change.
> 8. **Make it one build.** One command builds any named dataset from the raw layer.
>    - Each step names its inputs and outputs and is cached by a hash of its code, inputs and settings, so a top-up rebuilds only the listings it touched.
>    - Any region builds on thelio without hand slicing.
>    - One catalog file names every dataset, snapshot, ledger version and feature set, replacing the hard-coded paths.
>    - Fits read the saved, hashed fit-ready table.
> 9. **Delete the rest.** Remove whatever no current fit, check or site page reads; the record keeps the results. The page-capture write step can go once its two readers have moved to the new tables: Data improvements' analysis inputs and the website's current-listings publish.
>
> **It's done when checks outside the pipeline agree.**
> - On the four-region API data, the new pipeline's table matches the current pipeline's, row for row and column for column, or every difference traces to a named ledger entry or a listed bug in the old code.
> - For the old page-crawl areas, the API-built table agrees with the page-crawl tables on the ads both have: the same unit, the same events and the same latest ask. Every disagreement is listed with its cause before the page-crawl data retires.
> - Errors planted in a copy of the raw layer are caught: a building on the wrong lot, a studio priced like a three-bedroom, one ad under two buildings, one unit under two spellings, a stale ask, and a Brooklyn ad under a Manhattan address. Report how many were caught.
> - City records agree: units per building are within the legal count, unit floors are within lot floors, and the offline lot lookup matches the current registry. List every disagreement, and check a random sample against floor plans and the unit's other ads.
> - The Friday top-up runs incrementally, and its result equals a full rebuild.
> - A fixture of a few buildings' raw records runs the whole pipeline in the test suite in under a minute.
> - Before-and-after times, memory and dollars come from systemd's accounting and the Modal ledger, not estimates.
>
> **Keep the standing rules.**
> - Corrections still need independent evidence, and bulk ad reading uses Sonnet or Haiku.
> - Free checks on thelio need no approval. The Modal budget and the one-hour cap stand.
> - Don't refit for negligible changes. Moving the served model onto API-built tables changes rows, so it is a data change: it gets its own fit, scored under the evaluation framework, before it is served.
> - Data improvements runs the pipeline after backfills and top-ups, and the scraper thread owns the collector. Land the work in small reviewed PRs that keep a run possible at any time, and agree with each thread before changing a step it uses.
>
> This serves the project goal. The event log carries the market's own reaction (ads that sit, get cut or rent). Lot and building identity connect each ad to the physical city. Dated joins make the city's natural experiments usable.
