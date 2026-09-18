# Reviewed bathroom research projection — 2026-09-18

This revision applies 20 named, source-bound decisions to the bathroom research projection. It quarantines one explicit office advertisement, marks bathroom composition as unknown for 17 advertisements with externally shared bathroom/toilet access, and accepts two explicitly corroborated multiple-half-bath layouts. The main analytical dataset and serving model remain unchanged.

## Decisions and exact scope

| Action | Advertisements | Evidence and interpretation |
|---|---|---|
| Quarantine nonresidential advertisement | 3303145 | Explicit “NON RESIDENTIAL - ONLY FOR OFICE USE.” The original observation is retained in `quarantined.jsonl`. |
| Mark bathroom composition unknown | 16 named advertisements at 333 West 29th Street | All 25 captures were independently reread. Every advertisement explicitly describes shared bathrooms or toilets. Two distinguish a private shower from shared toilets; neither supports a private full/half fixture inventory. |
| Mark bathroom composition unknown | 2430461 | Explicitly describes two half and two full baths shared with other apartments on the floor. Reported full=1, half=0 does not describe private apartment composition. |
| Accept corroborated multiple half baths | 1945700 | Explicit one full and two half baths matches reported full=1, half=2. |
| Accept corroborated multiple half baths | 2762077 | Explicit two baths and two powder rooms matches reported full=2, half=2. |

The 16 named shared-access advertisements are 1536491, 2533438, 2204760, 1530908, 2635017, 2420686, 2379476, 2584659, 2582396, 1540253, 2555696, 2627433, 1646782, 2201202, 2571848, and 1700760. This is an exact advertisement list, not a building-wide rule or a claim about other units or dates.

No count is inferred or corrected from ambiguous text. A reviewed shared-access flag does not mean zero private fixtures. It means the reported fixture totals cannot safely represent private apartment bathroom composition. The two affirmative corroborations remove **only** `multiple_reported_half_bathrooms_review_required`; counts and any other flags remain intact.

## Preserved fields and interpretation clock

Every surviving observation preserves `reported_full_bathrooms`, `reported_half_bathrooms`, the original scalar `bathrooms`, all price fields, and every other original analytical field exactly. Shared-access cases retain their reported counts and original per-field count statuses. Their derived `bathroom_count_evidence` gains:

- `composition_status: reviewed_external_shared_access_composition_unknown`
- `reviewed_external_shared_bathroom_or_toilet_access` in `flags`

The model can treat flagged bathroom composition as unknown without changing what the source reported. Existing flags are preserved. For each changed surviving observation, `bathroom_count_before_review` retains the original reported counts and evidence, and `bathroom_review` records the decision ID, source projection row hash, action, and interpretation time.

The decision interpretation clock is **2026-09-18T19:56:11+00:00**. It is separate from the original capture and analytical knowledge clocks, which are not rewritten. These are retrospective research interpretations of existing source captures, not historically available feature labels.

Each decision binds the analytical audit ID, advertisement ID, unit identity, canonical URL, every source capture, raw/body/description hashes, exact description text, and literal evidence offsets. The decision bundle also binds both existing review bundles, the bathroom audit, the original projection, and the implementation hash. All source descriptions were rechecked before publication.

## Before and after

| Measure | Original bathroom projection | Reviewed research projection |
|---|---:|---:|
| Observations | 52,712 | 52,711 |
| Known reported full counts | 52,712 | 52,711 |
| Known reported half counts | 52,555 | 52,554 |
| Complete, unflagged bathroom composition | 52,522 | 52,508 |
| Rows with review flags | 33 | 46 |
| Multiple-half review flags | 33 | 30 |
| Zero-full review flags | 4 | 3 |
| External-shared-access review flags | 0 | 17 |

Flag counts overlap. The decrease in reported-count coverage comes only from the quarantined office row. The known reported counts on retained shared-access cases remain present; their composition is unusable for the private-bathroom interpretation. Sixteen previously unflagged rows acquire a shared-access flag; one shared-access row already had unusual-count flags. Two corroborated layouts become unflagged.

## Artifacts and verification

- Decisions: `data/model/chelsea-bathroom-research-decisions-20260918`.
- Reviewed projection: `data/model/chelsea-reviewed-bathroom-projection-20260918`, version `reviewed-bathroom-counts-projection-v1`.
- `changes.jsonl` records source-linked before/after derived fields for all 20 decisions.
- `quarantined.jsonl` preserves the full original office observation.
- Implementation: `models/bathroom_research_revision.py`.

Ten focused revision tests cover retained source counts, preservation of other flags, quarantine behavior, source-row/identity/hash/span/capture tampering, refusal to accept changed corroboration wording or counts, and deterministic publication/replay. The complete bathroom-focused set has 28 passing tests. Decision preparation and projection both replayed exactly against the published bundles. An independent full-cohort comparison verified that every surviving reported count and original analytical field is unchanged, all untouched rows are byte-equivalent under canonical JSON, and only advertisement 3303145 was removed. No scraping or fitting was performed for this revision.
