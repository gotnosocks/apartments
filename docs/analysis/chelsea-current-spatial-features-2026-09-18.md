# Spatial feature candidates from captured building evidence

All **172 current listings / 85 buildings** have usable coordinates in their
captured building objects. The unit's own property-details object does not supply
these coordinates. Each coordinate was accepted only after matching the listing's
`buildingId` and the canonical unit URL's building slug to the containing building
object. Repeated building objects, direct latitude/longitude fields and `geoCenter`
must agree. All current captures of each building also agree.

The research artifact provides raw latitude/longitude and relative coordinates
centered on the equally weighted 85 observed buildings. The center is
**40.7453106, −73.9990391647**. Relative values remain degrees; they are not distances
or offsets from a geographic NYC centroid. No external geocoding was requested.

Simple address parsing yields **22 candidate street labels**. It removes only a
leading house number and normalizes case/whitespace; it does not invent alias
equivalence between names such as “7th Avenue” and “Seventh Avenue.” The literal
building address and own-listing address are retained separately. These labels
describe the building address, not a unit's street-facing windows or views.

The central modeling limitation is explicit: these features are constant within
building. Coordinate columns and street indicators lie in the span of building
indicators. Separating a location contribution from the building offset therefore
depends on structural and prior assumptions; there is no within-building location
contrast in this data. A spatial experiment should examine changes in building
offsets and residual patterns under matched priors, rather than interpreting a
coordinate coefficient as an independently identified neighborhood premium.

Artifact: `data/model/chelsea-current-spatial-candidates-20260918`, with every
capture's raw-body/listing hash, matched building ID, source path and source clock,
plus the building-level feature candidates and frozen code. Eight tests cover
binding to the correct building, conflicting coordinate channels/objects, literal
street parsing and equal-building centering. No model input or fit has changed.
