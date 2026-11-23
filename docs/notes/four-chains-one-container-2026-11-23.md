# Four chains in one container (2026-11-23)

The full onefit fit `u5-of` ran 2 containers of 2 chains each (500 warmup, 2,600 draws). Each
container spent about 350 s preparing the design, 119 s compiling and 2,836 s sampling (1.13 s
a sweep of 2 chains), 3,961 s in its fit stage. Two containers pay the prep and compile twice.
One container with all 4 chains pays them once. That is cheaper if a sweep of 4 chains costs
well under twice a sweep of 2, which holds if the GPU is not yet saturated at 2 chains.

Cost of a fit, in container seconds at one rate: two containers about 2 × (470 + 3,100 × 1.13)
= 7,946 s. One container about 470 + 3,100 × 1.13 × r, where r is the 4-chain sweep time over
the 2-chain one. Break-even is r ≈ 2.13. At r = 1.7 it saves 19%.

## Probe

At f8f32e6a (#1541), the same model, dataset and split as `mem-probe`, `4 20 20 1`, `--large
--lean` on an H200, label `chains4-probe`. The comparison is `mem-probe` (2 chains, the same
20 + 20 sweeps, 1.610 s a sweep). It is also the first lean (48 GiB) container. About 10
minutes, about $0.9. Not a model test.

## Predictions (written before launch)

1. The container runs to exit 0 in 48 GiB, with `memory_peak_bytes` between 15 and 22 GiB.
   P ≈ 0.85.
2. The four chains fit on the H200's 141 GB. P ≈ 0.85.
3. A sweep of 4 chains takes 1.9 to 3.2 s, central 2.4 s: r ≈ 1.5 against 1.610 s.
4. Decision: if r ≤ 1.7, run the next full onefit fit as one 4-chain container (about 1.8 h
   of wall time, inside the 9 h cap). If r > 1.7, keep two containers.

## Result

(after the probe lands)
