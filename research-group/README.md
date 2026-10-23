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
