# Token use by the thread sessions

Measured 2026-10-05 from the Claude Code transcripts on thelio (`~/.claude/projects/**/*.jsonl`),
the 48 hours to 06:46 UTC, summing the `usage` of each assistant API call once. Weight is the
input-equivalent cost share: cache reads ×0.1, cache writes ×2 (hour-long cache), output ×5.

| Session | API calls | Cache read | Cache write | Output | Max context | Weight |
|---|---:|---:|---:|---:|---:|---:|
| Data improvements | 701 | 334.5M | 6.0M | 487k | 966k | 37% |
| Website | 595 | 301.1M | 2.5M | 435k | 966k | 29% |
| Website subagents | 703 | 38.5M | 2.7M | 59k | 144k | 7% |
| Data collection | 231 | 54.1M | 1.2M | 135k | 390k | 7% |
| Modeling subagents | 548 | 32.5M | 2.6M | 25k | 156k | 7% |
| Modeling (session since 10-05 00:40) | 185 | 28.0M | 1.4M | 98k | 969k | 5% |
| Other (Q&A and ops sessions) | 214 | 29.9M | 1.0M | 143k | 231k | 4% |
| Data improvements subagents | 253 | 18.9M | 1.2M | 18k | 197k | 3% |
| Remaining subagents | 92 | 4.2M | 0.4M | 8k | 66k | 1% |
| **Total** | 3,522 | 842M | 19.0M | 1.41M | | |

Cache reads are 98% of the tokens. Uncached input is negligible (7k).

- **Context size is the cost.** Data improvements and Website ran most calls at 300k to 966k tokens of
  context (978 calls, 586M cache read between them). Auto-compaction only fires near the 1M window.
  At a 200k ceiling the same calls would read about a third as much.
- **Cold rebuilds.** A wake more than an hour after the last call rewrites the whole context: 22
  rebuilds over 50k in the four thread sessions wrote 8.6M tokens, about 45% of all cache writes.
  The 120-minute heartbeat is always cold, and so is any wake after a long fit.
- **Shared wakes.** `wait-next` watched `frontier-*` units by default, so every fit end woke the
  threads that own no GPU work too.
- **Subagents are cheap per call.** Their contexts stay under 200k; they cost through call count
  (reviewers and playtesters), not size.

## Changes

- `ops/team/wait-next` batches wakes: a unit finishing or a PR changing waits up to `--batch`
  minutes (default 15) for the other watched units, and an idle GPU, a watched file or the
  heartbeat still ends the wait at once, so no GPU time is lost. A queued fit counts as a
  watched unit, so a fit that ends with the next one queued wakes its owner after the full window.
  `frontier-*` units are watched only with `--gpu`.
- `.claude/settings.json` sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000`, so sessions compact near
  200k (Ben approved 2026-10-05; it applies when a session restarts). CLAUDE.md asks for a handoff
  note at milestones, log reads with `tail`/`grep` only, and never asking Ben to type "go".

## Second pass: 07:10 to 15:25 UTC, 2026-10-05

| Session | Calls | Cache read | Cache write | Median / max context | Weight |
|---|---:|---:|---:|---:|---:|
| Website | 602 | 60.4M | 1.41M | 99k / 334k | 29% |
| Data improvements | 107 | 43.6M | 1.28M | 421k / 479k | 21% |
| Website playtesters (16 spawns) | 584 | 35.3M | 1.06M | 60k / 116k | 17% |
| Modeling | 125 | 40.8M | 0.51M | 329k / 407k | 16% |
| Website reviewers (31 spawns) | 238 | 9.0M | 1.05M | 42k / 58k | 9% |
| Other reviewers (11 spawns) | 91 | 4.1M | 0.63M | 55k / 77k | 5% |
| Data collection | 5 | 1.6M | 0.38M | 407k / 410k | 3% |

Hourly cost peaked at 11:00 to 14:00 UTC (4.8, 7.8 and 9.3 units against about 2 before), driven by
Website's playtest rounds 3 to 5 and its PR reviews.

- The compaction window works without a restart: Claude Code reads `.claude/settings.json` live
  from the session's worktree. Website's worktree has it and compacted six times at about 167k.
  The Data improvements, Modeling and Data collection session worktrees are on branches from
  before #234, so they still run at 330k to 480k and have not compacted once. `wait-next` now
  says so when the session that runs it lacks the variable.
- Subagent fan-out is now a third of the cost. Reviewers cost through cache writes: each spawn
  starts cold. Playtesters cost through call count.
