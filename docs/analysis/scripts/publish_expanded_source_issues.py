"""Carry three manually reviewed advertisements into the expanded-source notes.

No observation, price, posterior, or main-selection mutation. The complete
archived-capture review is in chelsea-spline-source-issues-2026-09-19.md.
"""
import argparse
import json
from pathlib import Path

from apartments import source_issues
from apartments.research_pipeline import digest

SOURCE_HASH = 'd244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717'
EVIDENCE_HASH = '79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08'
TEMPORAL_SCOPE = (
    'Exact historical initial-ask observation with retrospective same-advertisement '
    'attributes. The description was captured in September 2026; its wording is '
    'not independently dated to the initial ask or the full marketing interval. '
    'This note does not assign a physical-attribute effective date.'
)


def specifications():
    return [
        {'audit_id': '15b0a695cf02ea4e2102d83f014a109ef7bdd423d20fdfbd2cedef7593922302',
         'kind': 'furnished_only_offer_unmodeled',
         'message': 'This advertisement explicitly offers the apartment furnished only for a one- or two-year lease; the analytical furnishing field is unknown. Furnishing may contribute to its residual. No separate furnished premium or signed rent is established.',
         'temporal_scope': TEMPORAL_SCOPE,
         'observed_fields': {'furnished': None, 'asking_rent': 18000., 'period': '2023-06-01'},
         'literals': ['Please note: The apartment is being offered furnished only, for 1 or 2 year lease.']},
        {'audit_id': '15b0a695cf02ea4e2102d83f014a109ef7bdd423d20fdfbd2cedef7593922302',
         'kind': 'in_unit_laundry_claim_unextracted',
         'message': 'The own-advertisement description names a utility closet with a washer/dryer, while analytical laundry type is unknown. This is an extraction lead; the annotation does not change the fitted feature.',
         'temporal_scope': TEMPORAL_SCOPE,
         'observed_fields': {'laundry_type': None},
         'literals': ['a utility closet with stacked front-loading Whirlpool washer/dryer']},
        {'audit_id': 'b97bfb2f62f56515737f38c5a8352486864118749a3ef45b81ab0414b42a3aa5',
         'kind': 'furnished_offer_unmodeled',
         'message': 'This advertisement describes a furnished rental while the analytical furnishing field is unknown. It does not establish furnished-only terms, exclude an unfurnished alternative, or quantify a furnishing premium.',
         'temporal_scope': TEMPORAL_SCOPE,
         'observed_fields': {'furnished': None, 'asking_rent': 35000., 'period': '2017-03-01'},
         'literals': ['This furnished rental is the epitome of luxury and is available immediately for the most discerning resident.']},
        {'audit_id': '03c8e14364538ae2750529efa9bda9082461d74e0a9725b7ad5a8af72e469180',
         'kind': 'structured_prose_bathroom_conflict',
         'message': 'Structured and fitted bathroom counts are five full and zero half, but the description says 5.5 baths. The conflicting claims remain unresolved; the note does not add a half bath or change the unknown penthouse floor.',
         'temporal_scope': TEMPORAL_SCOPE,
         'observed_fields': {'bathrooms': 5., 'reported_full_bathrooms': 5, 'reported_half_bathrooms': 0},
         'literals': ['5 bed, 5.5 bath duplex']},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reviewed-at', required=True)
    args = parser.parse_args()
    if (digest(args.dataset/'complete.json') != SOURCE_HASH
            or digest(args.evidence/'complete.json') != EVIDENCE_HASH):
        raise ValueError('Expected the reviewed expanded source and exact description archive')
    notes = source_issues.publish_source_issues(
        args.dataset, args.evidence, specifications(), args.output,
        reviewed_at=args.reviewed_at, reviewer='Codex: complete archived-capture source review')
    restored = source_issues.load_source_issues(args.dataset, args.output, evidence=args.evidence)
    if notes != restored:
        raise ValueError('Published source notes differ from independently loaded notes')
    print(json.dumps({'observations': len(notes),
                      'issues': sum(len(note['issues']) for note in notes.values()),
                      'manifest_sha256': digest(args.output/'complete.json')}), flush=True)


if __name__ == '__main__':
    main()
