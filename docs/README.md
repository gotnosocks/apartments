# Map of the docs

Start with the three files at the top. The rest is the record behind them.

## Read first

| File | What it answers |
|---|---|
| [model/drift.md](model/drift.md) | What is the current model, how is it fitted, and how well does it predict? |
| [research-record.md](research-record.md) | What has the project tried, and what came of each try? |
| [handoff/project-owner.md](handoff/project-owner.md) | Where did the last working session stop, and what is next? |

## Standing documents

| File | What it holds |
|---|---|
| [project-intent.md](project-intent.md) | The data contracts: raw captures, corrections, dated analytical tables. The modelling aim in it predates 2026-11-10; the root README states the current one. |
| [leak-free-scoring.md](leak-free-scoring.md) | Why a row's rent may reach a fit only as its target, and the splits that enforce it. |
| [coding-standards.md](coding-standards.md) | Code style and lint rules. |
| [thelio-jobs.md](thelio-jobs.md) | Running jobs on Ben's machine: the two resource classes and `ops/job`. |
| [model/modal.md](model/modal.md) | Running fits on Modal: budget, the per-fit cap, the convergence gate. |
| [site.md](site.md) | The listings site: pages, build and deploy. |
| [research-plan.md](research-plan.md) | The plan and log of the frontier line (2026-09-24 to 2026-10-17). Historical since the B0 line began. |
| [TODO.md](TODO.md) | Open items of the current model and the Deals page. The list before 2026-11-10 is in `archive/TODO-2026-10.md`. |

## The record

| Folder | What is in it |
|---|---|
| `notes/` | One dated note per fit or check since 2026-10-19: the predictions written before a fit, then its results. A folder beside a note holds its scripts and tables. |
| `model/` | Model write-ups up to 2026-10-18: the PyMC line, the frontier line and its leaderboard, feature tests, mixing reviews. |
| `handoff/` | One note per thread, saying where it stopped; `housekeeping.md` records the tidy-up of 2026-11-10. `2026-09-24/` holds the handoff between the first two model lines. |
| `data/` | Data audits and pipeline notes: coverage, corrections, quarantine rules, storage. |
| `analysis/` | The Chelsea pilot's analyses (2026-09). |
| `operations/` | Checkpoints and incident notes from running the machine. |
| `playtests/` | Notes from using the site as a renter would. |
| `archive/` | Superseded documents kept for reference, including the root README of 2026-09. |

## Conventions

- A note's date is the day its work was done. Notes are not rewritten afterwards: a later
  correction is a new note that links the old one.
- A fit's predictions are committed before the fit is launched.
- Numbers in a note come from files on thelio under `/data1/apartments/`; the note names the
  run so the numbers can be traced.
