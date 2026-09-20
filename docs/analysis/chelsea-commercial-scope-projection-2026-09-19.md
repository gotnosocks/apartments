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

No refit or main-selection change has occurred. Archived implementation
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

The intended source-only refit keeps the established PyMC specification and
sampling protocol: natural cubic floor spline, full/half/balance bathrooms,
shared Student-t noise, four chains, 4,000 warmup and 6,000 retained draws per
chain, nutpie/Numba diagonal NUTS, target acceptance 0.93, max depth 10 and seed
20260924. No sampler-shortening or simultaneous feature experiment is planned.
The new full-cohort graph-parity run initially stopped when the sandbox denied
writes to the existing PyTensor/Numba cache (session 32521, exit 1). A retry with
cache access is running (session 82508); no numerical settings changed. This is
a compilation-environment failure, not a failed graph-equivalence criterion.
Compare common retained observations against the original expanded-floor fit,
with the explicit cumulative policy and archived code checks, rather than
claiming improvement from dropping observations. Repeat fixed panels and inspect
the new residual tail. A separate later bathroom-prior experiment can address
the known sparse second-half-bath coefficient without confounding this revision.
