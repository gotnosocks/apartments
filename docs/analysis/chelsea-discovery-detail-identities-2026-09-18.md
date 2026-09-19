# Discovery detail identities: nine unresolved canonical links

All nine advertisement-only links in the September 18 discovery queue returned
HTTP 200 and source-reported ACTIVE listings. Their detail-page canonical links
still name advertisements rather than units. They therefore remain outside the
204 successfully projected candidates; an HTTP success is not an identity check.

An offline review joins only the listing's own rental-history IDs to verified
historical canonical-unit memberships. Sale histories are excluded. Unit-label
matches are retained separately as corroboration, without inventing unit URLs.

- Advertisement **5156276**, One High Line #W15E: rental history 4484104 maps to
  the existing `/building/one-high-line/w15e` unit, agreeing with the display label.
  This is a candidate historical association, not an automatically accepted merge.
- Advertisement **5021142**, 147 West 22nd Street #2: history maps to both
  `/building/147-west-22-street-new_york/2nd-floor` and `/building/147-west-22-street-new_york/2`.
  The label supports the latter; the two historical identities require alias review.
- The other **seven** have neither an associated historical unit nor an exact
  existing canonical-unit label match: 5047355, 5100372, 5121898, 5131634,
  5148766, 5149364 and 5160185. Lack of a match does not prove a new physical unit.

Any accepted association needs a versioned identity policy preserving the raw
canonical advertisement URL, supporting source evidence and knowledge clock.
No identity merges, source corrections or analytical inclusions were made here.

Evidence: `data/model/chelsea-discovery-detail-identity-review-20260918`, containing
all nine reviews, verified historical-shard hashes and frozen code. Six tests cover
rental versus sale history, label-only evidence, conflicting units/buildings,
unresolved history and wrong-advertisement rejection.

The companion `data/model/chelsea-discovery-detail-completion-review-20260918`
verifies all 213 captures and reports 168 eligible canonical candidates. It is a
coverage and eligibility review, not a new model dataset or a market census.
