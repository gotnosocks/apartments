# Review app handoff

The Review section of the site (`/review`) shows Ben cards one at a time on a phone, so he can
flag data that looks wrong while doing something else. He asked for it on 2026-11-12, and
PR #1321 merged it as bd3c18d. `docs/review-app.md` describes the card format and the flow.
This note covers running it on thelio and the work still open.

## State at 2026-11-12 04:20Z

The site at :8600 runs bd3c18d and serves four queues:

| Queue | Cards | Producer |
| --- | --- | --- |
| `outliers` | 300 | `review_cards/outliers.py` |
| `studio-beds` | 1,691 (430 with backing) | `review_cards/studio_beds.py` |
| `held-sets` | 59 (12 more dropped as not kept) | `review_cards/held_sets.py` |
| `unit-joins` | 23 (13 with a proposal) | `review_cards/unit_joins.py` |

No answers have been exported yet.

## Where the queues live

Each producer writes `meta.json` and `cards.jsonl` to
`/data1/apartments/site/review/queues/<queue>/`. The site appends Ben's answers to
`/data1/apartments/site/review/decisions.jsonl`. The site unit runs as ben with UMask 0077,
and ben owns the whole folder.

## Rebuilding a queue

The producers only read data, so they cost nothing and can run beside a fit. Run them from a
checkout of master, in a 3G scope as the memory budget requires. Each takes 10 to 20 seconds and
peaks under 1 GB:

```sh
cd /data1/apartments/serve/master   # or any worktree of master
for q in outliers studio-beds held-sets unit-joins; do
  systemd-run --user --scope -q -p MemoryMax=3G \
    env PYTHONPATH=src JAX_PLATFORMS=cpu \
    /data1/apartments/venvs/bridge-root/bin/python -m apartments.review_cards build "$q"
done
```

`--out` changes the output folder, which defaults to the site's. `--datasets`,
`--diagnostics`, `--ledger`, `--sprint` and `--memory` point a build at other inputs. Each
build reads the newest entry of the pipeline catalog and the ledger of the checkout it runs from.
It skips any ad the ledger already settles, so rebuild after a ledger PR merges. Writes go to a
temporary name, which is then renamed into place, so the site never shows half a queue.

A card's answer only exports while the card is unchanged, because the export compares each
answer's `card_sha` with the card on disk. An answer to a card that has changed since goes
to the findings and needs answering again. Export first, then rebuild.

## Exporting answers

```sh
cd <a worktree of master on a new branch>
PYTHONPATH=src /data1/apartments/venvs/serve-site/bin/python -m apartments.site.review export \
  --root /data1/apartments/site --ledger pipeline/ledger [--day YYYY-MM-DD] [--dry-run]
```

The command prints counts as JSON (`corrections`, `units`, `findings`, `answers`) along with
the files it wrote:

- `pipeline/ledger/<day>-review-app.ndjson`: sets and excludes, each carrying Ben's reading as
  an `owner` item next to the card's own evidence;
- `pipeline/ledger/units/<day>-review-app.ndjson`: joins;
- `/data1/apartments/site/review/findings-<day>.jsonl`: all other answers, plus answers to cards
  that are missing or have changed.

The command records the answers it exported in `review/exported.jsonl`, so running it again
writes nothing new. Commit the ledger files on the branch and open a reviewed PR as with any
other ledger change. Use `--dry-run` to see the counts without writing anything.

## Next work

1. **unit-joins over every linked building.** The queue covers only the five buildings of
   the worked examples (`unit_joins.EXAMPLES`), until the sprint's own label test
   (`/data1/apartments/tmp/outlier-sprint/s2/G/code/std.py`) lands. Once it does, take its
   test in place of the copied `norm` and `JUNK`, then call `build(sources, examples=None)` or
   make that the default. Pass `examples=None` only after reading a sample of the new cards,
   since city record coverage varies by building.
2. **A regular rebuild.** A `systemd --user` timer should rebuild the four queues every night
   after the pipeline build and after each ledger PR merges, exporting first so that no
   answer goes stale. It doesn't exist yet. Write it as an `ops/` script that runs the export
   with `--dry-run` and holds off the rebuild while answers are waiting to be exported.
3. **Reading the findings.** The thread that owns each queue should read the `no` and `unsure`
   answers in `findings-*.jsonl`. They show where a producer's screen or backing rules nominate
   badly.
