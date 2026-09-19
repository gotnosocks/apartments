# Unit-label floor inference: first source-bound check

A first inference rule extracts the positive one- or two-digit prefix from a
unit label ending in one letter: `3D → 3`, `14B → 14`. It reads StreetEasy's own
`/propertyDetails/address/displayUnit`, retaining the original literal and rule.
It does not substitute a latest listing, parse the URL, or reinterpret the
inferred label as physical height. Numeric-only, leading-zero, penthouse,
letter-prefix and compound labels remain unresolved under this initial rule.
These are candidates for a future measurement policy, not patched source claims.

The verified audit covers all **71,906 captures / 52,704 observations / 22,158
units** in the frozen research cohort. It proposes a label-derived floor for
**31,931 observations / 11,722 units / 802 buildings**. No observation has two
different inferred candidate values across its captures; this does not establish
that the candidates are correct.

Among 213 observations with both a candidate and an existing explicit floor
claim, 176 agree and 37 disagree. At the distinct-unit level, **135 of 164 units
agree throughout their comparable observations; 29 have at least one
disagreement**. Repeated observations do not count as independent agreement
units. The explicit claims themselves have source and extraction errors, so
these counts are neither a population accuracy estimate nor proof that the
numeric prefix is the side that is wrong.

Examples reviewed against captured descriptions:

- At 152 West 20th Street, labels `1C`, `1D`, `2D` and `3D` are described as floors
  2, 2, 3 and 4, respectively. The descriptions also distinguish the number of
  flights. This suggests a systematic numbering offset to investigate; it does
  not establish a physical-height map for every unit in the building.
- Labels `34A` at 337 West 14th Street and `41A` at 115 West 23rd Street accompany
  explicit third- and fourth-floor wording. Multi-digit prefixes cannot be
  interpreted consistently across buildings without additional evidence.
- The modeled third-floor claim for 307 West 29th Street `4A` comes from wording
  about a video of the same apartment on the third floor, following a similar-unit
  photo disclaimer. This is an extraction/scope review case; the reference is not
  reliable ground truth merely because it was already in the dataset.
- Previously reviewed identities at 180 Seventh Avenue and 452 West 22nd Street
  also have conflicting floor descriptions across advertisements. Label inference
  cannot resolve these source conflicts by itself.

A complementary check uses the 35 apartment-floor claims in the stratified
48-capture description review, all previously unknown to the model. The first
label rule covers 18: 16 agree and two disagree. The disagreements are `1B` at
180 Seventh Avenue and `1C` at 433 West 24th Street, both described as second-floor
apartments. This selected development sample also cannot estimate corpus
accuracy. Seventeen claims have labels outside the first rule.

The next measurement iteration should preserve explicit and inferred evidence
separately, review systematic building numbering, inspect source disagreements,
and validate additional label rules on different units. Do not derive building
height, skipped-floor conventions or physical change dates from these prefixes.
The elevator interaction should name the actual metric and its evidence policy
when fitted. Existing source and floor-comparison fits remain unchanged.

Reproduce the audit with:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m models.floor_label_research \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --descriptions data/model/chelsea-analysis-descriptions-20260918 \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --refresh data/probes/chelsea-candidate-refresh-20260918 \
  --output data/model/chelsea-unit-label-floor-audit-20260918
```

The artifact contains every source label, hash, inferred candidate, observation
comparison and disagreement, plus frozen code. The complementary comparison is
`data/model/chelsea-unit-label-description-comparison-20260918` and is bound to
both input manifests. Twenty-three tests cover rule boundaries, repeated-unit
counts, conflicting capture labels, unknown references, own-listing scope,
immutable replay and modified source-shard rejection.
