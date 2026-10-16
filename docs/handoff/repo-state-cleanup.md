# Repo-state cleanup: handoff

Updated 2026-10-16 ET. The cleanup thread ran on thelio from Ben's 2026-10-14 09:21Z request to
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

## Done on 2026-10-16

The NB9 latest-ask fit went live at 07:16 ET (#899), so I refreshed the research dashboard
artifact at https://claude.ai/artifact/WLw3xxZHyTXruJWiDLknzg. It is a Dashboard-type artifact,
filled through its database: for each dataset I uploaded a new CSV as an asset, then pointed the
`datasets/<id>` document's `source.url` at it.

- `served_now` comes from the live site build's held-out asks: 29,669 asks, median miss 3.69%,
  79.1% inside the 80% range, 94.8% inside the 95% range.
- `switches` comes from the selection milestones in `/data1/apartments/dashboard/site/data.json`,
  joined to their fit records. `design_history` in `story.py` misreads the NB9 feature set
  (`unitnu4-nb9-nostuy-lots2-v1`), so I wrote that row's set, neighbourhood count and change
  words by hand.
- `fits` counts the 409 fit records from Sep 23 to Oct 16.
- `tests` is unchanged. The ledger's paired rows still end on 2026-10-08, and its later rows
  carry no paired diff.

The CSV copies in `/mnt/project-files/dashboard` are still from 2026-10-10. Thelio has no
`/mnt/project-files`, so a session with that folder has to copy them over.

## Queue (Modeling owns it)

The NB9 C fit is served (#899). The rest of the queue is in [`modeling.md`](modeling.md).

The areatime fit stays off the queue until someone has a design that fits within the hour cap.
The elevfill and petsfill feature tests are retired, since #778 and #794 now correct the data
itself.

## Background jobs

None. No `cleanup-*` systemd units are running or loaded, and the cleanup thread left nothing in
the background.

## Leftovers

- Scratch directory `/data1/apartments/tmp/cleanup` (552K): helper scripts, autoselect outputs,
  test logs and the branch lists behind the deletions.
- Kept branches with unmerged work, all listed in the decision record:
  - 10 branches of closed PRs from before the cleanup;
  - 8 branches with no PR;
  - the branches of the 6 PRs closed during the cleanup: `data/quarantine-v11`,
    `data/unit-labels-v10`, `data/unit-splits-v5`, `data/plutoasof-v1`, `data/permit-v2`,
    `data/unit-labels-v4`.

The other worktrees under `/data1/apartments/tmp` belong to other threads.
