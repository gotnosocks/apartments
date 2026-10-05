# Working in this repo from a project thread

Ben runs the project as a team of Claude threads (Modeling, Data improvements, Data collection,
Website), each with a Remote Control session on thelio. The goal is continuous improvement with
no idle hours, so these rules are about never going quiet. They apply to the top-level session of
a workstream thread, not to subagents, reviewers or one-off sessions. Conventions for fits, jobs,
PRs and deploys are in project memory and in `docs/thelio-jobs.md`.

## Never end a turn with nothing pending

A thelio session parks about 60 minutes after its last activity unless one of its own background
tasks is still running. A parked session sees no fit landing, no PR merging and no idle GPU, and
it stays parked until a person writes in its thread. On 2026-10-04 that left the GPU idle from
03:51 to 10:48 ET. Sessions that had a background task pending stayed up for 107 minutes and woke
when it finished.

So end every turn by starting `ops/team/wait-next` with the Bash tool's `run_in_background: true`,
from the copy that follows master:

```sh
/data1/apartments/serve/master/ops/team/wait-next --gpu --pr N
```

It returns when the GPU goes idle (`--gpu`: after a job ends, or after 30 minutes if it was
already idle), a file appears or changes (`--file PATH`), or after `--max` minutes (default 120)
as a heartbeat. A `frontier-*` unit finishing (watched with `--gpu`; `--unit PATTERN` for others)
or a watched PR changing (`--pr N`) is batched: the wait goes on up to `--batch` minutes (default
15) to collect the other watched units, and an idle GPU still ends it at once. Its exit wakes the
session with what changed. Act on it, then start it again. A
background `ops/job` run or fit you are waiting on works too, as long as something stays pending.
If a message wakes you while a `wait-next` is still pending, leave it running rather than
starting a second one. Leave out `--gpu` only when you don't own GPU work.

- Session crons (CronCreate) die when a session parks, and a 2-hourly cron never fires before
  the 60-minute park. Use `wait-next --max` for periodic checks, and systemd `--user` timers
  for anything that must run with no session at all, like `apartments-gv-monitor.timer`.
- After any wake, including a resume after a park or a usage-limit stop, check state yourself
  (`ops/job status`, `gh pr list`, your logs) and start `wait-next` again before ending the turn.

## Keep the context small

Every tool call re-reads the whole context, and a wake after the hour-long prompt cache expires
writes all of it again. Over 2026-10-03..05 the two sessions that ran at 300k to 966k tokens made
two thirds of the project's token cost (`docs/token-usage.md`). `.claude/settings.json` sets
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` so sessions compact near 200k instead of 1M. Help it along:

- At each milestone (a PR merged, a fit landed and recorded, a decision from Ben), update your
  thread's handoff note, `docs/handoff/<thread>.md`, with what the next turn needs, so a
  compaction or a fresh session loses nothing.
- Read logs and large files with `tail`, `grep` or `sed -n` ranges, never whole. Ask subagents
  for a short conclusion, not file dumps.
- Wake only for what you act on: watch the PRs you are waiting on, and leave out `--gpu` and
  `--unit` when you own no GPU work.
- Never ask Ben to type "go" or to confirm a step his standing rules already allow. Do it and
  report. A decision that really is his goes to him once, and you carry on with your
  recommended default.

## Keep the GPU queued

Whoever owns GPU work (Modeling, and Data improvements for its exploration fits) keeps the next
fit queued behind the running one: launch it now as a `systemd-run --user` unit that calls
`ops/job gpu`, and it starts when the GPU lock frees. Before ending a turn, have at least the
next few hours of fits running or queued, with the night's full fits queued by evening.

## Don't wait on another thread

If your work depends on another thread's PR or result, watch it with `wait-next --pr N` and check
it yourself. If it hasn't moved by the next wake, message that thread's session (ListAgents,
SendMessage) and say exactly what you need. Meanwhile take the next item from your own backlog
(`docs/research-plan.md`, `docs/TODO.md`) rather than idling. A decision only Ben can make goes to
your thread once; keep working on the default you recommended while you wait.
