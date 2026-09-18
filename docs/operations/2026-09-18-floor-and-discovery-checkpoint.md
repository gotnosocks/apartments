# Floor experiment and bounded discovery checkpoint

The versioned v4 PyMC runner, explicit floor-design reconstruction, joint floor
contrast reports, posterior-check compatibility and apartment-analysis support
are implemented. No floor posterior has been fitted or selected. The main model
remains the explicitly selected accepted baseline.

Validation:

- Full suite: **1,500 passed, 3 skipped, 9 warnings**, 329.62 seconds, exit 0.
- After strengthening graph-proof dependency/settings checks, the focused v4
  suite passed **15 tests**, including four added proof-binding regressions.
  The complete suite preceded only this small code change and documentation.
- Full cleaned-cohort graph proof: 52,704 rows, three parameter points and
  23,431 gradient coordinates. Maximum absolute density/gradient differences:
  2.92e-11 / 1.52e-9. Artifact:
  `chelsea-bayesian-floor-graph-parity-20260918-v3`.
- Discovery: 28 new Oxylabs requests, all accepted, plus four verified reused
  captures. Offline replay reproduced the immutable report without requests.
  The 213-advertisement review publisher also replayed identically.
- `git diff --check` passed; changed source was checked against credential
  values without printing them, with zero matches. Credentials and large data
  artifacts remain ignored.

Python commands used `uv run --frozen --no-sync python`, with
`UV_CACHE_DIR=/tmp/apartments-uv-cache` because the default cache is read-only.
This preserves the installed inference environment; it does not claim a fresh
lockfile sync. The test environment and PyTensor threading controls follow the
[previous checkpoint](2026-09-18-bayesian-main-checkpoint.md).

The source-cleaned shared-noise fit first failed the fixed parameter gate
(R-hat 1.01039). Its longer 4-chain, 4,000-warmup/6,000-retained retry finished
sampling but was killed at 23:20:09 UTC for memory exhaustion before a posterior
checkpoint existed. Kernel logs confirm the kill; there is no recoverable fit
or interpretable interval from that run. The floor readiness artifact was
prepared before this failure and remains an unlaunched proposal. Large fits
must wait for validated bounded-memory result storage and export.

See the [source revision status](../analysis/chelsea-bayesian-source-revision-2026-09-18.md),
[floor specification](../model/listed-floor-increment-design.md), and
[actual discovery coverage](../analysis/chelsea-rental-discovery-2026-09-18.md).
