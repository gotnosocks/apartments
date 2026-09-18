"""Conservative text corroboration of same-capture structured outdoor types.

This is a finite phrase rule for a measurement sensitivity experiment, not a
complete language parser or evidence that unmentioned amenities are absent.
Source audit records must reproduce the original literal extraction. A type is
kept only when the same capture has both its structured code and unambiguous
unit-private wording. Conflicting wording blocks that type across the supplied
captures; callers must supply captures of one analytical advertisement only.
"""
from __future__ import annotations

import re

from apartments.outdoor_evidence import PRIVATE_TYPES, extract

VERSION = 'outdoor-private-text-corroboration-v1'
_NOUN = re.compile(r'\b(?P<roof>roof(?:top)?[ -]+decks?)\b|\b(?P<balcony>balcon(?:y|ies))\b|'
                   r'\b(?P<garden>gardens?)\b|\b(?P<terrace>terraces?)\b|\b(?P<patio>patios?)\b', re.I)
_CODES = {'roof': 'PRIVATE_ROOF_DECK', 'balcony': 'BALCONY', 'garden': 'GARDEN',
          'terrace': 'TERRACE', 'patio': 'PATIO'}
_ADJECTIVE = (r'(?:large|small|huge|spacious|expansive|oversized|landscaped|planted|sunny|'
              r'covered|uncovered|enclosed|outdoor|wraparound|wrap-around|beautiful|'
              r'(?:north|south|east|west)(?:east|west)?[ -]facing|'
              r'\d+(?:,\d{3})*(?:\.\d+)?[ -]*(?:square[ -]*(?:foot|feet)|sq\.?[ -]*ft\.?|sf))')
_PRIVATE = re.compile(r'\b(?:private|your\s+own)(?:[ \t-]+' + _ADJECTIVE + r'){0,5}[ \t-]+$', re.I)
_BOUNDARY = re.compile(r'[;!?\n\r\u2028\u2029]|(?<!\d)\.(?!\d)|<br\s*/?>|</p>', re.I)
_HEADING = re.compile(r'(?:^|[\n\r.;]|<br\s*/?>|</p>)[ \t]*(?P<scope>building amenities|'
                      r'building features|community amenities|shared amenities|'
                      r'apartment features|unit features|home features)[ \t]*:?', re.I)
_UNIT = re.compile(r'\b(?:this|your|the)\s+(?:apartment|unit|home|residence)\b', re.I)
_MULTI = re.compile(r'\b(?:some|select|selected|other|certain|all)\s+(?:units|apartments|homes|residences)\b|'
                    r'\b(?:units|apartments|homes|residences|penthouses)\s+(?:feature|offer|have|include|with)\b', re.I)
_SHARED = re.compile(r'\b(?:shared|common|communal|community|residents?\b|building\b)', re.I)
_FUTURE = re.compile(r'\b(?:planned|proposed|future|will|soon|to be|undergoing|under construction|'
                     r'may|might|could|would|potential|optional|possible)\b', re.I)
_VIEW = re.compile(r'\b(?:views?\s+(?:of|over|onto)|overlooks?|overlooking|faces|facing)\s+'
                   r'(?:(?:a|an|the|its|private|your|own|' + _ADJECTIVE + r')\s+){0,8}$', re.I)
_NEGATED = re.compile(r'\b(?:no|without|lacks?|not(?:\s+(?:have|having|offer|offering|include|including|'
                      r'feature|featuring|provide|providing))?)\s+'
                      r'(?:(?:a|an|any|the|its|own|your|access|to|private|' + _ADJECTIVE + r')\s+){0,8}$', re.I)
_AFTER_NEGATION = re.compile(r'^\s*(?:is|are|was|were)\s+(?:not\s+(?:private|included|available)|shared|communal|common)\b', re.I)


def _context(description: str, start: int, end: int) -> tuple[int, int]:
    before = list(_BOUNDARY.finditer(description, 0, start))
    after = _BOUNDARY.search(description, end)
    return (before[-1].end() if before else 0, after.start() if after else len(description))


def corroborate(captures: list[dict]) -> dict:
    """Return corroborated codes and exact-source accepted/rejected evidence.

    ``private_types=[]`` means unknown under this rule. Rejected and ambiguous
    matches are review evidence, never explicit physical-absence assertions.
    The input source hashes are carried through, not reverified against bodies;
    the upstream immutable audit verifies those bodies and advertisement IDs.
    """
    result = {'version': VERSION, 'private_types': [], 'evidence': [],
              'rejected_evidence': [], 'ambiguous_evidence': []}
    proposed = []
    contradicted = set()
    identities = {(c.get('audit_id'), c.get('source_listing_id'), c.get('unit_id')) for c in captures}
    if len(identities) > 1:
        raise ValueError('Corroboration captures must belong to one analytical advertisement')
    seen = set()
    for capture in captures:
        capture_id = capture['capture_id']
        if capture_id in seen:
            raise ValueError('Duplicate corroboration capture_id')
        seen.add(capture_id)
        description = capture.get('description')
        payload = {'propertyDetails': capture.get('property_details'), 'description': description}
        extraction = extract(payload)
        if extraction != capture.get('extraction'):
            raise ValueError('Source capture extraction mismatch')
        description_path = '/description'
        details = capture.get('property_details')
        if isinstance(details, dict) and isinstance(details.get('description'), str):
            description, description_path = details['description'], '/propertyDetails/description'
        structured = {a['value'] for a in extraction['assertions']
                      if a['attribute'] == 'private_type' and a['value'] in PRIVATE_TYPES}
        if not isinstance(description, str) or not description:
            continue
        headings = list(_HEADING.finditer(description))
        for noun in _NOUN.finditer(description):
            code = _CODES[noun.lastgroup]
            left, right = _context(description, noun.start(), noun.end())
            before = description[left:noun.start()]
            after = description[noun.end():right]
            local = description[left:right]
            private = _PRIVATE.search(before)
            start = left + private.start() if private else noun.start()
            reasons = []
            negated = bool(_NEGATED.search(before) or _AFTER_NEGATION.search(after))
            if negated:
                reasons.append('negated_or_shared_type_statement')
            if private and re.search(r'\bsemi[ -]?$', description[max(0, start - 8):start], re.I):
                reasons.append('semi_private')
            if _FUTURE.search(local):
                reasons.append('planned_or_hypothetical_language')
            units = list(_UNIT.finditer(before))
            multiple = list(_MULTI.finditer(local))
            # A concrete unit subject must follow the multiple-unit wording, not
            # merely precede it ("this home is among units with ...").
            if multiple and not (units and all(m.end() <= units[-1].start() for m in multiple)):
                reasons.append('multiple_unit_scope')
            shared = list(_SHARED.finditer(local))
            if shared and not (units and all(m.end() <= units[-1].start() for m in shared)):
                reasons.append('building_or_shared_scope')
            preceding_headings = [h for h in headings if h.start() < noun.start()]
            if preceding_headings and preceding_headings[-1].group('scope').lower().startswith(('building', 'community', 'shared')):
                if not units or left + units[-1].start() < preceding_headings[-1].end():
                    reasons.append('building_or_shared_heading')
            view = _VIEW.search(before)
            if view and (not private or view.start() < private.start()):
                reasons.append('view_without_access')
            evidence = {
                'capture_id': capture_id, 'body_sha256': capture.get('body_sha256'),
                'raw_listing_sha256': capture.get('raw_listing_sha256'), 'code': code,
                'start': start, 'end': noun.end(), 'match': description[start:noun.end()],
                'context_start': left, 'context_end': right, 'context': local,
                'source_path': description_path, 'reasons': reasons,
                'structured_same_capture': code in structured,
            }
            if code not in structured:
                evidence['reasons'] = reasons + ['no_same_capture_structured_type']
                result['ambiguous_evidence'].append(evidence)
                # A clear contrary statement in another capture still conflicts
                # with this advertisement's positive claim.
                if negated or 'building_or_shared_scope' in reasons:
                    contradicted.add(code)
            elif private and reasons:
                result['rejected_evidence'].append(evidence)
                # Uncertain scope is not a factual negative. Only direct
                # contradiction, shared use or negation blocks other captures.
                if negated or 'building_or_shared_scope' in reasons or 'semi_private' in reasons:
                    contradicted.add(code)
            elif private:
                proposed.append(evidence)
            else:
                evidence['reasons'] = reasons + ['no_direct_private_type_phrase']
                result['ambiguous_evidence'].append(evidence)
                if negated or 'building_or_shared_scope' in reasons:
                    contradicted.add(code)
        # Keep generic wording (e.g. private deck without a roof) reviewable.
        covered = {(m.start(), m.end()) for m in _NOUN.finditer(description)}
        for candidate in extraction['description_candidates']:
            if candidate['feature'] != 'outdoor_wording' or (candidate['start'], candidate['end']) in covered:
                continue
            result['ambiguous_evidence'].append({
                'capture_id': capture_id, 'body_sha256': capture.get('body_sha256'),
                'raw_listing_sha256': capture.get('raw_listing_sha256'), 'code': None,
                'start': candidate['start'], 'end': candidate['end'], 'match': candidate['match'],
                'source_path': candidate['source_path'], 'reasons': ['no_supported_direct_type_phrase'],
                'structured_same_capture': False,
            })
    for evidence in proposed:
        if evidence['code'] in contradicted:
            evidence['reasons'] = ['contradictory_type_evidence']
            result['rejected_evidence'].append(evidence)
        else:
            result['evidence'].append(evidence)
    result['private_types'] = sorted({e['code'] for e in result['evidence']})
    return result
