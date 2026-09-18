# Research design: observed listed-floor increments

`models.bayesian_floor_increment_design.FeatureDesign` replaces the standardized linear `listed_floor` feature with

`sum(beta_k * 1(known listed_floor > k))`.

This is a new isolated, versioned design. It has **not been fitted**, has no posterior floor increments, and does not change an accepted model or serving behavior. Sparse floor evidence does not earn automatic inclusion in the main model.

Thresholds are the sorted, finite floor labels observed in the training cohort, excluding the maximum. They are not a manufactured integer range. The cleaned 52,704-row cohort has only 364 known labels and 52,340 unknowns. The known values enter through the existing `advertised_floor` alias; the `listed_floor` field itself is null. Its 19 supported levels are:

`1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, 17, 20, 24, 28, 41`.

There are 18 increment terms. `listed_floor_gt_11` distinguishes observed labels 11 and 14; it is not three separately estimated premiums for crossing 12, 13, and 14. Gap contrasts also include 17→20, 20→24, 24→28, and 28→41. Public matrix/raw-feature transformation rejects any known label absent from fitted support, including labels inside these gaps. A supported negative floor or ground label zero is retained in its natural numeric order; neither is recoded as missing or shifted to floor one. Unknown observations activate no floor thresholds and retain a distinct unknown indicator when it varies in training.

Every supported level records rows, distinct units, and distinct buildings. Adjacent observed-level contrasts additionally record shared buildings and shared units at both endpoints. In this cohort, 11 of 18 adjacent contrasts have no shared building. Labels 9, 16, 20, 28, and 41 each have only one observation. Two units appear at both labels 2 and 3: this is a source-review question, not established physical movement between floors. Matrix rank alone cannot establish useful separation from building/unit effects. The full cleaned-cohort design has 60 active columns and rank 60.

The increment prior scale is explicitly configurable and provisionally defaults to 0.15 log points. Increments are independent zero-mean Normal coefficients under the existing compatible graph; their signs are unconstrained, so prices need not increase monotonically with floor. The cumulative prior standard deviation from the minimum to maximum supported label is `0.15 * sqrt(18) = 0.636`. The old standardized slope implied roughly `0.15 * (41 - 1) / 3.99 = 1.50` for that contrast. These are different priors as well as different representations; a comparison must audit both instead of attributing changes only to flexibility.

Listed labels remain separate from physical height. No unit-name parsing, skipped-floor correction, or inference of physical floor occurs. Existing physical-floor, elevator interaction, and listed-minus-physical gap columns retain their exact prior encoding; they are all absent or inactive where source values are unavailable. If future data fully populate physical floor and listed-label gap, their algebraic relationship with a saturated listed-floor representation can cause rank deficiency. The existing fail-closed rank gate is retained; that future representation must be reviewed explicitly.

All nonfloor raw columns, centered columns, and prior scales are unchanged from the referenced bathroom design. Save/load persists explicit numeric/category/raw/active feature order, supported levels/thresholds, means, priors, support metadata, and a version tag. Loading validates semantic order independently of JSON key sorting and refuses mismatched feature inventories, thresholds, active masks, or priors. This loader is specific to the new version; existing frozen loaders and experiments are untouched.

Focused validation is in `tests/test_bayesian_floor_increment_design.py`: exact indicator boundaries, negative/ground handling, gaps, unknowns, unsupported transforms, endpoint support counts, unchanged nonfloor and independently observed physical-floor columns, serialization parity, and malformed/tampered metadata. Commands use `uv run --frozen --no-sync python -m pytest`; no fit or network request is part of this design task.

The immutable full-cohort design audit is `data/model/chelsea-listed-floor-increment-design-20260918/report.md`. It includes the verified cleaned source manifest/observation hash, saved feature and time designs, exact frozen implementation files and runtime versions, all floor support/gap records, and a proof that 42 nonfloor/reporting columns and the time design remain exactly unchanged. The measured extreme prior comparison is 1.503233 versus 0.636396 log SD. Its publisher is `models.publish_floor_increment_audit`; the artifact report records the exact `uv` invocation. There is no posterior in this artifact.
