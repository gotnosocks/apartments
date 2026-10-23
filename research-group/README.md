# Research group

Five members work on the project goal (`corpus/project-files/goal-proposal/deeper-goal-2026-10-15.md`):
GPT-6 Astra (`astra`), GPT-6.1 Sol (`sol61`) and Gemini 4 Argon (`argon`) through pi on thelio, and
Fable (`fable`) and Opus 5.5 (`opus`) as Claude agents. Each owns one research direction, with no
duplicates, and critiques the others.

## Corpus (same for every member)

On thelio, under `/data1/apartments/research-group/`:

- `corpus/project-files/`: snapshot of the project's shared files (modeling results, research
  reviews, goal proposal, handoffs, conference paper, defense page, blog post and its round-1
  comments). Refreshed by the group coordinator.
- `corpus/blog-discussion/`: every blog comment, Claude and outside models.
- the repo at `/data1/apartments/serve/master` (read only; code, docs, `docs/research-plan.md`).
- fit results: run directories and reports under the repo's fit output paths (see `docs/thelio-jobs.md`).
- the scraped StreetEasy data, read only, at `/data1/apartments/pipeline/datasets/`. Each
  pipeline build appends a line to `catalog.ndjson` naming its three files, and the last line
  points to the current build. On 2026-10-23 that build holds:
  - `records-086e22e48969b098.parquet` (3.4 GB, 2,260,764 rows): a row for each distinct API
    record of each ad, with `listing_id`, `collected_at` and `last_collected_at` (Unix seconds),
    `response_id`, `listing_type`, `record_sha256` and `raw_listing_json`. The JSON is
    StreetEasy's full record: the ad text in `description`, `pricing` (price, price and status
    changes, `monthsFree`, `leaseTermMonths`, `netEffectiveRent`, fee lists), `propertyDetails`
    (with the street address, but no coordinates), `propertyHistory`, `media` (photos, floor
    plans), `buildingId`, the brokerage in `legacy.sourceGroupLabel`, and the dates.
  - `ads-3775f6d9b3e028ca.parquet` (2,221,281 rows): a row per ad with parsed fields, first and
    latest asks, on and off days, days on market, identity and exclusion reasons, and the ad's
    fate in the pipeline. The comment at the top of `pipeline/models/analysis/ads.sql` in the
    repo lists the columns.
  - `rows-b3ddebf19af1dc1e.parquet` (1,969,284 rows): the kept rows, one per ad, with
    `asking_rent`, `latest_ask`, `latest_gross` and unit attributes. The model datasets under
    `/data1/apartments/frontier/datasets/` start from these.

  `docs/data/pipeline.md` in the repo describes each file. Read only the columns you need. A
  full read of `raw_listing_json` takes several GB of memory, so filter it in duckdb with
  `json_extract_string` under a memory limit of 2 GB or less.
- `corpus/data/`: one-off exports, each described in `corpus/data/README.md`.
- the web: search and read papers (hedonic pricing, NYC rents, spatial models, natural experiments).
  Claude members use WebSearch and WebFetch. Every member can also run `bin/web-search QUERY`
  (DuckDuckGo), `bin/web-search --scholar QUERY` (OpenAlex and arXiv) and `bin/web-fetch URL [CHARS]`
  (page as plain text).

## Board

`board/` is the shared channel. Every member reads all of it and posts with:

```sh
bin/board-post HANDLE "Title" [--reply-to POST_ID] < body.md
bin/board-read --list            # titles
bin/board-read --since POST_ID   # full text of newer posts
bin/board-read POST_ID           # one post
```

Posts are never edited; correct with a reply. Cite files and URLs.

## Your own folder

Each member keeps its work in `members/HANDLE/`: notes, code, analyses and model proposals. Put
model code there as a patch against `serve/master` or as a standalone module, and leave
`serve/master` itself alone (it is read only). Other members read your folder when they review
your requests.

## Fit requests

Modal fits are scarce, so members argue for them on the board:

1. Post `bin/board-post HANDLE "Fit request: NAME"` with
   - the design: the model change and the question it answers
   - the code path in `members/HANDLE/`
   - a runtime and cost estimate (fit-only, under 1 hour)
   - the written prediction, with numbers, made before the fit
2. The other members reply for or against, citing evidence.
3. The group settles which request takes the next slot. The group coordinator reads the thread,
   moves the chosen code into a reviewed PR, runs it with `ops/modal-fit` under the shared
   $10/day limiter, one fit at a time alongside the conference thread's queue, and posts the run
   path back to the board as a reply to the request.

Members never launch fits themselves; the sandbox has no Modal access.

## Data requests

The project's Data collection thread runs the StreetEasy scraper, and its Data improvements
thread maintains the pipeline and its corrections. Members can ask either thread for new data
or a pipeline fix:

1. Post `bin/board-post HANDLE "Data request: NAME"` with
   - what to collect or fix
   - why, and which direction it serves
   - a rough cost, such as the number of OxyLabs calls
   - how to check the result
2. The group coordinator passes the request to the matching thread and posts its answer back as
   a reply.

A one-off read-only export from data already on thelio is quicker: ask the coordinator in a
reply or a post, and the export goes to `corpus/data/`.

## Rules

- Model asking rents; the last ask before a listing goes off market stands in for the closing price.
- The held-out set is the latest ad of repeat-listed units, not a time forecast, and some features
  (size fills, building shares, Mundlak means) are being rebuilt from training ads only.
- Write predictions on the board before any fit, and record misses as misses.
- Members run inside `bin/sandboxed`: the repo and fit outputs are read only, and the only
  writable place is `/data1/apartments/research-group/`. Write there only, and never launch fits,
  GPU jobs or Modal jobs yourself.
- Free read-only checks on thelio need no approval. Keep them small: the machine has about 15 GB
  of memory and runs fits beside you.
- Modal fits run one at a time inside the shared $10/day budget and the ~1 hour cap, through fit
  requests (above).
- Keep a record per direction in `records/HANDLE.md`: hypothesis, evidence, checks, fit requests,
  results and misses.
