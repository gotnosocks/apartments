# Label-floor runtime follow-up, September 19, 2026

Leave the frozen fits unchanged. A separate, exact PyMC graph could plausibly reduce the cost of future fits by sharing additive feature blocks independently. This has **not been implemented or benchmarked**, and the size reduction below is not a sampling-speed claim.

The expanded-floor graph has 52,653 observations, 93 feature coefficients, and 18,613 unique complete feature rows. The existing graph computes one dense feature product over those rows, then gathers predictions back to observations. Floor labels therefore split rows that would otherwise share the same non-floor features.

Read-only reconstruction of the saved final design gave:

| Feature block | Columns | Unique rows | Dense entries |
|---|---:|---:|---:|
| Complete current feature matrix | 93 | 18,613 | 1,731,009 |
| Everything except the 51 floor thresholds | 42 | 12,919 | 542,598 |
| Everything except thresholds and floor-unknown indicator | 41 | 11,562 | 474,042 |

These are exact uniqueness counts, without rounding or target aggregation. They were calculated from `chelsea-bayesian-label-floor-disk-20260919/fit/feature-design.json` and the final label-floor source dataset. The source manifest SHA is `5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605`.

## Smallest useful graph experiment

Independently compress the non-floor and floor blocks, compute their PyTensor matrix products against slices of the **same beta vector**, then gather and add them per observation. Keep all saved design columns, means, parameter names/order, priors, time effects, group effects, and Student-t likelihood unchanged. This remains the same PyMC posterior; only deterministic arithmetic sharing changes. A floor block has at most one pattern per observed floor plus unknown, so its dense work is tiny compared with the current cross-product of floor labels and other features.

A specialized alternative computes the ordered floor contribution as a prefix sum of the 51 threshold coefficients, indexed by the supported floor rank, minus the saved floor-centering offset. Unknown floor uses zero uncentered threshold contribution; its missingness indicator remains separate. The installed PyTensor NUMBA backend supports one-dimensional cumulative sums. The pooled floor/elevator term can similarly be a small lookup or a separate feature block.

Independent block compression is the lower-risk first experiment: it directly reuses the saved centered design and avoids introducing new rank/unknown-floor logic. Prefix-sum optimization would save only a few thousand additional dense entries once blocks are separated. Neither approach removes the 52,653-observation likelihood, unit/building gradient gathers, or NUTS trajectory work.

Before adopting a new graph, prove full-cohort log-density and unconstrained-gradient agreement at identical dispersed points, including floor-unknown and elevator-unknown cases. Then compare warmed **joint logp-and-gradient** callbacks through the actual nutpie backend, in an otherwise quiet environment. Only an appreciable steady-state improvement should justify a separate production-length matched sampling comparison. Startup timing or arithmetic counts alone are insufficient.

## What currently limits interpretation of runtime

The existing expanded-floor parity artifact reports approximately 2.01 ms for standalone NUMBA logp and 1.89 ms for standalone gradient evaluation. Nutpie compiles a joint logp-and-gradient function, so these standalone timings must not simply be added to estimate a NUTS step. No operator-level profile was collected here; dense feature arithmetic is a plausible contributor, not a proven exclusive bottleneck.

Early expanded-floor warmup used about 127 NUTS steps per iteration, versus about 63 in the preceding sparse-floor run. The larger, correlated cumulative floor curve can increase trajectory work independently of arithmetic cost; an equivalent graph rewrite will not remove posterior geometry. Initial concurrency also put eight sampling chains across six physical CPU cores, so simultaneous fits confounded per-fit throughput. The interaction fit was subsequently paused while the primary fit continued, with a watcher arranged to resume it. No sampler or frozen implementation was changed by this review.

The concrete recommendation is to finish the existing model comparison first and retain this bounded exact-graph experiment for a later runtime improvement. No additional profiling, benchmark, or sampling run was started for this note.
