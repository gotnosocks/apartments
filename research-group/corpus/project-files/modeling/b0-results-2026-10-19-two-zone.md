# Two-zone location fit: results (did not converge)

*Fit 2026-10-19. This is the converged design from #1156 plus a location surface for each of two zones. That design has no intercept (week 0's level takes the intercept's prior), a pinned-total season, independent bath steps and Normal walk shocks. The two zones are Manhattan (BBL borough 1) and Brooklyn + Queens. Each zone has its own rotated HSGP box, a 500 m squared-exponential kernel, its own amplitude with a HalfNormal(0.3) prior, and centred coefficients. There is no borough term. The combined surface is centred on its ad-weighted mean, so the walk carries the overall level. The model is in PR #1159 (merged), and the data use registry snapshot 20261019-bcfbb52-extend. Nothing on the served model or the site changed.*

## Data check before the fit

All 67,977 buildings and 1,896,486 ads have coordinates and a BBL, and all fall inside an NYC bounding box.

| Zone | Buildings | Ads |
|---|---|---|
| Manhattan | 21,994 | 1,115,906 |
| Brooklyn + Queens | 45,983 (24 in Queens) | 780,580 |

## Boxes

| Zone | Rotation | Padded box | Basis functions |
|---|---|---|---|
| Manhattan | 25.5° | 5.2 × 18.9 km | 10 × 34 = 340 |
| Brooklyn + Queens | 39° | 11.3 × 12.5 km | 20 × 22 = 440 |

## Run

- Run `two-zone-b0-latest-a5825bfe-dense-w1500`, fit-only, on an A100-40GB.
- 16 chains, 1,500 warmup steps and 500 draws.
- 26 min (warmup 14.5, sampling 10.7) and $1.06, against an estimate of $1.21.
- No divergences.

## Convergence: fails

- **Worst:** R-hat 3.79 and ESS 9, on the 5+ bed step.
- **Also failed:** g (R-hat 2.21), τ (1.91), the season terms and the bedroom steps.
- **Passed:** the zone levels and the gap between zones (R-hat 1.03, ESS 530).

Unlike the earlier fits, the chains agree on where the posterior is. For example, all 16 put the 5+ bed step between 0.106 and 0.117 and τ near 0.006. The trouble is that each chain barely moves. The adapted step size was 0.0016, against 0.25 in #1156's converged fit, with at most 64 leapfrog steps per draw.

## Why

- **Data:** no problem found.
  - The 901 buildings the registry extension added fit no worse than the rest.
  - The most extreme buildings are believable: Brownsville and East New York at about −0.77, West Chelsea and Hudson Yards at the top.
- **Brooklyn + Queens surface:** behaves. Its amplitude is 0.57, and its largest coefficient is 3.0 prior sds.
- **Manhattan surface:** the failure.
  - Its biggest coefficients sit at the high-frequency corner of the basis, waves (8..10, 29..34). They reach 24.7 sds of their unit-amplitude prior, and the amplitude climbed to 3.65 to allow it.
  - Manhattan rents change over much less than 500 m: waterfront and park-edge blocks, and single towers next to walk-ups. The 500 m kernel can only follow that by forcing its finest waves up.
  - Those waves are strongly correlated (|corr| up to 0.97). The diagonal mass matrix can't absorb that, which forces the tiny step size.
- **Zone level:** fine. The lowest waves are unremarkable, and the zone gap converged. An earlier guess that the zone level was the cause was wrong.

## Rough values (unconverged, no trustworthy intervals)

- **Zone gap:** Manhattan sits +32.6% above Brooklyn + Queens (zone levels +0.117 and −0.165). This quantity converged.
- **τ:** about 0.006.
- **Residual ν:** about 6.5, down from 21 under the normal walk without location.
- **Residual σ:** 0.165 to 0.186, down from 0.24 to 0.34 without location. This one mixed.
- **Bath premium:** an extra bath is worth about half what it was without location (+41% against +71% for a 2-bed), so part of the old bath premium was location.
- **Studio → 1 bed:** +27.8%, inside the predicted range, though the chains under it never mixed.

## Map

`/data1/apartments/frontier/runs/two-zone-b0-latest-a5825bfe-dense-w1500/surface_map.png` on thelio shows the posterior mean and sd per building.
- **Manhattan:** highest in West Chelsea, Hudson Yards and along the Hudson.
- **Brooklyn:** lowest in central and eastern Brooklyn.

The sd panel means nothing, because the chains stalled.

## Predictions

| Prediction | Result |
|---|---|
| Manhattan over Brooklyn + Queens: +18% to +35% | **Hit**, +32.6% |
| Max R-hat ≤ 1.02 | Miss, 3.79 |
| Amplitude medians between 0.3 and 1.2 | Miss for Manhattan (3.65), hit for Brooklyn + Queens (0.57) |
| 1-bed step over a studio: +18% to +30% | Not assessed, unconverged |

## Proposed fixes (waiting on Ben)

1. **A building random effect,** b_s ~ Normal(0, s_building), with s_building sampled. It soaks up building-to-building jumps, so the surface can stay smooth. It adds about 68k parameters, cost about the same (under $1.50).
2. **A shorter length-scale for Manhattan,** about 150 m, either learned or as a second component. That needs about 10 times the basis functions and probably breaks the 1-hour cap unless Manhattan is split.
