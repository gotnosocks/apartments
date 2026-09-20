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
full projection replay has not yet been performed.

## Preflight and remaining work

The source comparison and reader preflight now accept an explicit policy path.
Without it, they still enforce the original four-ad experiment. With it, they
verify the policy's original-source binding, unique named ads, allowed actions,
and exact equality to the published policy bytes, then enforce the same ordered
retention, inverse, captured-current and inherited-sidecar checks. The full
posterior-comparison command has not been generalized to arbitrary policies.

All 65 source-comparison/preflight tests pass, including changed policy bytes,
changed source binding, unreviewed membership, duplicate ads, invalid actions,
retained-value changes, lost floor sidecars and changed current observations.
The real source/evidence/design preflight is running with this explicit policy
(session 31195); its result is not yet established.

No refit or main-selection change has occurred. Before fitting, finish preflight,
verify replay, and handle archived implementation comparisons explicitly: the
floor verification optimization changed two loader-contract files, so the
previous narrowly defined loader-only comparison guard cannot simply be assumed
to accept a new fit. Preserve all mathematical and sampler equivalence checks.
Carry source annotations with exact retained-row/capture checks before any
promotion. The ongoing UI check concerns the earlier four-ad candidate, not
this newly published source. Other commercial-screen groups remain under review.
