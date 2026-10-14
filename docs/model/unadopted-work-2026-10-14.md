# Unadopted work: decisions of 2026-10-14

On 2026-10-14 Ben asked for a decision on every held fit, open rule and stale branch, with three
guides:

- a negligible data change gets no refit;
- a correction toward a known ground truth goes ahead of model updates;
- a stale modeling result gets a decision about retesting.

This file records each decision and the evidence behind it. Scores follow the evaluation framework
of the 2026-10-08 research review (§3 of [research-review-fable-2026-10-08.md](research-review-fable-2026-10-08.md), as Modeling adopted it):
paired PSIS-LOO on shared rows with a bar of about 2 combined SE. From 2026-10-14 the paired SE
is the larger of the iid and the lot-clustered SE (branch `select/lot-clustered-se`).

## Per-fit cap

Ben, 2026-10-14 09:57Z: "I'm pretty hard capped at about 1 hour or maybe $2 of modal compute."

- #739 enforces the time half: a fit's container stops at an estimated hour, with a 75-minute
  backstop.
- The dollar half waits on Ben's answer to Modeling.
- Every retest below runs at C's settings, so each one costs about as much as a C fit.

## Queue

Modeling runs these in order, one at a time:

1. The C refit on latest-ask-v2 and quarantine-v13.
2. lines.
3. arwalk-fixedrho.

Everything else listed here stays off the queue.

## Decisions

| Item | Decision | Evidence |
|---|---|---|
| latest ask | Adopted | latest-ask-v2 (#730); Modeling refits C under it; #733 keeps a first-ask incumbent from pairing with a latest-ask fit; #737 shows "other target" for such pairs |
| final ask | Retired | Ben chose the latest ask on 2026-10-13 at 13:51Z. The final ask drops 37% of rows, and its new-building miss matched C's. `tune-finalask-v1` stays in the code. |
| lines | Retest first after the C refit | Against C: building-weighted new-building lpd +83.9 with lot SE 14.4; PSIS-LOO +53.0 with lot SE 22.1, a tie under the lot SE |
| areatime | Off the queue | Its fit stage alone ran 3,340 s at C's settings, so a container would run about 70 minutes, past the hour. It comes back only with a design that fits in an hour. Its evidence stands: PSIS-LOO +405.5 with lot SE 146; building-weighted new-building lpd +24 ± 9. |
| arwalk | Capped design queued | Under the per-fit cap the 24,000-draw plan was withdrawn. At 09:59Z the coordinator approved Next modeling action's capped design: rho fixed at 0.89 from the first fit's posterior, run at C's settings, about 40 to 50 minutes and about $2, with a predicted gate pass of 80 to 85%. It runs after lines and before any areatime return, on latest-ask-v2 and quarantine-v13, scored against the C refit. Next modeling action holds its config and predictions. |
| elevfill, petsfill | Held for Ben | Both correct coded fields toward ground truth, and neither change is negligible, so each needs a fit Ben has not released under the cap. |
| bigbed | Retired | A tie (+46.8, lot SE 30.7) that adds interaction terms; elegance keeps C. |
| lister, retail, noise, trees, crime, hpd | Retired | Screen shares were 1.2 to 2.4% or inside the permutation null, and none was predicted above about 2 SE in #672's pre-registration. hpd's prediction was +20 against a bar of about 30 to 35. |
| amenlevel | Retired | It reads rent and gained +13.5 ± 10.7 on the latest split, under the bar. |
| nofloorslope | Retired | −318.8 |
| lognoise | Retired | −2,002 |
| yearnoise and lognoise multipliers | Not queued | They answer the coverage question in §6 of the 2026-10-13 plan, which waits on the C refit's coverage. |
| predsize | Retired as designed | Never queued. A redesign would start from the new-building score. |
| renov | Closed null | +2.0 ± 14.8 (#422) |
| stab | Closed null | −1.1 ± 2.5 (#435) |
| archive CLI | Closed 2026-10-13 | #715 |
| clustered SEs | Adopted | The board's paired SE is the larger of the iid and lot SE (B3). The lot/iid ratios against C below show how much the iid SE understated the error. |
| negligible data changes | Adopted | #740: a run stays servable when its rules change fewer than 0.25% of its rows. |
| plutoasof-v3 | In the base | Every NB8 set, nb8-nostuy-v1 and so C among them, reads `nb5-plutoasof-v3`. The ledger row now says so. |

Lot/iid SE ratios against C:

| Fit | lot / iid |
|---|---|
| lines | 1.44 |
| elevfill | 1.53 |
| bigbed | 1.70 |
| areatime | 4.02 |
| nofloorslope | 1.59 |
| arwalk | 1.48 |
| lognoise | 1.66 |
| amenlevel | 2.36 |

## Rules merged without a refit

Both rules correct data toward a known ground truth and change well under the 0.25% negligible
share, so I merged them and left the C refit on quarantine-v13 and unit-labels-v15 servable.

- **quarantine-v14** (#741): v13 plus the 13 shop, event-space and short-lease rows that #542's
  rent-blind text screen found. #542 is closed.
- **unit-labels-v16** (#742): v15 plus #420's spelled-out label joins, guarded by agreeing median
  bedrooms as every label rule since v3 is. 176 rows change unit (0.082% of 214,872). The
  latest-ask price screen under v16 gives the same 11 hits over 2.5 and the same 2 over 3. #420 is
  closed.

Combined, the two change 189 rows against about 537 allowed. The next fit that needs a refit for
another reason picks both up.

## Closed PRs

#542 and #420 went into v14 and v16. #425, #439, #437, #478 and #222 were closed with a comment
giving the reason.

## Branches

Of 177 remote branches I deleted 78. Each had a merged PR whose `archive/pr-N` tag holds the
branch tip, so no commit was lost.

I kept these, since their commits live nowhere else:

- Closed-PR branches with unmerged work:
  - data/floors-ad (#162)
  - data/nb8-pets-v1 (#663)
  - data/permit-v1 (#437)
  - data/renovated-since-v1 (#422)
  - data/unit-label-swaps (#335)
  - data/unit-labels-v6 (#326)
  - data/unit-splits-v2 (#400)
  - features/nb-openspace (#140)
  - features/nb-transit (#139)
  - model/design-labels (#192)
- Branches with no PR:
  - app/summary-reader
  - batch/dayfourier-v2
  - batch/dayfourier-v4
  - batch/q5-f2
  - batch/relist-explore
  - bedroom-time-20260922
  - explore/prevprice-latest
  - frontier/sub10-fits
- Branches closed in this cleanup, kept for their unmerged commits: data/quarantine-v11 (#542),
  data/unit-labels-v10 (#420), data/unit-splits-v5 (#425), data/plutoasof-v1 (#439),
  data/permit-v2 (#478), data/unit-labels-v4 (#222).

I also skipped 49 branches checked out in a worktree, 30 with commits in the last two days and the
branches of 2 open PRs. About 100 remote branches remain.
