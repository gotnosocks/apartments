# Existing unresolved annotations after the residual-scope revision

The four existing unresolved findings on advertisements **2021775, 2728974 and 4141846** were carried from the expanded-floor source to the residual-scope source. The annotated observations and complete attached capture evidence are exactly equal. All issue identifiers, messages, literal spans, specifications and capture records remain unchanged, including the original reviewer and review timestamp **2026-09-20T00:08:00Z**. This is a verified carry-forward, not a new physical-attribute review or correction.

The findings retain the distinction between a furnished offer and explicit furnished-only terms, plus the existing unextracted laundry claim and structured/prose bathroom conflict. No source features, fitted values or main selection changed through this operation.

| Artifact | Manifest SHA-256 |
| --- | --- |
| Previous issues: `chelsea-expanded-floor-source-issues-20260919` | `23ca6c13d393d5580ccf41084e8061d5a8234ff4dd323431100998736fe528d7` |
| New issues: `chelsea-residual-scope-source-issues-20260919` | `71c0f2b0108cc19b3b445628633d81ce6705e2af2114a8d11a1bffd0719d65d2` |
| Linkage: `chelsea-residual-scope-source-issue-linkage-20260919` | `099eaa4fa41933e50deb7f6dc75f269ab445669d0f7d5175c0c5dac308ec48bf` |

All artifact paths are under `data/model/`. The linkage binds the old/new source and description-evidence manifests and archives the helper and its local reader dependencies. The issue records are byte-identical (19,202 bytes); specifications are also byte-identical. The new bundle passed an independent `source_issues.load_source_issues` call and both published bundles passed a subsequent independent manifest/file verification.

Nine focused tests passed, including actual publication, independent reload, idempotent replay, changed row/capture rejection and preservation of literal Unicode line separators. The first actual run (session 21507) published and independently loaded the issues but failed before companion publication because its publisher requires text, not bytes. The standalone helper was corrected and the same output paths were retried. Retry **82964 exited 0**, reusing the identical issue bundle and completing the linkage. No running jobs remain from this carry-forward.

Reproduce from the repository root:

```sh
PYTHONPATH=. UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --frozen --no-sync python docs/analysis/scripts/carry_residual_scope_source_issues.py \
  --reference data/model/chelsea-expanded-label-floor-analysis-20260919 \
  --candidate data/model/chelsea-residual-scope-analysis-20260919 \
  --evidence data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --previous data/model/chelsea-expanded-floor-source-issues-20260919 \
  --output data/model/chelsea-residual-scope-source-issues-20260919 \
  --linkage data/model/chelsea-residual-scope-source-issue-linkage-20260919
```

This operation does not establish attribute effective dates, resolve the four findings, fit a posterior or validate their display in a candidate UI. The separate income-restriction research annotations are outside this carry-forward.
