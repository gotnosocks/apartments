# Draft doorman-service measurement policy

The follow-up reviewed the remaining **nine virtual-labeled advertisements and all 15 captures**, completing all 13 virtual ads in the four overlapping buildings. The prior review covered four full-time ads as well. Full descriptions, original body/raw hashes, structured amenities/addresses, literal spans and capture/interpretation clocks are preserved in `data/model/chelsea-doorman-measurement-review-20260918-v2`. Its `measurement-policy.json` is a proposal, not an implemented extractor or model feature.

The additional evidence changes the next source review:

- [2120944](https://streeteasy.com/rental/2120944) and [2128598](https://streeteasy.com/rental/2128598) describe 16th Street near Fifth Avenue while original structured addresses say 210 West 19th Street. Add both to identity/location adjudication alongside the previously identified [2019725](https://streeteasy.com/rental/2019725). Do not assign inferred addresses.
- [1453994](https://streeteasy.com/rental/1453994) explicitly advertises a **24-hour attended lobby**, while structured fields say `VIRTUAL` and `CONCIERGE`. Preserve both claims: services may coexist or subtype coding may be wrong. Neither explanation is verified.
- [5127535](https://streeteasy.com/rental/5127535) has only a period as its description. Structured virtual/concierge/resident-staff claims remain source evidence; staffed attendance and hours remain unknown.
- Other ads distinguish virtual access, live-in staff, package receipt and storage. [5099983](https://streeteasy.com/rental/5099983) explicitly says its superintendent accepts packages. Repeated Butterfly wording in [4076390](https://streeteasy.com/rental/4076390) and [4381621](https://streeteasy.com/rental/4381621) supports persistence of a reported service, without dating installation.

Record service dimensions independently so staffed and remote services can coexist:

| Dimension | Preserve | Do not infer |
| --- | --- | --- |
| Staffed lobby attendance | Explicit attendance claim and scoped hours | Concierge or resident staff means 24-hour attendance |
| Virtual service label | Literal label and vendor wording | Human remote operator or absence of onsite staff |
| Intercom / remote human operator | Separate explicit claims | Vendor name establishes functionality |
| Concierge / resident staff | Role and source tier | Delivery mode or attendance hours |
| Staff package receipt / package room | Separate service and facility claims | Storage room implies staff receipt |
| Video security | Explicit security claim | Human monitoring or its hours |

Each dimension needs **reported present, explicitly absent, unknown, or conflicting** status. Unmentioned text and missing/empty amenity lists are unknown. Keep structured and prose evidence separately; coexisting staffed and virtual claims are not automatically contradictory. These nine ads contain no explicit service-absence claims.

Bind hours to the named service. “Full-time” remains unquantified without a schedule; “24-hour attended lobby” supports reported daily coverage while days per week remain unknown. Preserve advertisement period, capture clock and interpretation clock separately. Physical effective dates remain unknown without explicit evidence. No physical service transition was verified.

After identity adjudication, test sensitivity to masking uncertain labels and to separate staffed/remote features. Those checks have **not** been completed. The review is purposive, not an error-rate sample, and supports no causal premium. No scraping, patches, frozen-model changes or fits were performed.
