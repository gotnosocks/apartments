# Review: a queue of cards for Ben to judge

Ben asked on 2026-11-12 for a way to go through the data and flag what looks wrong
(labels, extraction, features, units that should be merged) that is easy enough to use on a
phone while watching TV. The **Review** section of the rents site (`/review`) is that tool. It
shows one card at a time with the evidence beside the question, takes an answer with one tap,
and stores the answers. A separate export step turns the answers into ledger lines, which merge
through a reviewed PR like any other correction.

## How it fits together

```
producer (thelio, free, read-only)        site (/review)                 export (a thread)
  reads pipeline data, sprint outputs  ->  shows one card at a time  ->  writes ledger batch files
  writes <root>/review/queues/Q/           appends each answer to        pipeline/ledger/*.ndjson
         meta.json, cards.jsonl            <root>/review/decisions.jsonl  pipeline/ledger/units/*.ndjson
                                                                          then a reviewed PR
```

- A **queue** is a folder `<site root>/review/queues/<queue>/` holding `meta.json` and
  `cards.jsonl`. Any thread can add a queue by writing those two files; the site reads them by
  file version, so no restart is needed. Write `cards.jsonl` under a temporary name and rename
  it, then `meta.json` the same way.
- An **answer** is one line of `<site root>/review/decisions.jsonl`, appended under a file lock.
  The newest line for a queue and card is the answer in force; `undo` clears it.
- The **export** (`python -m apartments.site.review export`) reads the answers in force,
  writes the ledger lines they call for, and records what it wrote in
  `<site root>/review/exported.jsonl`, so a second run writes nothing new.

## The evidence standard on the cards

The project's rule is that a correction to a coded field needs independent backing, not the
ad's own text or its price (Ben, 2026-10-15). For unit joins Ben set a stricter standard on
2026-11-12: shared photos, text and timing only nominate a link, since landlords reuse
pictures across units. Joining two labels needs at least one of them to fail an independent
test of being a real apartment, such as being absent from city records (HPD apartment numbers,
condo lots) or sitting outside the building's own grid of floors and lines.

So every card puts the independent evidence first: the building's label grid, the city's
counts and apartment numbers, stated sizes and floor plans, the unit's other ads. Photos and
text come after, marked as nominating evidence only.

Ben's answer is recorded in the ledger as an `owner` item, "Ben's reading in the review app",
with its date. The export copies the card's own backing items beside it, so the ledger line
shows what he saw. The ledger accepts an `owner` item as backing on its own; the cards are
built so that he never has to rely on that.

## meta.json

```json
{
  "queue": "unit-joins",
  "title": "One apartment under several labels?",
  "summary": "Chains of ads the repost screen links, with the building's labels and city records.",
  "question": "Are these labels one apartment?",
  "help": "Join only when a label fails a test of being a real unit: not in city records, or off the building's grid.",
  "answers": [
    {"code": "yes", "label": "One apartment", "key": "y", "applies": true},
    {"code": "no", "label": "Different apartments", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"}
  ],
  "built": "2026-11-12T05:00:00Z",
  "source": "src/apartments/review_cards/unit_joins.py on 3f2a1b0",
  "count": 412
}
```

- `queue` matches the folder name: lower case letters, digits and hyphens.
- `answers` lists two to four buttons. `key` is the keyboard shortcut on a laptop; `s`
  (Skip) and `z` (Undo) are taken. An answer
  with `"applies": true` means "do what the card proposes", and the export writes the card's
  proposal for it. Every queue also gets a **Skip** (decide later) and **Something else is
  wrong** (below), which the site adds itself.
- `question` and `help` are the defaults for each card. A card may override `question`.

## cards.jsonl

One card per line, in the order to show them (the site shows the first card without an answer
in force). Unknown keys are ignored, so producers can carry extra fields for their own use.

```json
{
  "id": "16-monitor-street-brooklyn:3e",
  "title": "16 Monitor St, Brooklyn: 3E, 3F, 3G, 3H, 3I, 3J",
  "subtitle": "Nooklyn · 1 bed · $2,600 · Aug to Sep 2018",
  "claim": "The repost screen links these six labels as one apartment taken down and posted again.",
  "proposal": {
    "ledger": "units",
    "line": {"change": "join_units", "building": "16-monitor-street-brooklyn", "units": ["3e", "3f", "3g", "3h", "3i", "3j"]},
    "evidence": [{"kind": "city_record", "detail": "The condo has eight unit lots, 1E to 4E and 1F to 4F; none for 3G, 3H, 3I or 3J."}],
    "summary": "Join 3F, 3G, 3H, 3I and 3J into 3E."
  },
  "options": [],
  "blocks": [ ... ]
}
```

- `id` is unique in its queue and stable across rebuilds of the queue, so an answer stays
  attached to its card. Use the thing the card is about (a building and unit, a listing and
  field), not a row number. It takes letters, digits and `. _ : ~ + -`, up to 200 characters.
- `proposal` (optional) is what an applying answer writes: `ledger` is `corrections` or
  `units`, `line` is a ledger line without `evidence`, `decided` or `source`, and `evidence` is
  the card's backing items in the ledger's kinds (`docs/data/pipeline.md`). The export adds the
  `owner` item, `decided` and `source`. A card with no proposal is a question only: its
  answers are recorded and exported as findings, not as ledger lines.
- `options` (optional) offers alternatives to the proposal, each `{"code", "label",
  "proposal"}`: for a bedroom count, "1 bedroom", "2 bedrooms" and so on. Choosing one is an
  applying answer with that option's proposal.
- `blocks` is the evidence, shown in order. Each block has a `type` and a `title`, and
  `"nominating": true` marks evidence that only nominates (photos, text, timing), which the
  site shows under a label saying so.

### Block types

`facts`: rows of label and value, with an optional mark per row.

```json
{"type": "facts", "title": "City records", "rows": [
  {"label": "PLUTO residential units", "value": "8"},
  {"label": "Condo unit lots", "value": "1E–4E, 1F–4F"},
  {"label": "HPD apartment numbers", "value": "none for 3G, 3H, 3I, 3J", "mark": "bad"}
]}
```

`grid`: the building's unit labels by floor, for seeing at a glance which labels sit outside
the building's lines. Each cell is a label with its ad count and years; `mark` is `candidate`
(on this card), `city` (in city records), `oneoff` (one ad, never used again) or empty.

```json
{"type": "grid", "title": "Labels ever advertised", "floors": [
  {"floor": "3", "cells": [{"label": "3E", "ads": 6, "years": "2016–2024", "mark": "city"},
                           {"label": "3G", "ads": 1, "years": "2018", "mark": "candidate"}]}
]}
```

`ads`: a list of ads, newest last. Each ad gives what it gives; every key is optional except
`listing_id`.

```json
{"type": "ads", "title": "The chain", "ads": [{
  "listing_id": "2501619", "unit": "3F", "opened": "2018-08-23", "closed": "2018-08-29",
  "status": "delisted", "first_ask": 2600, "last_ask": 2600, "bedrooms": 1, "full_baths": 1,
  "half_baths": 0, "square_feet": null, "floor": 3, "lister": "Nooklyn",
  "photos": ["https://photos.zillowstatic.com/fp/<key>-se_large_800_400.webp"],
  "floor_plans": ["https://..."],
  "text": "the ad's description, cut to about 1,200 characters",
  "url": "https://streeteasy.com/rental/2501619",
  "mark": "candidate",
  "record": {"period": "2018-08", "bedrooms": 1, "full_baths": 1, "half_baths": 0,
             "square_feet": null, "latest_ask": 2600}
}]}
```

`record` holds the row's recorded values as the corrections ledger's `when` needs them; give it
for any ad a card might correct, so a "fix a value" answer can be exported.

`text`: a paragraph, `{"type": "text", "title": "...", "body": "..."}`.

`links`: `{"type": "links", "title": "...", "links": [{"label": "...", "url": "..."}]}`.

Images load from the hosts in `review.IMAGE_HOSTS` (StreetEasy's photo host) or from files
under `<site root>/review/media/`, referenced as `/review/media/<path>`. The site's content
policy blocks any other host.

## Answers

Each line of `decisions.jsonl`:

```json
{"queue": "unit-joins", "card": "16-monitor-street-brooklyn:3e", "answer": "yes",
 "option": null, "problems": [], "fix": null, "note": "",
 "at": "2026-11-12T05:10:03Z", "card_sha": "<sha256 of the card's line>"}
```

- `answer` is one of the queue's answer codes, `option` (with the option's code),
  `problem` (Something else is wrong), `skip`, or `undo`.
- `problems` lists codes from the Tags vocabulary's data errors (`wrong_beds`, `wrong_price`,
  `wrong_unit`, `not_apartment`, `restricted`, `duplicate`, `data_other`).
- `fix` is an optional value Ben types for one of the card's ads: `{"listing_id", "field",
  "value"}` with `field` one of `bedrooms`, `full_baths`, `half_baths`, `square_feet`,
  `latest_ask`. The export writes it as a `set` with his reading as the backing, when the ad
  has a `record` to fill `when`; otherwise it lists it for a thread to finish.
- `card_sha` ties the answer to the card as it was shown. If a rebuild changes the card, the
  answer stays in force for the queue's order, the site marks the card as changed since the
  answer, and the export writes no ledger line for it (below).

## Export

```sh
python -m apartments.site.review export --root /data1/apartments/site \
  --ledger pipeline/ledger --day 2026-11-12
```

It writes, for the answers in force not yet exported:

- `pipeline/ledger/<day>-review-app-01.ndjson`: the corrections ledger's sets and excludes;
- `pipeline/ledger/units/<day>-review-app-01.ndjson`: the unit ledger's joins and splits;
- `<site root>/review/findings-<day>-01.jsonl`: every answer that writes no line (no, can't
  tell, a problem with nothing to write), and every problem answer, for the thread that built
  the queue. A "no" on a screen's card is a measured false positive of the screen.

Each file name ends in `-01`, or the next free number, so a second export of a day sorts after
the first, as the ledger reads its files in order of name. An answer given before a rebuild
changed its card writes no ledger line: it goes to the findings with `card_changed`, since the
card's proposal may not be what Ben saw, and the card asks for a new answer. Each written line's `source` is
`review app <queue>/<card> <at>`. Then a thread opens the usual reviewed PR, whose tests read the
new files with the ledger's own rules.
