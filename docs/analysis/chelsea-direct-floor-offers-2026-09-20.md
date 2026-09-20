# Explicit dwelling-floor wording from residual review

Attribute evidence v8 adds two bounded description rules prompted by the
residual movement review:

- Advertisement 3967693 starts `FLOOR TWO, UNIT ONE`. The explicit floor is 2;
  the unit label supplies no floor number.
- Advertisement 776029 says `This first floor walk-up apartment`. The explicit
  advertised floor is 1, without inferring physical elevation.

The new rules accept a leading floor/unit headline using cardinal words one
through twenty, or “this” plus an ordinal floor and dwelling noun, optionally
with “walk-up.” They reject reference-media, shared-space, hypothetical and
negative language in the surrounding sentence. Wrapped lines do not reset
that sentence scope. Literal source spans and the rule identifier are retained.
Conflicting structured floor values remain visible as conflicts rather than
being overwritten.

All 163 focused attribute/named-floor/direct-floor tests pass. The fixtures
preserve complete, hash-checked own descriptions for both reviewed ads (three
captures), including later virtual-staging language on 3967693. Tests also
cover reference claims, questions, hypothetical offers, shared amenities,
independent unit labels, exact spans and structured/text disagreement.

The full description-only v7-to-v8 replay has been launched with
`docs/analysis/scripts/audit_direct_floor_offers.py`. It checks every archived
description, verifies source/capture identities, and requires every nonfloor
attribute, evidence item, warning and conflict to remain unchanged. It preserves
all changed captures for manual review. Output is planned at
`data/model/chelsea-direct-floor-offer-replay-20260920`; results are pending.

This is an extraction improvement under evaluation, not an applied source
projection. The running PyMC fit's frozen input is unchanged. Additional matches
and any source conflicts require review before claiming a coverage increase or
fitting a source revision. Historical effective dates and physical floors remain
separate questions.
