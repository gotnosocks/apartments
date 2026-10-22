# Where the Claude usage goes (2026-10-05)

## Update: exact thelio numbers (48h to 06:46Z, from local transcripts)

| Session | Calls | Cache read | Max context | Cost share |
|---|---:|---:|---:|---:|
| Data improvements | 701 | 335M | 966k | 37% |
| Website | 595 | 301M | 966k | 29% |
| Website subagents | 703 | 39M | 144k | 7% |
| Data collection | 231 | 54M | 390k | 7% |
| Modeling subagents | 548 | 33M | 156k | 7% |
| Modeling | 185 | 28M | 969k | 5% |
| Other + remaining subagents | 559 | 53M | | 9% |

This corrects the inference below: Data improvements and Website, not Modeling, are the top consumers. Auto-compaction only fires near 1M, so 978 calls ran with more than 300k of context, which is 586M of the 842M cache reads. 22 cache rebuilds after idle wrote about 45% of all cache writes.

Done: PR #233 (merged) makes wait-next batch wakes for up to 15 min and watch fit units only with --gpu. Pending Ben's OK: CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000 in .claude/settings.json, plus a CLAUDE.md "keep the context small" section.

---


Costs below are the list-price dollar figures Claude Code records per session. They are a proxy for plan usage, not a bill (the plan isn't billed per token), but they rank the consumers correctly.

## Two Claude sessions per workstream

Each workstream thread runs **two** Opus sessions:
1. **A cloud thread session.** It talks to Ben, relays messages and briefs the machine session.
2. **A Remote Control session on thelio.** It does the actual work (fits, PRs, crawls, site).

Both draw on the same plan limit.

## What I could measure

### Cloud thread sessions (exact)

| Session | Lifetime | Recent rate | Context per API call |
|---|---|---|---|
| Modeling | $80 | ~$16/day | 250–375k tokens |
| Data improvements | $39 | ~$13/day | |
| Data collection | $25 | ~$13/day (est.) | 250–375k tokens |
| Website | $25 | ~$5–15/day (only 8h read) | |
| Coordinator | $3 | since 00:51Z | |

- **All four threads together:** about $50–60/day.
- **Turns without text:** 85–100% of their turns end without writing anything for Ben. They are wakes: relays, status refreshes, background-task notices.

### thelio sessions (not visible from here)

The current thelio sessions don't show up in the session API, so I can't read their counters. Their predecessors, the same roles before the Oct 3 move, give the scale:

| Old thelio session | Cost | Period | Per day | Notes |
|---|---|---|---|---|
| Modeling | $914 | Sep 24–Oct 3 | ~$110/day | 2.5B cache-read tokens, 6.6M output |
| Data Collection | $329 | Sep 23–Oct 3 | ~$33/day | 34M cache *writes*, context reached 750k |
| Website | $176 | Sep 26–Oct 3 | ~$28/day | |
| Model Improvement | $143 | 2 days | ~$75/day | |

Inference: the thelio Modeling session is still the single biggest consumer. Next are the other thelio sessions, then the cloud thread layer at roughly $50–60/day.

## Why it's expensive (mechanisms, with evidence)

1. **Huge contexts re-read on every step.**
   - Sessions run with the 1M-token window, so contexts grow to 300–750k before any compaction.
   - Every tool call re-reads the whole context. One cloud turn re-read 0.6–1.6M tokens.
   - Under 150k, the same work costs a fraction of that.
2. **Cache expiry after about 1h idle.**
   - The first turn after an hour idle rewrites the whole context to cache: $0.8–2.7 per wake, against $0.05–0.25 for a warm turn.
   - About 12 such rebuilds came to ~$20 of the ~$55 measured.
   - The hourly wake check and wait-next wakes land right at that one-hour mark, so nearly every wake pays the rebuild.
3. **Synchronized wakes.** Modeling, Data improvements and Data collection were all woken together (10-04 14:48, 18:25, 19:40, 10-05 00:40). Each paid its own rebuild.
4. **"Type go" turns.** Several of the most expensive turns ($1.4–2.3) only asked Ben to type "go" after a thelio session parked.
5. **Relaying costs twice.** A cross-thread note passes through up to four Opus sessions: thelio → cloud thread → coordinator → other cloud thread → other thelio. Each one re-reads a 100–400k context.

No subagent fan-outs were seen in the last ~24h. The playtester runs were earlier.

## Tweaks

### No throughput cost (can apply via a thelio PR)

- **A. Keep contexts small.**
  - Add a CLAUDE.md rule for thelio sessions: at a milestone, or when context passes ~150k, write state to a handoff note and compact.
  - Keep long logs in files and read them with `tail`/`grep`, never whole.
  - Biggest single lever.
- **B. Have wait-next deliver batches.**
  - Wake once when several jobs finish, or on a real milestone, not on every job end.
  - Queue fewer, longer fits so the GPU stays busy with fewer wakes.
- **C. Stop "type go" asks.** Thread sessions shouldn't ask Ben for "go"; the coordinator already corrects these.
- **D. Stagger and condition the coordinator's hourly check.**
  - Only wake a thread that is parked *and* has queued work.
  - Never wake all of them in the same minute.

### Trade some quality or speed for tokens (Ben's call)

- **E. Run the cloud thread sessions on Sonnet.** They mostly relay and summarize. That cuts that layer's cost by roughly half or more, but replies to Ben may be a bit less sharp.
- **F. Lower Modeling's exploration cadence overnight.** Fewer exploratory fits means fewer wakes, but slower research.
- **G. Let thelio sessions message each other directly** for routine cross-thread notes, instead of going through the cloud thread and the coordinator. Ben's earlier relay setup would change.
