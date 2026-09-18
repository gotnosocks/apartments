# Chelsea: outdoor access measurement and independent source review

The new occurrence-level measurement separates explicit private wording,
apartment access, shared facilities, views, negative claims, planned claims and
unresolved mentions. It improves several errors found in changed residuals, but
**independent source review does not support promoting it into model inputs**.
The main analysis model and the two prior outdoor experiments remain unchanged.

The [outdoor model comparison](chelsea-outdoor-model-2026-09-18.md) showed that
feature contributions were sensitive to evidence policy. This follow-up examines
the measurement problem before attributing additional price variation to those
features. No further fits, source-price edits or cohort exclusions were made.

## What the measurement preserves

`models.outdoor_scope_audit` binds the same 52,712 analytical observations to the
verified outdoor capture inventory. It publishes a measurement/review bundle,
not an analytical dataset for fitting. Each mention retains exact source offsets,
literal context, capture and body hashes, original clocks, classification rule,
scope and subject. Matching structured assertions are a separate evidence field;
text claims no longer require a corresponding structured code.

Private and shared occurrences of the same type may coexist. Apartment access
does not establish exclusivity. A generic deck is not silently converted to a
roof deck, and a yard is not silently converted to a garden. Views are retained
without asserting access. Proper-name matches such as Hudson Yards and London
Terrace remain non-amenity evidence. Explicit negative statements stay review
claims; missing or unresolved mentions never imply physical absence.

The first grammar is frozen in `apartments.outdoor_scope`; the revised grammar is
`apartments.outdoor_scope_v2`. Their source snapshots and hashes accompany the
respective evaluation artifacts. The revised grammar fixes courtyard-view
misclassification, orientation wording such as south-facing private terraces,
some room-to-outdoor access relations, and viewer/feature-owner confusion.

## Coverage is not validated feature prevalence

| Claim scope | Rows | Distinct units | Buildings |
| --- | ---: | ---: | ---: |
| Explicit private wording | 5,444 | 2,755 | 507 |
| Apartment-access wording | 922 | 580 | 243 |
| Shared wording/scope | 7,402 | 3,598 | 284 |
| View relation | 2,762 | 1,610 | 336 |

These groups overlap. There are also 409 rows with planned claims, 41 with
negative claims and 17,119 with unresolved mentions. The grammar records 170
rows with both private and shared mentions of the same type and two rows with
positive and negative claims of the same type.

Most private wording has an unresolved grammatical subject: 4,705 rows have at
least one such occurrence, while 1,088 have an explicitly identified apartment
subject. A phrase such as private garden can describe a building facility.
Consequently the 5,444-row coverage figure is not a count of apartments with
verified private outdoor space. Some subject and scope classifications also
disagree; this remains review evidence rather than a reconciled physical state.

## Development versus independent evaluation

A separate agent selected and read 40 distinct units, eight per lexical stratum:
private wording, apartment access without private wording, shared wording,
garden views and mixed private/shared descriptions. Those units do not overlap
112 previously reviewed units. The 97 mention annotations were prepared before
the agent saw extractor output.

The initial grammar agreed with 52 of 97 exact mention-scope labels. That sample
then guided revisions, including the courtyard-view fix. The revised grammar
agreed with 80 of 97 labels. All 25 matched mentions it classified as private or
apartment access had one of those two source labels. These are **development
results**, not independent accuracy estimates. Seven additional extracted
mentions were outside the annotation inventory, including one private claim.

After the revised grammar was frozen, the agent labeled a second sample of 25
units, five per stratum, excluding all 152 previously reviewed units. The agent
did not consult revised code or outputs. This sample has 58 annotations, with
six ambiguous and 14 context-dependent labels explicitly flagged.

| Frozen revised grammar, second sample | Result |
| --- | ---: |
| Exact mention-scope agreement | 33 / 58 |
| Private labels classified private | 9 / 10 |
| Apartment-access labels classified access | 0 / 4 |
| View labels classified view | 8 / 11 |
| Shared labels classified shared | 10 / 25 |
| Matched private/access predictions with private/access labels | 9 / 11 |
| Labeled spans without an exact extractor span | 2 |
| Additional extracted mentions outside label inventory | 5 |

The two questionable private predictions both concern a building's private
garden entry. The missed apartment-access claims include a balcony opening to
the kitchen, an invitation to step onto the apartment's balcony, a concise
one-bedroom-with-balcony title and a long coordinated feature list. Four shared
mentions were called planned because ordinary future-tenant wording says
residents will have access. The two span mismatches include a decked surface and
a sun-deck span; exact-span disagreement is not automatically a semantic error.

These samples were selected to contain difficult wording, repeat some building
templates, and use agent judgments rather than independent physical ground
truth. The second sample contains no negative/planned labels. It cannot establish
population precision, recall, or correctness for those two classes. Its failure
to confirm access-claim coverage is sufficient to hold the proposed encoding.

The original annotations remain immutable. An adjudication addendum distinguishes
local mention evidence from document coreference and notes genuine ambiguity:
private wording under a building heading blocks secure apartment attribution but
does not necessarily prove shared use. A garden-paradise title may require later
doorway/stairs wording to establish access. These are separate from definite
implementation errors, such as confusing a courtyard view with access.

## Two apparent contradictions and three coexistence cases

The source follow-up reviews both positive/negative rows and three deterministically
selected private/shared rows:

- **1445338:** a private terrace is temporarily inaccessible during façade work.
  One parenthetical closure statement is missed, while another sentence generates
  a negative claim. Physical amenity and current access status need separate
  representations. An archive capture date does not establish closure dates.
- **5083189:** not including the 800-square-foot deck refers to the apartment's
  1,600-square-foot interior measurement. It does not deny access. Treating this
  as a negative amenity claim is an extraction error.
- **2195748:** the apartment has a private terrace and the building has a common
  rooftop terrace. Keeping separate occurrences avoids the old global veto.
- **4165484:** apartment terraces coexist with a building garden. A later private
  garden sentence needs document context to preserve its building subject.
- **4823202:** a common residents' garden is also described as a private garden
  of a landmarked building. The modified building subject is missed. Here the
  overlap is partly a scope error, not proof of two different gardens.

The next useful step is a source-claim representation that jointly resolves
subject, access relation, exclusivity and temporary availability, with evidence
confidence and unresolved cases preserved. Adding more isolated phrase rules
has not yet demonstrated reliable generalization. Any replacement must be
checked on new units before repeating the matched contribution experiment.
Outdoor area also needs measurement exclusions, bounds and private/shared scope
before it becomes a numeric input.

## Artifacts and reproducibility

- First labels: `data/model/chelsea-outdoor-scope-validation-20260918`.
- Initial evaluation: `data/model/chelsea-outdoor-scope-first-evaluation-20260918`.
- Revised development evaluation: `data/model/chelsea-outdoor-scope-revised-evaluation-20260918`.
- [Independent labels and adjudication](../../data/model/chelsea-outdoor-scope-holdout-20260918/review.json).
- [Independent evaluation](../../data/model/chelsea-outdoor-scope-holdout-evaluation-20260918/summary.json).
- Full-cohort measurements: `data/model/chelsea-outdoor-scope-measurements-20260918`.
- [Five source follow-ups](../../data/model/chelsea-outdoor-scope-followup-20260918/review.json).

All source selection used archived evidence; no new scraping was needed.
Measurement and evaluation replay preserve exact results. Source descriptions,
annotation spans, analytical membership, capture identity and knowledge clocks
are checked. The full suite passed **811 tests, with two skipped**. Test success
establishes the code contracts and listed regression cases; it does not override
the independent source-evaluation limitations above.

```sh
.venv/bin/python -m models.outdoor_scope_audit \
  --dataset data/model/chelsea-outdoor-projection-20260918 \
  --evidence data/model/chelsea-outdoor-evidence-20260918 \
  --output data/model/chelsea-outdoor-scope-measurements-20260918

.venv/bin/python -m models.outdoor_scope_evaluation_v2 \
  --review data/model/chelsea-outdoor-scope-holdout-20260918 \
  --output data/model/chelsea-outdoor-scope-holdout-evaluation-20260918
```
