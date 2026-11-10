# Housekeeping handoff

The 24-hour housekeeping pass that Ben started on 2026-11-10 at 15:22Z. It tidied what exists
and ran no fits or Modal jobs. On thelio every action and its undo command is logged in
`/data1/apartments/tmp/housekeeping-2026-11-10/actions.log`, next to `inventory.md`,
`journals/`, `patches/` and `safe-to-remove.tsv`.

## GitHub

- **Tags.** `archive/pr-1281` to `archive/pr-1289` are pushed and annotated, on each PR's
  head. Every branch that was on origin besides master and the two overhaul and housekeeping
  branches is tagged `archive/branch/<name>`, 50 tags in all. Thirteen worktree heads that
  were in no branch, master or tag are tagged `archive/wt/<branch>`.
- **Branches.** On 2026-11-10 Ben approved deleting 46 old branches, and they are gone from
  origin. To restore one, run `git push origin archive/branch/<name>^{commit}:refs/heads/<name>`.
  Seven branches remain: master, `claude/project-thread-09vaqy` (overhaul),
  `claude/project-thread-eje9tu` (this pass) and four older thread branches (024h3p, 9mwm7k,
  fz2el7, myum4e), which stayed in case those threads are still running.
- **PRs.** #1141, #1153 and #1168, all from October, were closed with Ben's go-ahead, and their
  branches are tagged. #1288 trimmed `docs/TODO.md` to the current model's items (the old list
  is `docs/archive/TODO-2026-10.md`), added the Deals page to `docs/site.md` and removed a stray
  image. #1289 applied ruff's safe lint fixes outside the library code.
- **Lint.** `ops/lint` over the whole repo leaves six findings in library modules under
  `src/` and `frontier/src`. Run records hash those modules, so they were left alone. It also
  leaves two findings that need judgment (F841 in `models/minimal_model_report.py`, B904 in
  `models/modal_remote_fit.py`) and the scripts beside dated notes under `docs/`.

## Thelio

- **Disk.** `/data1` was 99% full, with 12G free. The pass moved 507 directories to
  `/data2/apartments-offload/<same relative path>` and left a symlink at each old path. Those
  were the 47 pipeline lanes under `tmp/pipeline/lanes/`, `tmp/publish-path` and 459 September
  and October runs under `frontier/runs/`. Each copy's file count and byte total were checked
  before the source was removed, so every old path still resolves. `/data1` ended with about
  370G free. `/data2` is at 84%, and the run moves stopped when it reached its 150G floor.
  No served run moved (drift f6, k6, m6; drift-building b9, j9, n9 and companions), and no
  November run moved. The largest things still on `/data1` are `archive/crawls` (58G),
  `frontier/runs` (87G), `model-fits` (71G, September Chelsea fits) and
  `migration/packs` (27G).
- **Worktrees.** 33 worktrees whose work is in master or a tag were removed, freeing 9.6G.
  Their local branches are kept. The two worktrees with uncommitted changes
  (`tmp/pipeline/wt-ledgernames2`, `worktrees/agent-a2549d2c889eadc92`) have their diffs saved
  in `patches/`.
- **Units.** `systemd-oomd` killed the six overhaul scopes that failed on the night of
  2026-11-09 (land.sh, chain2.sh, params_all). Nothing the served model needs was lost. The
  market runs `drift-*-1becc8c9-f4b`, `-f4l`, `-f5b`, `-f5l` and the `00aa62eb` runs f2, b1,
  l1, f4 and f5 never got a report, and they are not served. 81 old failed units were reset
  after their journal tails were saved. `apartments-streeteasy-topup.service` (2026-10-17),
  `design2.service` and `pipeline-lane-wings.service` still show failed.
- **Timers.** Every project timer has been off since Ben paused them on 2026-10-18
  (`/mnt/project-files/ops/paused-timers-2026-10-18.md`), and the pass left them off. With
  them off there is no weekly StreetEasy top-up and no daily backup of the StreetEasy archive
  to `/data2`. The only new ads since then came from the one-off scrape of 2026-11-10.
- **Site.** The Deals page is current (published from drift-building n9). The Estimates
  section was last built on 2026-10-19 from the m7 line and has not been rebuilt from the
  drift model.

## Shared project files

142 superseded files (October handoffs, digests, task briefs, results notes, most of them
also in `docs/notes/` or `docs/model/`, and the conference drafts) were moved to
`/mnt/project-files/archive/2026-10/` at their old relative paths. Nothing was deleted.
`archive/README.md` lists every move. Still at the top level are `goal-proposal/`, the two
research reviews that the project instructions cite, `dashboard/`, `ops/paused-timers-…`
and `uploads/`.

## Left for Ben

- Whether to turn the StreetEasy top-up and backup timers back on.
- The older duplicate of the "How the Rent Model Finds Deals" explainer
  (https://claude.ai/artifact/GK1qc5pTPKDHVsWtFV8Neh). The current one is
  https://claude.ai/artifact/CidAo43kMNH2Kw7GHwTHf7. Only Ben can delete an artifact.
- Whether the four old `claude/project-thread-*` branches can go.
