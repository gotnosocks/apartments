# Doorman-category overlap: source review

The accepted model associates virtual versus full-time doorman coding with +4.21% asking rent (95% credible interval 3.32% to 5.12%). This is a conditional association; the reviewed overlap does not establish a service premium.

Neither shared unit supplies clean evidence of a physical virtual/full-time doorman transition. One has conflicting unit/location/layout identity; the other combines VIRTUAL structured coding with 24-hour lobby-service prose. No reviewed virtual phrase refers merely to a virtual tour.

The exact 52,711-row source contains four overlapping buildings: 142 full-time and 13 virtual advertisements. Only two source unit IDs occur in both categories. The review selects one pair per building, prioritizing those shared units, then minimizing the advertisement-period gap with deterministic audit-ID tie breaks. All ten captures of the eight selected ads were reviewed and reparsed from their original hashed bodies.

| Building | Full-time ads / units | Virtual ads / units | Reviewed ads | Classification |
| --- | ---: | ---: | --- | --- |
| 210-west-19-street-new_york | 1 / 1 | 7 / 6 | [2458632](https://streeteasy.com/rental/2458632), [2647860](https://streeteasy.com/rental/2647860) | structured_full_time_without_prose_confirmation |
| 220-west-24-street-new_york | 114 / 60 | 1 / 1 | [1797236](https://streeteasy.com/rental/1797236), [2019725](https://streeteasy.com/rental/2019725) | shared_unit_identity_and_location_conflict |
| 410-west-23-street-new_york | 1 / 1 | 2 / 2 | [1434584](https://streeteasy.com/rental/1434584), [2970437](https://streeteasy.com/rental/2970437) | service_transition_or_product_mismatch_unresolved |
| chelsea-green | 26 / 17 | 3 / 3 | [2019657](https://streeteasy.com/rental/2019657), [1420528](https://streeteasy.com/rental/1420528) | possible_staffed_and_virtual_coexistence_or_subtype_misclassification |

**210-west-19-street-new_york** — The only full-time advertisement has structured FULL_TIME, but its description mentions a live-in superintendent accepting packages, without claiming round-the-clock staffed door service. The virtual advertisement explicitly identifies a voice intercom/virtual doorman system and structured VIRTUAL. This may be classification ambiguity, coexistence or a service change; descriptions do not distinguish them. Different source units and historical periods do not identify a within-unit change.

**220-west-24-street-new_york** — The shared #2F identifier contrasts a studio/elevator/doorman ad at structured 220 West 24th Street with a three-bedroom walk-up ad describing The Clarice on West 21st Street, while its structured address says 222 West 24th Street. Virtual modifies a doorman intercom, not a tour, but advertisement-to-physical-unit identity is suspect. Do not interpret this as a verified staffed-to-virtual conversion or infer a replacement address.

**410-west-23-street-new_york** — The earlier studio advertisement explicitly offers 24-hour concierge/doorman and attended parking. The later two-bedroom advertisement explicitly names a Carson virtual doorman and phone intercom. Source units differ, ads are five years apart, and the amenity packages differ markedly. A real service change is possible, but coexistence, copied building prose or mismatched product identity cannot be excluded from these two ads.

**chelsea-green** — The shared #3D has stable one-bedroom/one-bath/700-square-foot measurements. Its earlier structured VIRTUAL ad also has CONCIERGE and describes 24-hour lobby service; the later FULL_TIME ad explicitly describes a 24-hour lobby attendant, superintendent and porter. Earlier prose never mentions a virtual system. The source subtype changes, but the text does not establish that staffing was newly introduced. Virtual access could coexist with staff, or the earlier subtype may be wrong.

Source subtype changes were observed, but **zero physical service transitions were verified**. Coexistence is a plausible hypothesis, not an established fact. None of the reviewed virtual descriptions confused a tour with a doorman system.

Eight deliberately selected advertisements, not an error-rate sample. The model contrast is a conditional association, not willingness to pay or a causal service premium. Only four buildings and two source unit IDs overlap; most information is between units/buildings under the specified priors. Advertisement periods and capture/interpretation clocks do not establish physical effective dates. No source, analytical or model mutations.

Next sensitivity work:
- Adjudicate advertisement2019725 identity and West21st versus structured West24th location without guessing an address.
- Represent staffed attendance and remote/intercom access separately with hours, source tier and conflict status; do not force mutually exclusive labels where services may coexist.
- Review the remaining nine virtual advertisements in overlapping buildings before claiming within-building corroboration.
- After independent adjudication, compare contribution sensitivity with disputed labels masked and with separate staffed/remote indicators; no such sensitivity is completed here.

The immutable bundle retains all 155 overlap row identities, selected full source rows, full descriptions, exact literal offsets, structured addresses/amenities, original raw JSON, body/raw/text hashes, capture clocks and separate interpretation clocks. Source observations SHA-256: `6f4a05b01139d3d094ecaa2a7c305c02cb066e1c236dfe547c663a4d18b49b1f`.

Artifact: `data/model/chelsea-doorman-overlap-source-review-20260918`.
