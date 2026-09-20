# Prepared location-scope follow-up

The next cumulative scope policy retains all nine existing exact-ad exclusions
and adds advertisement **2938067**, whose Manhattan structured address conflicts
with repeated Park Slope/Brooklyn description claims in both raw captures.
This finding came from the building-effect movement review. Its residual is
not the exclusion criterion, and no replacement address or price is inferred.

The reviewed observation is exactly equal to its row in the original expanded
floor source, including all nonfloor fields and capture membership. The prepared
policy therefore remains bound to the same original source as the earlier
cumulative scope policy. No sibling advertisement or whole building is excluded.

- Policy: `config/reviews/chelsea-location-scope-followup-20260920.json`, SHA256
  `42125f8d8e8a68b4f69d3ba7f02cedea918ab9f119c1de4540283a2ce6ef837d`.
- Combined review: `data/model/chelsea-location-scope-followup-review-20260920`,
  manifest `5f8a8d4e3458b837a755124583ab45ed11fbf6df71ab3d76691c3d46fea61b22`.
- Original raw location review: `chelsea-2938067-location-review-20260920`,
  manifest `e69a5bd1af646ff887b564294ed13beaa4a3ff9189a4c34ce498828c1e890042`.

Preparation and identical replay pass. The existing decision builder is running
with review clock `2026-09-20T05:40:18Z` to bind every own capture and validate
all ten decisions. Its pending output is
`data/model/chelsea-location-scope-decisions-20260920`.

This policy is **not yet applied**. The live direct-floor fit retains its frozen
nine-ad source plus the 24 floor additions, so its eventual matched comparison
isolates those floor changes. Combining the location correction with the floor
revision later will require revalidating the exact source and floor-policy
bindings; a policy bound to the old source must not be reused silently.

## Validated decisions and new source build

Decision preparation completed successfully for all **10 advertisements and 18
attached captures**. Independent full artifact hash verification passed. Decision
manifest: `b1a409ba18a700a25bd9b3ac3b2a5b549a3c7aaeb298a1137aba79f5a4651dea`.
Every decision passed the existing exact-row, typed capture-membership, raw
payload, literal span, address and chronology checks.

The existing reversible source builder has now been launched with these
decisions. Pending output: `data/model/chelsea-location-scope-analysis-20260920`.
It verifies the complete inherited source lineage, exact inverse, unchanged
retained observations, row order and capture-time active population before
publication. This build starts from the original expanded-floor source; it does
not yet include the later 24 direct-description floor additions. Completion,
replay and safe rebinding of those additions remain to be checked.

The separately running direct-floor fit continues on its unchanged source.

The location-scope source build has completed and its full artifact hashes have
been independently verified. Manifest:
`9b4e7acf824b5d1c99b5d3386135ec58da0c22ec38a30a9353f3420fbfe83238`.
It contains **52,643 observations, 22,146 units and 1,127 buildings**, with all
172 capture-time active observations unchanged. Ten exact advertisements are
retained in the quarantine sidecar; the full parent inverse passed.

`rebase_direct_floor_policy` now checks that the sole difference from the nine-ad
source is removal of 2938067, both scope revisions reconstruct the same original
source, all 24 floor-decision rows remain byte-equivalent under canonical
serialization, and all 17 preserved floor-review findings remain unchanged.
Six tests reject price/order/membership changes and verify detached output.
The full policy rebinding is running at
`data/model/chelsea-location-direct-floor-prepared-policy-20260920`; it does not
apply the floor additions. The direct-floor fit has entered retained sampling
on its original frozen inputs.
