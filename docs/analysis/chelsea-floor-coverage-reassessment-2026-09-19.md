# Floor extraction coverage reassessment

The reported 56.8% is correct for the selected dataset, but reflects an
unfinished label-inference policy. It is not the amount of floor information
available in the archive. Calling extraction complete overstated its scope:
the previous work completed a full-cohort pass of one narrow rule.

The main parser accepts a positive one- or two-digit prefix followed by one
letter, such as `3D` or `14B`. It omits numeric-only labels, letter prefixes,
multi-letter suffixes and explicit ordinal labels. The new audit verifies the
saved projection, replays its rules and reconstructs its exact ordered parent;
an independent census agrees with these counts.

| Population | Known floor | Total | Coverage |
|---|---:|---:|---:|
| Fitted price observations | 29,907 | 52,653 | 56.8% |
| Distinct units with any known-floor observation | 10,980 | 22,155 | 49.6% |
| Capture-time ACTIVE observations | 95 | 172 | 55.2% |

169 units have a mix of known and unknown observations, accounting for 402
missing-floor rows. Reusing another advertisement's floor across those rows
requires an explicit identity/time policy; the census does not do that.

Of the 22,746 unknown-floor rows, **only seven lack a captured unit label**.
None has different literal labels across its own captures, or conflicting
numeric candidates under the existing rule. The status
`unresolved_or_conflicting_capture_labels` obscures the main issue: all 20,268
rows in that status are syntax exclusions here, not capture conflicts.
Other missing rows are withheld by building-wide conflict exclusions (1,567),
building-count bounds (694), or missing counts for two-digit prefixes (217).

## Common omitted formats

These hypotheses use literal own-capture labels. They are candidates for a
broader extraction rule, not accepted corrections or an updated fit.

| Candidate rule | Example | Missing observations | Units | ACTIVE rows | Existing explicit-floor comparisons |
|---|---|---:|---:|---:|---|
| Hundreds portion of 3–4 digit labels | `1404 → 14`, `906 → 9` | 5,456 | 2,492 | 32 | 13 agree; five disagree, all at 160 W22 |
| North/south wing prefix | `S15K → 15` | 1,245 | 555 | 7 | Three agree; none disagree |
| Front/rear suffix | `4FE → 4`, `3RW → 3` | 875 | 405 | 3 | 20 agree; one disagrees at 244 W16 |
| Explicit ordinal floor label | `11THFLOOR`, `11THFL` | 2 | 2 | 0 | No existing reference |

These nonoverlapping formats account for 7,578 missing observations. Treating
every candidate as correct would raise coverage to 71.2%; that illustrates the
omitted scope, **not a validated coverage result**. More general multi-letter
suffixes cover 1,839 missing rows, but include misleading labels such as `1BR`
and `1BEDS`. Five-digit labels, one/two-digit numeric labels, address fragments,
penthouse/duplex names and other prefixes need separate rules.

The numeric candidates include substantial groups at Caledonia, 21 Chelsea,
Carteret, 101W15, Kensington House, 3Eleven, 507 West Chelsea and Chelsea Centro.
Concrete current misses include 21 Chelsea `517`, `613`, `219`, `318`; 3Eleven
`2105`, `3107`, `3921`, `2020`; Carteret `1408`; and 507 West Chelsea `404`.
N/S prefixes occur frequently at 555 West 23rd, The Tate and Ruby Chelsea.

The existing building-count guard allows 4,748 numeric, 502 wing-prefixed and
837 front/rear candidates, plus one ordinal label. Count compatibility is not
proof of numbering, and missing count is not proof of an invalid label. For
example, 743 N/S-prefixed rows lack a building count even though selected S15K
and S8P source claims agree. The five numeric disagreements at 160 W22 require
review before treating the hundreds convention as universal.

## Completed disagreement review

All six disagreements above have now been reviewed against their complete own
descriptions and all twelve raw captures. The five at 160 W22 are erroneous
floor extractions from **“Photos are of the same unit on the 3rd floor.”** No
structured floor field supports floor 3. These are reference-photo descriptions,
not evidence against the numeric numbering convention. The five claims need
source-bound corrections in the next analytical projection; repairing the live
extractor alone does not change a frozen dataset.

244 W16 `1RE` explicitly says **“This apartment is on the 2nd floor walk-up”**.
That extraction is correctly scoped. Retain the source assertion and the
conflicting label evidence; neither a generic suffix overwrite nor a building-wide
offset is justified. See the [complete six-case review](chelsea-expanded-label-rule-conflicts-2026-09-19.md).

## Next extraction revision

1. Review all new-rule disagreements using the advertisement's own full
   description, including any reference-photo/video disclaimers.
2. Separate unsupported syntax, missing labels and actual capture conflicts in
   the next projection's provenance.
3. Add named rules for supported formats, preserving original labels, inferred
   floor, rule identity and source evidence separately.
4. Audit high-impact building-count and missing-count exclusions and complex
   numbering. Keep advertised labels separate from physical height.
5. Publish a new reversible projection and compare its spline fit with the
   selected model. Existing posterior and source artifacts remain immutable.

Reproduce the census with:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m models.floor_coverage_audit \
  --dataset data/model/chelsea-label-floor-analysis-20260919 \
  --output data/model/chelsea-floor-coverage-audit-20260919
```

The output retains every missing row with exact labels, every candidate and
every explicit-floor comparison, bound to the selected source and projection
hashes. No scrape, source edit, imputation or model fit occurred in this audit.
An identical full-cohort replay passed, and 23 focused audit tests cover the
named hypotheses and deliberately unsupported label forms.
