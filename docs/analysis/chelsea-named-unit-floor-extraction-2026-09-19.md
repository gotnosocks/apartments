# Named-unit introductory floor claims

`attribute-evidence-v7` extracts an explicitly stated floor from an initial
named-dwelling introduction such as “Welcome to Apartment 1A on the second
floor”. The label identifies the claim's subject; its digits do not supply
the floor. This addresses the four disagreements found during the
[income-source review](chelsea-income-claim-review-2026-09-19.md).

The rule `named-unit-initial-offer-floor-v1` is anchored to the description's
start. It permits an optional welcome phrase and a short alphanumeric label
containing a digit, and requires an explicit numerical floor or a correctly
spelled ordinal from first through twentieth. Original description offsets are
preserved. Conflicting explicit assertions still become unresolved conflicts;
physical floor and floors above ground are not inferred.

The introductory sentence is screened for reference/media, shared-space,
comparison, conditional, uncertainty and negation language. A question is not
accepted as an assertion. Unrelated photo disclaimers in later sentences do not
suppress an otherwise explicit introduction. This is a conservative grammar,
not a complete floor parser or a general language-understanding system.

## Complete archived-description replay

The exact v6 implementation was replayed against v7 over **72,065 archived
description records**, comprising **40,531 distinct description inputs**.
Of those records, 71,813 attach to the accepted analytical cohort; 252 are
outside it. All changed descriptions were read in full.

Exactly **eight captures for four advertisements** change. Each previously had
no extracted description-floor assertion; each now has one:

| Advertisement | Named unit | New prose assertion | Existing fitted label proxy |
|---|---|---:|---:|
| 4810936 | 1A | 2 | 1 |
| 4817705 | 2D | 3 | 2 |
| 4902655 | 1b | 2 | 1 |
| 4968706 | 1C | 3 | 1 |

Every other extracted attribute, non-floor evidence item, conflict and warning
is unchanged. No out-of-cohort description changed. A broader introductory
grammar census also found advertisement 4837062's “forth floor” typo; this rule
leaves it unrecognized. The recovered claims do **not** increase current
known-floor coverage: they expose disagreements with existing proxies, and do
not establish one uniform numbering offset.

The replay is description-only. Structured-field conflicts are tested
separately. **148 extractor tests passed**, including the full reviewed
descriptions with exact hashes, original-string offsets, ordinal forms,
reference/shared/conditional negatives and preserved unrelated attributes.
Another **27 amenity-model, laundry-revision and elevator-audit tests passed**.

Artifact: `data/model/chelsea-named-unit-floor-description-replay-20260919`.
Manifest SHA-256:
`7eacb04633f535d86ed17624db3e3068ed6d32d618008d2eae59fa26497ba0b1`.
V6 implementation:
`4fbc1b5b7f15061206d708ad8775190dd4bf9f3930fe072422a75b4ba0c3789a`.
V7 implementation:
`9672d89140cd87bc01944fd0b01ffc4652f57f8b4666bf76f0002c989ef37bad`.

Reproduce using the archived v6 implementation:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.audit_named_unit_floor_extraction \
  --dataset data/model/chelsea-expanded-label-floor-analysis-20260919 \
  --evidence data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --reference-implementation data/model/chelsea-named-unit-floor-description-replay-20260919/attribute_evidence_v6.py \
  --output data/model/chelsea-named-unit-floor-description-replay-20260919
```

No frozen observations, fitted values or main selection changed. Applying these
claims requires a separately reviewed, reversible source projection and matched
refit. The residential-scope comparison uses its already frozen data. Other
floor grammars, the 139 Eighth Avenue/300 W17 address association and physical
numbering remain separate research questions.
