# Cumulative commercial-scope source revision

The prepared nine-ad policy has passed exact-capture validation and been
published as a separate analytical dataset. This is a source-scope correction,
not a fitted-price improvement or a new selected model.

The original expanded-floor source has 52,653 observations. This revision keeps
52,644 observations, 22,147 units and 1,127 buildings. All 172 capture-time ACTIVE
observations are unchanged. Retained observation values and their order are
unchanged; the removed rows and complete decisions remain in a reversible
sidecar. Both the exact parent inverse and the full earlier lineage are checked
during publication.

## Decisions and evidence

The cumulative policy retains the previous exclusions for 1260588, 937046,
609730 and 2993341 and adds 1543471, 2391701, 806884, 947730 and 1466274.
The additions explicitly offer commercial loft, recording studio, event/office,
gallery/retail and pop-up retail products. No blanket building/unit exclusion,
price replacement or inferred physical-use date is applied. Mixed live/work and
ambiguous offers remain outside the policy.

All nine decisions were independently checked against the original expanded
source and all **16 attached own raw captures**. Validation checks source-row
hashes, exact descriptions/spans, raw JSON hashes, typed capture identity and
chronology. The new cumulative review clock is `2026-09-20T03:52:07Z`; references
to the prior reviews are preserved. It is the interpretation clock for this
new cumulative revision, not a claim that the source changed at that moment.

Published artifacts under `data/model/`:

- `chelsea-commercial-scope-decisions-20260919`, manifest
  `5a2b1a84273dcf39db8517003e859af91da44764a0413bf80055ccf2d65f9f1c`.
- `chelsea-commercial-scope-analysis-20260919`, manifest
  `27ad22fd2e4814915c3411c792d0305c01a218be27a14d17ee9f5f7ba3fde359`.

Decision preparation and projection exited 0 (sessions 92600 and 45853).
They use the existing `prepare_residual_scope_decisions` and
`models.project_residual_scope` interfaces with the cumulative policy at
`config/reviews/chelsea-commercial-scope-followup-20260919.json`. An identical
full projection replay passed (session 89838, exit 0), reusing the same artifact.

## Preflight and remaining work

The source comparison and reader preflight now accept an explicit policy path.
Without it, they still enforce the original four-ad experiment. With it, they
verify the policy's original-source binding, unique named ads, allowed actions,
and exact equality to the published policy bytes, then enforce the same ordered
retention, inverse, captured-current and inherited-sidecar checks. The full
posterior-comparison command now accepts the same optional `--policy`, records
its hash and verifies it remains unchanged throughout comparison.

All 65 source-comparison/preflight tests pass, including changed policy bytes,
changed source binding, unreviewed membership, duplicate ads, invalid actions,
retained-value changes, lost floor sidecars and changed current observations.
The real source/evidence/design preflight passed with this explicit policy
(session 31195, exit 0). Its artifact is
`data/model/chelsea-commercial-scope-reader-verification-20260919`, manifest
`9c987f2bd95ec47f68cb382f03ba4f23b00c938bdb6388dd638e601da659f264`.
It verifies all 71,797 retained literal captures, the 16 removed captures, the
exact parent inverse and inherited sidecars. Both designs have rank 47 and the
same 47 features, priors, category bases, size reference and floor knots
`[1, 5, 10, 20, 35, 57]`. Empirical centering changes; the elevator raw-unit prior
standard deviation changes by approximately −0.00620%, explicitly reported
rather than described as an identical numerical design.

The full refit has now been launched; the main selection is unchanged. Archived implementation
comparisons now explicitly handle the floor verification optimization in its
two loader-contract files, preserving mathematical and sampler equivalence
checks.
`models/floor_replay_compatibility.py` now recognizes exactly that reviewed
copying refactor by constructing the expected syntax tree from each bound
original implementation. It requires the public deep-copy wrapper, internal
top-level copy and exact replay-call substitutions; other code differences are
rejected. Both actual archived floor contracts pass, and adversarial changes to
floor values, exceptions, copy ownership and unrelated functions are rejected
(three tests covering both contracts and invalid inputs). After the preflight
finished, this guard was wired into the posterior comparison. The integration
tests confirm that changed contract files are tracked and then checked against
bound archived code; changing a floor value is rejected. Mathematical/sampler
files outside the existing loader changes and these two exact refactors remain
disallowed. The combined compatibility, source-comparison and preflight suites
now pass 70 tests.
Carry source annotations with exact retained-row/capture checks before any
promotion. The UI check for the earlier four-ad candidate has now passed
(session 28428); it does not validate a fit of this newly published source.
Its artifact manifest is
`de5b582ee0b25f5e33a63bef2093e1127c405cf4523bc5e3e2ddee1ceb229c94`.
Other commercial-screen groups remain under review.

The source-only refit keeps the established PyMC specification and
sampling protocol: natural cubic floor spline, full/half/balance bathrooms,
shared Student-t noise, four chains, 4,000 warmup and 6,000 retained draws per
chain, nutpie/Numba diagonal NUTS, target acceptance 0.93, max depth 10 and seed
20260924. No sampler-shortening or simultaneous feature experiment is planned.
The new full-cohort graph-parity run initially stopped when the sandbox denied
writes to the existing PyTensor/Numba cache (session 32521, exit 1). A retry with
cache access passed (session 82508, exit 0); no numerical settings changed.
The graph-parity manifest is
`7091f3b05845f17b313ea70e4340ba4c38f02e820a2f8139843e50cdbc083058`,
at `data/model/chelsea-commercial-scope-spline-graph-parity-20260919`.
All three tested parameter points pass; maximum absolute log-density difference
is `4.37e-11` and maximum absolute gradient difference `1.40e-9`. The source and
all recorded implementation hashes were checked again before launching the fit.
This proves numerical agreement at those points, not sampler convergence.

The full fit is running in
`data/model/chelsea-bayesian-commercial-scope-spline-disk-20260920` (session
30312; log `/tmp/chelsea-commercial-scope-spline-fit.log`). It uses the explicit
settings above, including shared residual scale, building prior 0.35, unit prior
0.25, feature prior multiplier 1 and floor prior 0.10. No shortened trial or
surrogate model is substituted. Do not launch another fit while this session is
live; completion and diagnostics remain unverified.

All four chains subsequently completed 4,000 warmup and 6,000 retained draws,
with zero divergences in the sampler progress records. Posterior export finished
and the process entered diagnostics/reporting at `2026-09-20T04:33:54Z`.
The posterior contains 4,340,049,047 bytes; its SHA-256
`514d96a4ba1c000b37d199ec3c1f7b174d2a2314ef58f27ecb273cd1bf14e765`
was independently recomputed and matches both storage metadata and the posterior
checkpoint. This establishes a preserved export, not passing posterior gates.
Full fit publication, diagnostics and matched comparisons remain pending.

The fit subsequently completed successfully (session 30312, exit 0), and the
entire published fit bundle passed independent hash verification. Manifest:
`a66e8d2e0b6f6515ab29dd729263f8c441417338a8bfaf4d871a90601db12776`.
Primary, derived-effect and floor diagnostics all pass. Maximum R-hat values
are 1.00737, 1.00177 and 1.00498 respectively; minimum bulk ESS values are
885.7, 1179.9 and 1800.8. There are zero divergences and zero depth-limit hits.
The status is `exploratory_converged`, not evidence of causal identification.
The matched comparison is now running (session 84842; log
`/tmp/chelsea-commercial-scope-spline-comparison.log`). The unchanged eight-case
development review is also running; neither result is yet established and the
main selection remains unchanged.

The existing four annotations on three retained advertisements have been
carried from the original expanded source to this source with the established
exact-row/capture and original-review-clock checks (session 2784, exit 0). Outputs are
`chelsea-commercial-scope-source-issues-20260920` and
`chelsea-commercial-scope-source-issue-linkage-20260920` under `data/model/`.
Independent public loading passed. The annotation manifest is
`da2c1e0c4df5ef5a30a8a363c15c59f84cf9ef474fb0dd6b76923b9d7718a751`;
the linkage manifest is
`e3139c46065458d00f4271248ee73aac33922c15c7499a1069e196bf91ad2456`.
The saved fit protocol and archived implementation checks also pass:
`chelsea-commercial-scope-fit-protocol-check-20260920`, manifest
`86bf798e812927e4b21b7f3470b7377a56fddf15176820e04ac29c96a9473f74`.
These checks establish the intended matched experiment, not posterior convergence.
Compare common retained observations against the original expanded-floor fit,
with the explicit cumulative policy and archived code checks, rather than
claiming improvement from dropping observations. Repeat fixed panels and inspect
the new residual tail. A separate later bathroom-prior experiment can address
the known sparse second-half-bath coefficient without confounding this revision.

Once the fit has completed and its diagnostic gates have been inspected, the
matched comparison command is:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.residual_scope_fit_comparison \
  --reference data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919 \
  --reference-dataset data/model/chelsea-expanded-label-floor-analysis-20260919 \
  --candidate data/model/chelsea-bayesian-commercial-scope-spline-disk-20260920 \
  --dataset data/model/chelsea-commercial-scope-analysis-20260919 \
  --policy config/reviews/chelsea-commercial-scope-followup-20260919.json \
  --output data/model/chelsea-commercial-scope-spline-comparison-20260920
```

This command was launched only after fit publication and verification.
Fixed residual/floor panels and candidate UI
validation remain separate requirements before any main-selection change.
