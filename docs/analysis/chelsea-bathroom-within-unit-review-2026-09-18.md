# Are within-unit bathroom changes useful identifying variation?

**The eight reviewed units do not yet provide clean physical bathroom-change evidence.** Three have explicit disagreement between structured counts and the same advertisement's description; a fourth is strongly suspect. Two might reflect real reconfiguration, while two remain unresolved. None establishes an independently verified physical change or its effective date.

The useful signal at this stage is which measurements and unit identities need review. These findings support source adjudication before treating all 418 composition-varying units as strong evidence for within-unit bathroom pricing effects. They do not establish an error rate for those 418 units.

## Selection and evidence

The reviewed source is exactly the 52,711-row dataset used by the current long Bayesian experiment. Units were chosen deterministically, without looking at fitted prices or residuals:

- Four common one↔two-full-bath transitions with no half baths and unchanged bedroom count, from 84 eligible units.
- Two changes in half-bath count while full baths stay constant, from 136 eligible units.
- Two full-bath jumps of at least two, from eight eligible units.

Within each stratum, units were ordered by a fixed SHA-256 key; the earliest qualifying adjacent known-advertisement transition was selected. No unit appears twice. This deliberately stratified development sample is not representative of all bathroom changes.

I read all available descriptions in the eight unit histories: 34 advertisements and 42 archived captures. The immutable selection contains full source records, original structured full/half fields and descriptions. Findings preserve listing IDs, price periods, capture and interpretation clocks, raw/body/description hashes, and exact highlighted text spans.

## Findings

| Unit | Selected source transition | Assessment |
| --- | --- | --- |
| 305 West 20th #3 | [4003192](https://streeteasy.com/rental/4003192), 2022-11: 2 full → [4304747](https://streeteasy.com/rental/4304747), 2023-12: 1 full | Unresolved. Both descriptions contain only address text; a later ad returns to two baths and changes bedroom count. |
| 316 West 19th #1RE | [1406103](https://streeteasy.com/rental/1406103), 2014-10: 1 full → [1832712](https://streeteasy.com/rental/1832712), 2016-07: 2 full | Explicit conflict: the earlier one-bath record's description already advertises **two full baths**. The apparent addition is not credible change evidence. |
| Chelsea House #7C | [2185821](https://streeteasy.com/rental/2185821), 2017-08: 2 full → [2936893](https://streeteasy.com/rental/2936893), 2019-12: 1 full | Explicit conflict: the later description says two full baths and a full second bath. Other inspected ads also describe two baths. |
| 252 West 30th #2B | [1964913](https://streeteasy.com/rental/1964913), 2016-12: 1 full → [5064467](https://streeteasy.com/rental/5064467), 2026-06: 2 full | Possible reconfiguration. Older sources describe the master bath; the later ad explicitly describes an additional full bath and different finishes. Earlier omission does not prove that bath was absent. |
| 139 West 14th #5F | [3027129](https://streeteasy.com/rental/3027129), 2020-04: 1 full + 1 half → [3516319](https://streeteasy.com/rental/3516319), 2021-05: 1 full | Explicit conflict: both descriptions say one and a half baths. The later ad also contains contradictory second-floor/ground-floor claims and obfuscated net-effective-rent wording. |
| 406 West 22nd #1R | [2059087](https://streeteasy.com/rental/2059087), 2017-04: 1 full + 1 half → [2461870](https://streeteasy.com/rental/2461870), 2018-07: 1 full | Unresolved premises identity. The first ad is a two-bedroom private-garden duplex; the next and later ads are studios. Subdivision, reconfiguration or a unit-label collision remain possible. |
| 146 West 17th #3A | [3856481](https://streeteasy.com/rental/3856481), 2022-05: 1 full → [4441673](https://streeteasy.com/rental/4441673), 2024-06: 3 full | Strongly suspect count change: the studio retains essentially identical prose describing its singular bathroom. Singular wording alone does not prove an exact count. Earlier history also switches between a three-bedroom and a studio one month apart. |
| 244 West 22nd #5D | [3383001](https://streeteasy.com/rental/3383001), 2021-01: 1 full → [4034212](https://streeteasy.com/rental/4034212), 2023-02: 3 full | Possible bundled reconfiguration or premises change: two bedrooms become five and the later ad claims gut renovation. Repeated later descriptions support five bedrooms/three baths, but the same physical footprint is unverified. |

The two possible reconfiguration cases require independently dated, unit-specific layout evidence. Even if confirmed, their changes involve more than bathrooms: kitchen/bath finishes, bedroom count, footprint or other renovation work may also change. Their rent differences should not be attributed to bathroom additions alone.

The 139 West 14th case additionally requires price-basis review. Its captured description says “Rent is N3t 3ff3ctive.” This review does not infer a replacement asking price or determine which historical price event the term applies to.

## Time and identity limitations

The selected transitions are ordered by advertisement price periods. Source captures were collected much later, in September 2026; their clocks are retained as collection/knowledge evidence. **A capture date is never assigned as a physical bathroom-change date.** Likewise, a common canonical unit URL is source identity evidence, not proof of unchanged physical premises.

No raw data, analytical rows, bathroom flags or model estimates were patched in this task. The three explicit conflicts should enter the separate source-review workflow; the suspected studio case needs corroboration before any numeric correction. The possible reconfigurations and identity cases should remain uncertain until stronger evidence is available.

## Reproducibility

- Exact source observations SHA-256: `6f4a05b01139d3d094ecaa2a7c305c02cb066e1c236dfe547c663a4d18b49b1f`.
- Source dataset: `data/model/chelsea-reviewed-bathroom-projection-20260918`.
- Verified description archive: `data/model/chelsea-analysis-descriptions-20260918`.
- Verified structured-count audit: `data/model/chelsea-bathroom-evidence-20260918`.
- Selection and complete source histories: `data/model/chelsea-bathroom-within-unit-review-selection-20260918`.
- Classified findings and text spans: `data/model/chelsea-bathroom-within-unit-source-review-20260918`.

Both output bundles contain their exact publication scripts and verified input manifests. Identical replays verify and reuse the artifacts. The computation checks source ancestry, advertisement/unit identity, capture membership, description hashes and quoted offsets.
