# Canonical StreetEasy apartment-floor audit

The internal field name is not a requirement. Apartment-floor information from
StreetEasy should be normalized from its actual source field and retain its
original path and literal. The model already accepts `advertised_floor` as the
listed-floor input; checking only a literal `listed_floor` key would misstate
coverage.

An offline audit inspected **71,906 verified own-listing payloads** supporting the
cleaned 52,704-row cohort: 71,893 historical captures and all 13 current captures.
It checked structured keys recursively, rather than requiring `floor` or
`listedFloor`. There were **no floor/storey/story/level-like structured keys** in
the audited own-listing scope. The property-details objects consistently contain
address, amenities, bedroom/full-bath/half-bath counts, features, living/lot area
and room count. This describes the captured payloads, not every field StreetEasy
might expose through another page or interface.

A second audit expanded the scope to **all decoded Flight records and inline
JSON in the 13 current raw pages**. Each page exposes `building.floorCount` and
a building-summary `floorsCount`; the two values agree on every page. Their
parent objects describe the building (including unit inventory and year built),
so these are building story counts, not apartment-floor labels. No structured
apartment-floor key was found in this expanded current-page scope. `floorPlans`
is media, and the broad key screen also matches irrelevant history keys through
the substring `story`. The paths, parent keys, values and raw-body hashes are
preserved in `data/model/chelsea-current-page-floor-key-audit-20260918`.

The audit excludes `latestListing` and `propertyHistory` from own-advertisement
attributes, and excludes media/floorplans from apartment-floor labels. Building
floor counts and unit-label inference are separate concepts. Every selected raw
listing was matched to the hash and identity in the verified description archive;
historical Parquet shards were checked against the bound source inventory, and
current bodies were decompressed, hashed and reparsed.

There are 364 modeled observations with a known floor after normalization.
A broad ordinal-floor description screen found 10,260 captures with a phrase;
9,756 of those captures belong to observations whose modeled floor is unknown.
These are **capture counts, not distinct units or newly established floors**.
The initial examples include common sky decks, shared roof terraces and a tower
whose residences start at floor 26. Those cannot be assigned as individual
apartment floors. Broader description extraction needs a stratified source review
and explicit handling of unit scope, ordinal words and multi-level apartments.

Artifact: `data/model/chelsea-canonical-floor-field-audit-20260918`. It contains
`review.json`, a complete verified capture inventory, structured candidates
(empty), bounded literal description-screen examples and the frozen audit script.
No source values were patched and the running source fit remains bound to its
original inputs.
