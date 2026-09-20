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
