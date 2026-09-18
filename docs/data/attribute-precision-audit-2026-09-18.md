# Description attribute precision audit, 2026-09-18

An independent Codex-agent review examined 90 literal extracted assertions across
floor, elevator, laundry, doorman, HVAC, pets, views and window exposures. Inputs
came from `data/exports/attribute-audit-20260918/description-evidence-sample.jsonl`.
Up to twelve examples per attribute family were chosen by deterministic hash order
after deduplicating identical full-description/attribute/value tuples. Repeated
building boilerplate remains represented.

These are **agent judgments about source text**, not human ground truth or checks
of physical apartments. The existing convenience sample oversamples extracted
positive evidence; neither population precision nor recall can be estimated from
these counts.

The review found 84 directly supported assertions, one unsupported unit-view
assertion, two ambiguous HVAC descriptions, and three pet-policy assertions whose
specific approval requirement had been lost. Fourteen reviewed records also
contained notes about additional missed evidence. The audited descriptions,
per-assertion rationales, excerpts, snapshot/listing IDs and hashes are saved in
`data/exports/attribute-precision-audit-20260918/selected.jsonl`, `labels.jsonl`,
and `summary.json`.

Concrete changes in `attribute-evidence-v2`:

- Snapshot 1898 attributed a community terrace's skyline view to the apartment.
  Common-area headings now retain scope across newlines and HTML breaks; an
  explicit apartment-feature heading restores unit scope.
- Snapshots 1379 and 1400 describe “CENTRAL A/C Wall Mounted Split Unit.” The
  extractor retains the literal evidence and an ambiguity warning, and leaves
  HVAC type unknown instead of asserting a precise central system.
- Coordinated phrases such as “Northern and Eastern exposure,” “South/West
  exposure,” and “windows facing north, south and west” now preserve every named
  direction, with other directions unknown. Negation and common-area scope still
  apply to the whole phrase.
- Hyphenated “no-pets” is recognized, and case-by-case/board approval is preserved
  as `approval_required` instead of generic pet permission.
- Explicit “in unit stacked washer/dryer” is recognized; installation or connection
  wording remains insufficient to establish installed equipment.

All 90 selected assertions match the revised description-only expectations,
including the deliberate unknowns and pet-policy refinements. This is a regression
check against the audit labels, not an independent validation result. The production
extractor also considers structured source assertions, which can create separately
recorded conflicts. Narrow-pattern omissions remain, including “laundry in the
basement”; this audit does not claim exhaustive feature recovery.

Validation: 53 tests passed across attribute extraction, historical dataset
construction, and dated analytical transformation. Six added test cases exercise
source-grounded failures, coordinated negation, section transitions, literal
offsets, ambiguous equipment, and installation qualifiers. The historical dataset
must be rebuilt under the new extractor version and implementation hash before a
new amenity comparison; previous published datasets remain immutable.
