# Next modeling action: the AR(1) building deviation (2026-10-14)

This note hands the AR(1) workstream to the next Modeling session. I wrote it at 22:40Z on
2026-10-14, when the work was waiting on a converged refit of C.

## State

The AR(1) model replaces C's half-year building walk with a stationary AR(1) deviation around the
building level. The results are in `docs/model/arwalk-2026-10-14.md` and the predictions, written
before each fit, are in `docs/model/predictions-arwalk-2026-10-14.md`.

- First fit (commit 24a7e9b, on C's old data):
  - rho came out at 0.89, the deviation sd at 0.077, building_scale at 0.157;
  - paired PSIS-LOO against C was +395 nats (SE 55 by building), and the new-building 80% year
    gap fell from +5.2 to +1.5 pp;
  - it failed the gate, with R-hat 1.041 on rho and ESS 39 on the sd, so every number from it
    is provisional.
- The worst unit effect in that fit came from a bad $1,000 row at 15 E 17th St #4. Ben asked
  for data fixes before any refit, and Data improvements made them, starting with #730
  (latest-ask-v2, quarantine-v13). Data improvements decides the quarantine and correction rules.
- #748 added `walk_ar_rho`, which fixes rho at 0.89 and skips its Metropolis step. The registry
  entry ends in `-arwalk-fixedrho`. The model, rho fixed or not, is unchanged otherwise.
- Predictions for the fixed-rho fit are recorded for three data versions:
  - #748, on C's bcaac064 data;
  - #749, on the West Coast split (split-v1);
  - #771, on the wing-rule set (nb8-nostuy-wings-v1).

  All three predict PSIS-LOO +350 (+185 to +515), a year gap of +1.5 (0.75 to 2.25), lpd +65
  (+30 to +100) and an 80 to 85% chance of passing the gate.

## Open work

1. Ben approved the fixed-rho AR(1) fit at 18:39Z, within his cap of about 1 h or $2 of Modal
   per fit. Modeling runs it from modalq-c on the same data as a C refit, and only once that C
   passes the gate.
2. The wing-rule C on quarantine-v15 failed narrowly on one building, 110 W 26th St (R-hat
   1.0148, ESS 183; group R-hat 1.031 passed). That building is not a West Coast building. Its
   building effect traded off against its own walk. Ben ruled out rerunning a failed fit on a new
   seed, so Modeling stopped the seed rerun and looked at the building's data.
3. At 22:40Z the next C, on quarantine-v17, was still running (see Background jobs). When it
   finishes:
   - If it passes the gate, launch the fixed-rho AR(1) on its exact rule list.
   - The #771 predictions list `latest-ask-v3`, `quarantine-v14` and `unit-labels-v16`. The
     v15 and v17 C fits ran on later versions (`latest-ask-v4`, `unit-labels-v17`). Before the
     launch, add a predictions line and a short section for the v17 rule list to the
     predictions doc and `config/predictions.jsonl`, and land them through review.
   - If it fails, the AR(1) keeps waiting.
4. Score the AR(1) against that C:
   - paired PSIS-LOO on shared rows, with SEs clustered by building and by lot;
   - new-building lpd, median miss and 80/95 coverage;
   - the 80% year gap;
   - the descriptive share.

   Score each prediction as a hit or a miss, and write the result doc through a reviewed PR.
5. If the AR(1) wins, take the result back to Ben before serving it.

## Dropped

- The collapsed (sd, rho) sampler draft. The Gibbs sampler already integrates the walk out in
  `block_solve`, so the draft added nothing.
- The 4-hour, 24k-draw plan, which Ben's per-fit cap rules out.

## Backlog only

- The latent per-apartment ask model, listed in `docs/research-plan.md`. The design sketch is in
  the project Library at `modeling/latent-ask-design-2026-10-14.md`.

## Holds

- Ben's 03:16Z hold on autoselect, serving and publishing stands. Run none of them.

## Background jobs

- `modal-fit-20261014-181956-1541796`: the wing-rule C on quarantine-v17 (commit e973a8d, label
  `a100-4500k9cb1-nb8-ul17r1s4q17ad3la4-wings1`), started 18:19 ET from Modeling's queue. Leave
  it running.
- The diagnostic unit `arwalk-fixedrho-diag` is stopped. Launch notes are in
  `/data1/apartments/tmp/arwalk/fixedrho/notes.txt`.
