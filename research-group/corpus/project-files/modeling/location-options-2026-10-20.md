# Location term: options reassessed (2026-10-20)

## What the four location fits have shown

| Fit | Surface | Step size | Worst R-hat | Amplitude (M / B+Q) | Surface sd (M / B+Q) | σ |
|---|---|---|---|---|---|---|
| Location model (borough HSGPs) | 500 m SE, non-centred | 0.0008 | 11.6 | 11.8 / 3.8 | 0.18 / 0.19 | 0.17–0.19 |
| Two zones | 500 m SE, centred | 0.0016 | 3.8 | 3.65 / 0.57 | — | 0.165–0.186 |
| Two zones | 1 km SE, centred | 0.0026 | 2.3 | 1.15 / 2.12 | 0.185 / 0.172 | 0.178–0.194 |
| Three zones + NJ | 1 km SE, whitened | 0.0070 | 1.14 | 6.26 / 3.84 | 0.188 / 0.172 | 0.177–0.193 |
| No location (#1156) | — | 0.19 | 1.009 | — | — | 0.24–0.34 |

Four things follow from this.

1. **The zone gap is settled.** Manhattan sits about +32% above Brooklyn + Queens in every fit, and NJ about +1%. Any option below will reproduce it.
2. **Sampling was a coordinates problem, and whitening mostly fixed it.** The waves are nearly interchangeable on the data, so the sampler crawls. Whitening unstuck the surface coefficients. What's left is the amplitudes, the season, the drift and two thin bath cells.
3. **The amplitudes don't match the surfaces (inferred).** An SE surface with amplitude a has a prior sd of roughly a at each point. The fits found surface sds near 0.18 but amplitudes of 1–12. The data put relatively more weight on the shortest waves the basis allows than an SE kernel expects, so the fit inflates the amplitude to make those plausible. This looks like a mismatch in the kernel's shape, not a sampler problem. It shows up at both 500 m and 1 km.
4. **Going from 1 km to 500 m bought almost no fit.** σ is about the same (0.18 against 0.17), so the variation left in the residual sits mostly at the building level, below what any affordable surface resolves.

## Options

| Option | What it changes | Sampling | Fit quality | Cost and risk |
|---|---|---|---|---|
| ~~A. Rescaled whitening~~ | Rebuild T at the fitted σ and amplitudes | **Ruled out:** the linear bound is unchanged (0.559 against 0.558) | — | Keep whitening; its reference values don't matter |
| **B. Fix the amplitudes** at plug-in values | Treat amplitudes as constants | Removes the unconverged amplitudes, and T becomes exact | Same surface. Loses amplitude uncertainty, which matters little because the data outweigh the prior 400–200,000× | ~$1. Easy to defend for a baseline |
| **C. Matérn 3/2 kernel** instead of SE, at 1 km | Kernel shape: heavier high-frequency tail | Same basis and whitening | Fits rough neighbourhood edges at a modest amplitude, so the amplitude prior means something again | ~$1. Small code change |
| **D. Building effect** b_s ~ N(0, s_b), plus a 1 km surface | Adds about 73k building offsets | Mostly diagonal geometry, which suits NUTS; m7 converged with this | Takes building-to-building jumps, and makes the surface's intervals honest because ads in a building stop counting as independent | ~$1–1.5. Biggest modelling gain |
| **E. Larger scale** (2 km) | About a quarter of the waves | Easier | Neighbourhood detail moves into the residual; σ likely rises | Cheap, but throws information away |
| **F. Smaller scale** (500 m or 250 m) + whitening | 4–16× the waves | Whitening is less exact where the prior matters, and T grows to 800–3,000 | Little gain unless C or D comes too, since σ barely moved from 1 km to 500 m | More cost, and a cap risk at 250 m |
| **G. Learned length-scale** | Length-scale becomes a parameter | Adds a stiff hyperparameter coupled to every wave | Lets the data choose the scale | The basis must cover the shortest scale. Hardest; defer |

## Recommendation

One change per fit, in this order:

1. **Fix the bath data first.** The remaining stall is set in warmup by something nonlinear, not by the rotation. The suspects are the mostly mistyped sparse bath cells, the heavy tails (ν 7.2) and the season trading off against the walk. Apply the 83-listing bath rule after review, then run free 5% checks with the corrected data and with ν fixed near 20. Once the step recovers, fit the whitened 1 km model to get a converged baseline with location.
2. **D, the building effect,** on top of the converged 1 km surface. This is the change that matters most for the model. It explains why σ stopped improving, why the amplitudes inflate, and why the intervals are too narrow.
3. **C, Matérn 3/2 against SE,** compared on held-out data once both converge. If the amplitudes stay inflated after D, C is the fix.

Skip E, and hold F and G until the building effect is in. B is a fallback if A still leaves the amplitudes unconverged.
