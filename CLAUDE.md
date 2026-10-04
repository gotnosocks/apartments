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

It returns when a `frontier-*` unit finishes (`--unit PATTERN` to watch others), the GPU goes
idle (`--gpu`: after a job ends, or after 30 minutes if it was already idle), a watched PR changes
(`--pr N`), a file appears or changes (`--file PATH`), or after `--max` minutes (default 120) as a
heartbeat. Its exit wakes the session with what changed. Act on it, then start it again. A
background `ops/job` run or fit you are waiting on works too, as long as something stays pending.
If a message wakes you while a `wait-next` is still pending, leave it running rather than
starting a second one. Leave out `--gpu` only when you don't own GPU work.

- Session crons (CronCreate) die when a session parks, and a 2-hourly cron never fires before
  the 60-minute park. Use `wait-next --max` for periodic checks, and systemd `--user` timers
  for anything that must run with no session at all, like `apartments-gv-monitor.timer`.
- After any wake, including a resume after a park or a usage-limit stop, check state yourself
  (`ops/job status`, `gh pr list`, your logs) and start `wait-next` again before ending the turn.

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
