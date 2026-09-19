"""Record manual source findings for the preselected dominant-building cases."""
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

# Conclusions from direct review of complete, hash-bound descriptions and all
# original structured captures. These decisions do not mutate a running fit.
DECISIONS = {
    '3338940': ('initial_ask_and_omitted_balcony',
        'Studio count agrees. Structured features explicitly include a balcony, absent from the prose and model. Own-ad ask falls from 3200 to 3000 the same day and later to 2700. The model intentionally uses the initial 3200; later prices do not prove that target was an error.',
        ['Beautiful Studio in Prime Chelsea!', 'laundry on every floor']),
    '3223153': ('bedroom_description_conflict',
        'The structured bedroom count is 1, but the complete description calls the apartment a studio and structured roomCount is 1. This can explain part of the negative residual, but copied description versus structured-count error remains unresolved. Do not silently replace either source assertion.',
        ['Beautiful Studio in Prime Chelsea!', 'laundry on every floor']),
    '4764409': ('description_location_conflict_and_initial_ask',
        'Structured address and canonical identity agree on 85 Eighth Avenue #5K. The description begins with Chelsea but contains incompatible Hell’s Kitchen/Central Park boilerplate and explicitly uses similar-unit photos. A large home office is a layout hypothesis, not a verified extra bedroom. Own-ad initial ask is 7000, later varying from 7500 down to 6000 before 6500; retain the original sequence.',
        ['Bright and Modern 1 Bedroom in prime Chelsea', 'a large home office', 'Hell’s Kitchen',
         'Please note photos reflect similar apartment on same line, apartment may slightly vary.']),
    '3895033': ('missed_same_floor_and_layout_ambiguity',
        'The source explicitly reports washer/dryer access on every floor, but extractor v3 misses this equipment-only phrase and leaves generic building laundry. A queen-size sleeping alcove behind French doors, balcony and renovation claims suggest layout/outdoor features to review. Structured bedroomCount is 1; no source correction is inferred from the alcove alone.',
        ['French doors open to a sleeping alcove', 'Enjoy your balcony', 'a washer/dryer on every floor']),
    '1894894': ('convertible_layout_and_initial_ask',
        'Both captures report a true one-bedroom convertible to two, consistent with structured bedroomCount 1. The model lacks measured area and this flexible-layout distinction. Initial ask 4800 falls to 4200 twelve days later. Keep the own-ad initial target; a later reduction is not evidence of a typo.',
        ['convertible 2 bedroom(True One Bedroom)', 'laundry facilities on every floor']),
    '2675026': ('net_price_basis_and_divided_layout',
        'Both captures preserve own-ad initial price 2878 on March 12, 2019, followed by 3100 on March 25. The description explicitly labels 3100 gross and 2878 net with one free month over 14 months, while structured concession fields are null. The analytical initial target equals the described net amount. Flag this observation for gross-price-basis quarantine in the next source revision; do not substitute the later 3100 at the earlier event date. The junior/divided one-bedroom layout is a separate hypothesis.',
        ['The gross rent is $3,100 with 1 month free on a 14-month lease term, the net rent is just $2,878!',
         'The unit is a Jr 1 bedroom with a divider']),
    '2034677': ('bedroom_wording_ambiguity',
        'Structured bedroomCount is 0 and roomCount is 3, while the description advertises a queen/full-size bedroom without explicitly stating a room count or separation. This is a layout/count review candidate, not proof of a one-bedroom. Initial ask 3400 later changes to 3138, 3300 and 3200. Structured and displayed identity agree.',
        ['Queen/Full Size Bedroom', 'BRAND NEW Kitchen']),
    '970866': ('short_term_product_and_missed_same_floor',
        'The offer explicitly says it is available on a short-term basis, with no duration or ordinary long-term option established. Flag lease-product scope for the next cohort review. BedroomCount 2 and 800 square feet agree with the description. Extractor v3 misses the explicit phrase laundry with new machines on every floor. No rent or bedroom replacement is supported.',
        ['AVAILABLE ON A SHORT-TERM BASIS', 'laundry with new machines on every floor']),
}


def run():
    base = Path(__file__).resolve().parents[3]/'data/model'
    candidates = base/'chelsea-laundry-dominant-building-review-candidates-20260919'
    raw = base/'chelsea-laundry-dominant-building-raw-review-20260919'
    _, cf = _verified_bundle(candidates, retain={'cases.jsonl'})
    rm, rf = _verified_bundle(raw, retain={'captures.jsonl'})
    if rm['candidates_manifest_sha256'] != digest(candidates/'complete.json'):
        raise ValueError('Raw source review lineage differs')
    cases = [json.loads(s) for s in cf['cases.jsonl'].decode().split('\n') if s]
    captures = {r['capture_id']: r for r in (json.loads(s) for s in rf['captures.jsonl'].decode().split('\n') if s)}
    if {c['source_record']['source_listing_id'] for c in cases} != DECISIONS.keys():
        raise ValueError('Manual review cohort changed')
    decisions = []
    for case in cases:
        row = case['source_record']; ad = row['source_listing_id']
        finding, interpretation, phrases = DECISIONS[ad]
        quotes = []
        for phrase in phrases:
            matching = []
            for c in case['captures']:
                text = c['description'] or ''
                start = text.find(phrase)
                if start >= 0:
                    matching.append({'capture_id': c['capture_id'], 'description_sha256': c['description_sha256'],
                        'start': start, 'end': start+len(phrase), 'literal': text[start:start+len(phrase)]})
            if not matching: raise ValueError('Reviewed phrase is absent: '+ad)
            quotes.extend(matching)
        sources = [captures[c['capture_id']] for c in case['captures']]
        if any(c['source_listing_id'] != ad or c['audit_id'] != row['audit_id'] for c in sources):
            raise ValueError('Reviewed raw source identity differs')
        decisions.append({'audit_id': row['audit_id'], 'source_listing_id': ad, 'unit_id': row['unit_id'],
            'building': row['building'], 'finding': finding, 'interpretation': interpretation,
            'literal_evidence': quotes, 'source_capture_ids': [c['capture_id'] for c in sources],
            'accepted_residual': case['accepted_residual'],
            'status': 'reviewed_source_findings_no_current_fit_mutation'})
    summary = {'version': 'laundry-dominant-building-source-adjudication-v1', 'cases': len(decisions),
        'original_captures_reviewed': len(captures), 'missed_same_floor_cases': ['3895033', '970866'],
        'gross_basis_quarantine_candidate': '2675026', 'short_term_scope_candidate': '970866',
        'bedroom_conflict_candidate': '3223153',
        'conclusion': 'Residual extremes reveal target basis, layout, reporting completeness and price-path issues. Neither residual sign nor the laundry coefficient resolves these sources. Keep the running controlled comparison unchanged; revise source measurements/cohort separately before promotion.',
        'main_selection_changed': False}
    publish_bundle(base/'chelsea-laundry-dominant-building-source-review-20260919',
        {'summary.json': canonical(summary)+'\n', 'decisions.jsonl': ''.join(canonical(r)+'\n' for r in decisions),
         Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'candidate_manifest_sha256': digest(candidates/'complete.json'),
         'raw_review_manifest_sha256': digest(raw/'complete.json')})
    print(canonical(summary), flush=True)


if __name__ == '__main__': run()
