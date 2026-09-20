# Candidate reader loading profile

The isolated candidate reader completed successfully. Its slow loading is
dominated by source-lineage reconstruction and repeated deep copying. This
provides a performance target; it does not establish the cause of the separate
UI crash or validate the UI.

One process loaded the exact saved residual-scope candidate using
`BayesianAnalysis.load`, accessed all rows and closed the reader. Selection
manifest verification took 0.003 seconds. Reader loading finished at 233.90
seconds; row access at 247.53 seconds; close at 247.54 seconds. Peak process RSS
was 4,517,004 KiB (about 4.31 GiB). The run used one BLAS thread and **cProfile**,
so these times include instrumentation overhead and are not a normal-run speed
benchmark. Session 90532 exited 0 and verified 52,649 rows.

| Profile location | Cumulative seconds |
|---|---:|
| Report construction | 193.58 |
| Source-lineage reconstruction | 181.75 |
| Deep-copy calls, across the process | 149.49 |
| Expanded-floor inverse | 97.70 |
| Two floor-label inverse calls | 60.98 |
| Design verification | 36.77 |

Cumulative times overlap; they must not be added together. About 763 million
function calls were recorded. The expanded-floor inverse invokes original-floor
verification as well as the outer lineage's floor inverse; inspect whether
equivalent validation/copying can be reused within one immutable load. Retain
all exact-source, capture, hash, chronology and mutation-detection checks.
Avoid persistent caches that can accept stale or modified artifacts.

Next, inspect mutation ownership and redundant validation in the two floor
contracts, implement a bounded optimization with adversarial contract tests,
then measure the same candidate both with and without instrumentation before
retrying the actual UI. Do not infer a speedup before measuring it, or confuse
reader performance with posterior sampler performance.

Frozen evidence: `data/model/chelsea-candidate-load-profile-20260919`, containing
the profiling script, stage/RSS events, sorted profile summary and hashes of the
five relevant implementation files. The candidate selection hash is recorded
in its manifest. No data, model, selection or validation gates changed.

## First bounded optimization

Internal floor forward replays now use temporary shallow row copies. These
functions only replace top-level fields and read nested values; they neither
mutate nor expose borrowed nested data as public results. Public `project_row`
still returns a deep copy, and both inverse contracts still reconstruct detached
rows. All hash, identity, literal, chronology, forward-transform and ancestor
checks remain in place. Duplicate ancestor validation has not been removed.

The floor/lineage suite passes 113 tests, including new nested-mutation isolation
checks. Another 224 evidence, residual-scope and fit-comparison tests pass. The
same full candidate loading profile is running against this implementation;
there is no measured speedup claim yet. Its output is
`/tmp/chelsea-candidate-load-optimized-profile.log` (session 1528).
