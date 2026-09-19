# Label-floor runtime follow-up, September 19, 2026

The independent feature-block graph below has now been implemented and checked during recovery from the expanded fit's tree-depth failure. Both full-cohort density/gradient parity proofs passed. The original fit and its diagnostics remain unchanged. The size reductions below are not sampling-speed claims.

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

Independent block compression was chosen because it directly reuses the saved centered design and avoids introducing new rank/unknown-floor logic. Prefix-sum optimization would save only a few thousand additional dense entries once blocks are separated. Neither approach removes the 52,653-observation likelihood, unit/building gradient gathers, or NUTS trajectory work.

Before adopting a new graph, prove full-cohort log-density and unconstrained-gradient agreement at identical dispersed points, including floor-unknown and elevator-unknown cases. Then compare warmed **joint logp-and-gradient** callbacks through the actual nutpie backend, in an otherwise quiet environment. Only an appreciable steady-state improvement should justify a separate production-length matched sampling comparison. Startup timing or arithmetic counts alone are insufficient.

## What currently limits interpretation of runtime

The existing expanded-floor parity artifact reports approximately 2.01 ms for standalone NUMBA logp and 1.89 ms for standalone gradient evaluation. Nutpie compiles a joint logp-and-gradient function, so these standalone timings must not simply be added to estimate a NUTS step. No operator-level profile was collected here; dense feature arithmetic is a plausible contributor, not a proven exclusive bottleneck.

Early expanded-floor warmup used about 127 NUTS steps per iteration, versus about 63 in the preceding sparse-floor run. The larger, correlated cumulative floor curve can increase trajectory work independently of arithmetic cost; an equivalent graph rewrite will not remove posterior geometry. Initial concurrency also put eight sampling chains across six physical CPU cores, so simultaneous fits confounded per-fit throughput. The interaction fit was subsequently paused while the primary fit continued, with a watcher arranged to resume it. No sampler or frozen implementation was changed by this review.

The first full fit subsequently hit depth10 on 1,392/24,000 retained transitions, failing the declared acceptance gate despite good R-hat/ESS and zero divergences. That result justified the bounded graph experiment alongside an explicitly larger depth ceiling for replacement fits. The original paused interaction attempt was cancelled with its trace and cancellation record preserved.

## Completed callback measurements

Each graph was measured with 3,600 warmed actual nutpie C logp-gradient calls, alternating batches across three points. Floor-only median callback time fell from 3.0753 ms to 1.7604 ms (42.8%); pooled floor/elevator fell from 2.7700 ms to 1.9916 ms (28.1%). This establishes a reduction in numerical evaluation cost on this machine, not a full sampling speedup or a fastest-backend result. Statistical parameterization and priors are identical; the graph rewrite cannot itself remove long NUTS trajectories.

Immutable proofs: `chelsea-label-floor-block-development-parity-20260919` and `chelsea-label-floor-elevator-block-development-parity-20260919`. Maximum absolute gradient differences are 2.68e-9 and 3.84e-9, respectively. The replacement fits separately record depth14; all retained-draw and convergence requirements remain unchanged.
