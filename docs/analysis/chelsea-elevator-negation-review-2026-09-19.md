# Elevator negation source review

An extraction error converted “non-elevator building” into a positive elevator
claim. Reviewing the revised Chelsea cohort's 43 buildings with opposing
elevator reports exposed the error; checking the full description archive found
109 affected captures attached to 98 retained historical observations. Replaying
their original structured payloads supports **96 negative claims and two
unknowns because the structured amenity code contradicts the description**.

The observations represent 32 units in six buildings. Repeated advertisements
and repeated marketing copy are not independent physical evidence. No current
listing is affected, and this review does not resolve all 43 building conflicts.
Other inspected minority claims explicitly describe elevator buildings or
walk-ups, while some have only structured evidence. Neither a majority vote nor
an assumed installation/removal date adjudicates those cases.

| Building | Historical observations | Units | Structured/text conflict masks |
| --- | ---: | ---: | ---: |
| 120 West 20th Street | 1 | 1 | 1 |
| 120 West 25th Street | 36 | 13 | 1 |
| 124 West 25th Street | 33 | 9 | 0 |
| 126 West 25th Street | 25 | 7 | 0 |
| 259 West 19th Street | 2 | 1 | 0 |
| 266 West 22nd Street | 1 | 1 | 0 |

The 259 West 19th Street cases are advertisements 4417318 and 4931353;
266 West 22nd Street is advertisement 5118079. The two conflicted advertisements
are 2061471 and 3027101, covering three captures. Their `ELEVATOR` amenity codes
remain in the evidence alongside the literal negative claims. They are masked,
not declared to have or lack an elevator.

## Extraction and evidence

`attribute-evidence-v5` recognizes the adjacent `non` prefix with a space or
hyphen/dash, including a space after the hyphen. Literal evidence spans retain
the denial. A structured positive assertion plus a text denial resolves to
unknown. Unrelated uses such as “non-smoking building with an elevator” remain
positive; a double negation such as “not a non-elevator building” is withheld.
All other attributes and assertions must be unchanged in the replay.

The final replay is
`data/model/chelsea-elevator-negation-replay-final-20260919`. It verifies the
analytical source and description manifests, capture membership, historical
Parquet shard hashes, original listing JSON hashes, advertisement identities,
and literal description spans. It uses original structured payloads with the
source-bound recovered description text. Every attached capture of each selected
observation is included, including any without the triggering phrase. Here all
109 attached captures contain it, and all 109 elevator outputs change. The
frozen v4 extractor and final v5 implementation are archived with the evidence.

I inspected the distinct literal denial contexts across all 109 captures and
both structured/text conflict cases. The many West 25th Street advertisements
reuse essentially the same parenthetical building description. This is a
targeted regression review, not an independent accuracy estimate for elevator
extraction or verification of physical building access.

## Reviewed patches and model status

The append-only ledger is
`config/reviews/chelsea-elevator-negation-20260919.jsonl`: 98 dated edits, each
targeting an exact analytical row hash and advertisement. Each tests the old
positive value before replacing it with false or unknown. The all-time validity
applies only to that exact row version; it does not propagate to other units,
advertisements, dates or buildings. `recorded_at` dates the correction knowledge,
not a physical change in facilities.

`data/model/chelsea-elevator-reviewed-correction-preview-20260919` records the
verified dry-run result and ledger. Each edit matches one row and changes only
the elevator field. Re-running the review script reuses the existing ledger and
identical preview without appending duplicates. The source datasets and selected
model remain unchanged. A complete source projection and model refit remain
necessary before these corrections enter contribution estimates.

The price-basis quarantine fit already running uses the frozen pre-correction
source. Finish its matched comparison before combining these new feature
corrections with it. Do not claim the new elevator coefficients are corrected
until the ledger has been projected, its inverse verified, and the model refitted.
This review strengthens the case for checking elevator measurement before fitting
floor interactions; it does not establish any interaction premium.

Validation: 96 tests pass across attribute extraction, the replay audit,
source-audit integrations, analytical transformation and the correction ledger.
The actual replay covers all selected original captures, and the ledger preview
was checked for idempotence.

Reproduce the replay with `models.elevator_negation_audit`, passing the revised
price-basis dataset, refreshed description archive, historical export and raw
Parquet archive. `--previous-extractor` can point to the final bundle's
`previous-attribute-evidence.py`; use a fresh output directory when code changes.
Run `python -m docs.analysis.scripts.review_elevator_negation` through `uv` to
verify or recreate the exact reviewed ledger/preview.
