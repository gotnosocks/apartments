# Repo-state cleanup: handoff

Updated 2026-10-14 ET. The cleanup thread ran on thelio from Ben's 2026-10-14 09:21Z request to
follow through on the latest-ask change and decide every loose item in the repo. It has parked;
this note lists what it finished and the work it leaves for the next session.

The decisions themselves, with the evidence behind each, are in
[`docs/model/unadopted-work-2026-10-14.md`](../model/unadopted-work-2026-10-14.md).

## Done on 2026-10-14

- **#733:** the board only pairs fits on the same price target.
- **#737:** the board and the site label a pair across price targets as "other target".
- **#739:** Modal fits launch under a per-fit cap of an estimated hour, with a 75-minute backstop.
  **#773** records Ben's confirmation (18:42Z): an hour per fit and no per-fit dollar cap, so
  `PER_FIT_USD` in `ops/modal/cap.py` stays `None`.
- **#740:** a data change under 0.25% of rows (`NEGLIGIBLE_SHARE`) goes in without a refit.
- **#741 (quarantine-v14)** and **#742 (unit-labels-v16)** merged with no refit, both under the
  0.25% bar.
- **#744:** the decision record linked above. It also updated the held-fit statuses in
  `docs/research-plan.md` and gave the ledger an optional `score` field for rows with no paired
  diff.
- **#746:** the paired SE on the board takes the larger of the iid SE and the SE clustered by tax
  lot.
- I closed 7 stale PRs and deleted 78 remote branches already merged into master. The decision
  record lists the closed PRs and the kept branches with unmerged work.
- Data improvements built and merged **#778** (elevator from ad text, `395d53e7`) and **#794**
  (pets from ad text, `6597bb69`). They enter the model through the single NB9 C fit.

## Open work

The research dashboard needs a refresh once a latest-ask C fit is served. Both copies have been
stale since 2026-10-10:

- the CSVs in `/mnt/project-files/dashboard`;
- the artifact at https://claude.ai/artifact/WLw3xxZHyTXruJWiDLknzg.

The next session should check the served model itself, in the leaderboard and the autoselect
output, and refresh both once the served fit targets the latest ask. A message from Modeling may
not arrive.

## Queue (Modeling owns it)

1. The NB9 C fit runs next, with the elevator and pets fills in its data.
2. Fixed-rho AR(1) follows.

The areatime fit stays off the queue until someone has a design that fits within the hour cap.
The elevfill and petsfill feature tests are retired, since #778 and #794 now correct the data
itself.

## Background jobs

None. No `cleanup-*` systemd units are running or loaded, and the cleanup thread left nothing in
the background.

## Leftovers

- Bridge worktree `/home/ben/code/apartments/.claude/worktrees/bridge-cse_017QMnWHmhvXVxnJ4Qi3Ly5h`,
  checked out on the local branch `select/lot-clustered-se` (`14f582ed`, squash-merged as #746).
  The remote branch is deleted. Remove both when that session ends.
- Scratch directory `/data1/apartments/tmp/cleanup` (552K): helper scripts, autoselect outputs,
  test logs and the branch lists behind the deletions.
- Venvs from the cleanup work, each safe to delete:
  - `/data1/apartments/venvs/wt-cleanup` (4.5G)
  - `/data1/apartments/venvs/wt-cleanup-b2` (4.5G)
  - `/data1/apartments/venvs/wt-cleanup-root` (1018M)
- Kept branches with unmerged work, all listed in the decision record:
  - 10 branches of closed PRs from before the cleanup;
  - 8 branches with no PR;
  - the branches of the 6 PRs closed during the cleanup: `data/quarantine-v11`,
    `data/unit-labels-v10`, `data/unit-splits-v5`, `data/plutoasof-v1`, `data/permit-v2`,
    `data/unit-labels-v4`.

The other worktrees under `/data1/apartments/tmp` belong to other threads.
