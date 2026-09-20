# Explicit floor extraction: three missed own-advertisement claims

All three misses are **grammar exclusions**, not failed case conversion or
photo/amenity suppression. The sole description-floor pattern in
`src/apartments/attribute_evidence.py` requires a dwelling noun followed by
“on … floor”, approximately:

```text
(this apartment|this unit|this home|the apartment|apartment|unit|residence)
[is [located|situated]|located|situated] on [the] NUMBER[ordinal] floor
```

It already uses case-insensitive matching. I reread the complete descriptions
and replayed all six bound captures through `attribute-evidence-v6` using their
full description strings. Each yields **zero floor-regex matches, zero floor
evidence items, no withholding warning, and `advertised_floor=None`**. Consequently,
the scanner's scope and negation checks never see these claims.

| Advertisement / captures | Exact phrase and character span | Missing grammar | In-memory diagnostic control |
|---|---|---|---|
| 5047403 / 6712, 10931 | `53RD FLOOR` `[10,20)` | Bare floor clause in the opening `3ELEVEN - …` headline; no dwelling noun or “on”. | Replacing only that phrase with `This apartment is on the 53rd floor` recovers 53. |
| 4729493 / 33224, 93213 | `3rd floor of a walkup building` `[69,99)` | Standalone apartment-location line; starts with the ordinal. | Adding `This apartment is on the` immediately before the phrase recovers 3. |
| 942756 / 19956, 61345 | `this 11th floor` `[216,231)` | Elided dwelling noun: the floor itself is described as having a 35-foot-wide great room. | Replacing only that phrase with `this apartment is on the 11th floor` recovers 11. |

Controls retain the rest of each complete description unchanged. They diagnose
the existing scanner; they are synthetic wording experiments, not source edits,
new evidence or implemented extraction rules. Description-only replay does not
assert anything about unexamined structured fields. The current label projection
already gives these observations the same floors 53, 3 and 11.

## Proposed narrow changes

Add separately named floor grammars rather than replacing the current pattern
with an unrestricted ordinal-floor search:

1. **Opening headline floor clause.** Consider an ordinal followed immediately
   by “floor” and a clause terminator in the first nonempty logical line, allowing
   a preceding listing/building title and dash. Require a unit-oriented headline
   context; reject media, model-unit and shared-amenity contexts. Capital letters
   alone are not evidence of unit scope. This would cover the actual 53rd-floor
   headline while leaving the later 42nd-floor sky-deck sentence unselected.
2. **Standalone ordinal walk-up location.** Recognize a complete clause of the
   form `NUMBER-ordinal floor of a/the walkup/walk-up/walk up building` in the
   apartment-description section. Do not turn “walk up two floors” into floor 3.
   The actual preceding line says “see video of actual unit”, which should not
   suppress the subsequent own-unit claim.
3. **Elided floor-as-residence clause.** Recognize `this NUMBER-ordinal floor has
   … great/living room` only when the paragraph establishes the offered dwelling
   as its subject, and the clause describes private residential space. Preserve
   the full supporting clause and context. Do not infer unit scope from the word
   “this” or “great room” alone; common-floor facilities and model residences
   remain exclusions. The actual HL23 paragraph introduces the offered condo and
   then describes its great room, kitchen and primary suite.

All three should feed the existing assertion/conflict mechanism, retain exact
`/description` offsets and their rule identities, and populate only advertised
floor. They must not fill physical floor or floors above ground. Existing
structured/prose conflicts must remain unresolved rather than being settled by
label agreement.

Two scope details need explicit treatment during implementation. First,
`_reference_floor_claim` currently returns false immediately when a match begins
with `this`; that is not sufficient protection for newly admitted `this 11th
floor …` clauses. Second, its reference-media check expects media language to
lead directly into the matched dwelling noun. A bare ordinal line following
`Photos:` or `Model apartment:` lacks that noun and may cross a newline. The new
grammars need local role/context checks rather than assuming the old helper covers
them. Shared-amenity headings must likewise persist across relevant lines.

Avoid a blanket description-wide photography exclusion: the genuine 53rd-floor
headline coexists with a later representative-images disclaimer. Preserve raw
character positions when handling CRLF, HTML `<br>` separators and Unicode;
normalizing text without an offset map would invalidate literal evidence.

## Regression cases required before implementation is accepted

These are proposed expectations, not a claim that new tests or rules have been
implemented. Each positive fixture should use the complete bound description,
not just its isolated phrase.

| Case | Required result |
|---|---|
| All six captured descriptions above | One deduplicated advertised-floor assertion per actual claim: 53, 3 or 11; exact literal spans. |
| Actual 53rd-floor headline plus its 42nd-floor sky deck and later representative-images disclaimer | 53 only; neither a false 42 conflict nor blanket withholding. |
| Actual `see video of actual unit` line followed by the walk-up location | 3; distinguish own-unit media from example media. |
| `Photos: 3rd floor of a walkup building.` and the same wording split over two lines | Unknown; an image location is not the offered dwelling's floor. |
| `Model apartment — 53RD FLOOR!` | Unknown despite headline shape and capitals. |
| `BUILDING AMENITIES: 42ND FLOOR! SKY DECK` and equivalent multiline form | Unknown; protect both heading and clause scope. |
| `This 11th floor gym has a great room.` | Unknown; not an apartment-floor claim. |
| `This 11th floor model apartment has a great room.` | Unknown; “this” must not bypass reference-unit scope. |
| `This 11th floor has a shared lounge.` | Unknown; residential-sounding space is insufficient. |
| `Not the 3rd floor of a walkup building.` / a hypothetical future floor | Unknown; preserve negation and uncertainty. |
| Existing photo-reference sentence followed by `This apartment is on the 8th floor.` | 8 only; preserve the v6 reference-photo repair. |
| Structured listed floor 8 plus a newly supported explicit floor-3 claim | Advertised floor null, retain both assertions/conflict; physical fields unchanged. |
| `Two floors up`, `PH405`, `14-story building`, `11-foot windows` | No newly inferred numeric advertised floor from these descriptions alone. |
| Exact positive fixtures with CRLF/HTML separators and unrelated Unicode before the claim | Same value with offsets indexing the original input string exactly. |

Also rerun the existing reference-photo, real-unit-with-nearby-media, negation,
structured-floor conflict and shared-amenity regressions. Before promotion, audit
the entire captured corpus of *newly matched* claims, especially disagreements
with existing explicit floors, and publish a new versioned interpretation. These
three cases motivate coverage work; they do not measure precision of the broader
rule or justify rewriting frozen datasets.

## Evidence bindings

- Extractor inspected: `attribute-evidence-v6`, SHA-256
  `4fbc1b5b7f15061206d708ad8775190dd4bf9f3930fe072422a75b4ba0c3789a`.
- Source-panel manifest:
  `90a36b6f0bbde3a7cb3e0b2a2e327fb89fd00132adab420476e64feabff6f0bd`.
- Source-panel records:
  `4968ae1322b08a144f3dc20a75e6c0469f72e507f83976837c8aac55c32dc283`.
- Description SHA-256, 5047403:
  `3a01b26ce3d57ddb86aa9a7081de1fecb3e5c01c5617ae4758463307eb1e6880`.
- Description SHA-256, 4729493:
  `7be1791cbbd38c441201b077bd7da6c75327231c3431cff5234215baa088b4e5`.
- Description SHA-256, 942756:
  `bd3baf8dd9880a89bc6c82a230257cffaca2f44fa5c198e2aec401231b4df3b8`.

Complete capture/label witnesses remain in
`data/model/chelsea-expanded-floor-source-panel-20260919/panel.jsonl`.
This investigation changed only this findings document. No scraper, extractor,
test, data artifact, model or UI dependency was modified.
