"""Occurrence-level outdoor claims with separate access scope and evidence basis.

This finite grammar measures advertising statements, not physical amenities.
Private and shared occurrences of one type can coexist. Text evidence does not
require a structured code; corroboration is recorded as a separate dimension.
No absence, ownership, exclusivity or area is inferred from unit access.
"""
from __future__ import annotations

import re

from apartments.outdoor_evidence import extract

VERSION = 'outdoor-access-scope-v1'
SCOPES = ('private_explicit', 'unit_access', 'shared', 'view', 'negative', 'planned', 'unresolved')
_NOUN = re.compile(
    r'\b(?P<ROOF_DECK>roof(?:[ -]?top)?[ -]+decks?)\b|'
    r'\b(?P<BALCONY>balcon(?:y|ies))\b|\b(?P<TERRACE>terraces?)\b|'
    r'\b(?P<PATIO>patios?)\b|\b(?P<GARDEN>gardens?)\b|'
    r'\b(?P<COURTYARD>courtyards?)\b|\b(?P<YARD>(?:back[ -]?)?yards?)\b|'
    r'\b(?P<DECK>decks?)\b|\b(?P<OUTDOOR_SPACE>outdoor\s+(?:spaces?|areas?))\b', re.I)
_BOUNDARY = re.compile(r'[;!?\n\r\u2028\u2029]|(?<!\d)\.(?!\d)|<br\s*/?>|</p>', re.I)
_ADJ = (r'(?:large|small|huge|spacious|expansive|oversized|landscaped|planted|sunny|'
        r'covered|uncovered|enclosed|outdoor|wraparound|wrap-around|beautiful|massive|'
        r'roof|rooftop|roof\s+top|rear|back|front|lush|lovely|spectacular|perfect|'
        r'(?:north|south|east|west)(?:east|west)?[ -]facing|'
        r'\d+(?:,\d{3})*(?:\.\d+)?[ -]*(?:square[ -]*(?:foot|feet)|sq\.?[ -]*ft\.?|sf))')
_MOD = rf'(?:(?:a|an|the|its|your|own|private|privates|shared|common|communal|{_ADJ})[ \t-]+){{0,9}}'
_PRIVATE = re.compile(rf'\b(?:private(?:s)?|your\s+own|exclusive)(?:[ \t-]+{_ADJ}){{0,5}}[ \t-]+$', re.I)
_SHARED_ADJ = re.compile(rf'\b(?:shared|common|communal|community)(?:[ \t-]+{_ADJ}){{0,5}}[ \t-]+$', re.I)
_NEG = re.compile(rf'\b(?:no|without|lacks?|not\s+(?:have|having|include|including|offer|offering|provide|providing))\s+{_MOD}$', re.I)
_NEG_ACCESS = re.compile(rf'\b(?:no|without|denied)\s+access\s+to\s+{_MOD}$', re.I)
_AFTER_NEG = re.compile(r'^\s*(?:is|are|was|were)\s+(?:not\s+(?:included|available|accessible)|unavailable|inaccessible)\b', re.I)
_VIEW = re.compile(rf'\b(?:views?\s+(?:of|over|onto)|overlooks?|overlooking|faces|facing)\s+{_MOD}$', re.I)
_FUTURE = re.compile(r'\b(?:planned|proposed|future|potential|optional|possible|may|might|could|would|will|to be|under construction)\b', re.I)
_MULTI = re.compile(r'\b(?:some|select|selected|other|certain|all)\s+(?:units|apartments|homes|residences)\b|'
                    r'\b(?:units|apartments|homes|residences|penthouses)\s+(?:feature|offer|have|include|with)\b', re.I)
_BUILDING = re.compile(r'\b(?:the|this|our)\s+(?:building|community|complex)\b|'
                       r'\b(?:building|community|residents?)\s+(?:amenities|features|offers?|includes?|enjoy|have|has|access)\b', re.I)
_UNIT = re.compile(r'\b(?:this|your|the)\s+(?:apartment|unit|home|residence|townhouse|penthouse)\b', re.I)
_UNIT_VERB = re.compile(r'\b(?:has|have|offers?|features?|includes?|boasts?|with|enjoys?)\b', re.I)
_ROOM = r'(?:(?:your|the|a|an|its|primary|master|main|second|guest|spacious|large)\s+){0,3}(?:living\s+(?:room|area)|dining\s+(?:room|area)|bedroom|kitchen|home\s+office|great\s+room|apartment|unit|home|residence|suite)'
_OFF_ROOM = re.compile(rf'^\s+(?:off|off\s+of|adjoining|attached\s+to|accessible\s+from)\s+{_ROOM}\b', re.I)
_FROM_ROOM = re.compile(rf'\b{_ROOM}.{{0,90}}\b(?:access\s+to|opens?\s+(?:out\s+)?(?:to|onto)|leads?\s+(?:out\s+)?(?:to|onto))\s+{_MOD}$', re.I)
_DOORS = re.compile(rf'\b(?:french\s+|sliding\s+)?doors?\s+(?:opens?|leads?)\s+(?:out\s+)?(?:to|onto)\s+{_MOD}$', re.I)
_HEADING = re.compile(r'(?:^|[\n\r.;]|<br\s*/?>|</p>)[ \t]*(?P<scope>building amenities|'
                     r'building features|community amenities|shared amenities|apartment features|'
                     r'unit features|home features)[ \t]*:?', re.I)


def _bounds(text, start, end):
    preceding = list(_BOUNDARY.finditer(text, 0, start))
    following = _BOUNDARY.search(text, end)
    return (preceding[-1].end() if preceding else 0, following.start() if following else len(text))


def scope_text(text: str | None, source_path='/description') -> list[dict]:
    """Classify individual literal mentions; unresolved mentions remain visible.

    Scope is local to each occurrence. ``unit_access`` is weaker than exclusive
    use. Section headings and explicit building subjects guard apartment-access
    rules; terse text lacking a subject can remain unresolved.
    """
    if not isinstance(text, str) or not text:
        return []
    result = []
    headings = list(_HEADING.finditer(text))
    for noun in _NOUN.finditer(text):
        left, right = _bounds(text, noun.start(), noun.end())
        before, after = text[left:noun.start()], text[noun.end():right]
        # A contrast introduces a new local subject/scope, without losing the
        # complete sentence used for review.
        contrasts = list(re.finditer(r'\b(?:but|whereas|while)\b', before, re.I))
        local_left = contrasts[-1].end() if contrasts else 0
        prefix = before[local_left:]
        private = _PRIVATE.search(prefix)
        units = list(_UNIT.finditer(prefix))
        building = list(_BUILDING.finditer(prefix))
        multi = list(_MULTI.finditer(prefix))
        unit_override = bool(units and all(m.end() <= units[-1].start() for m in building + multi))
        local_headings = [h for h in headings if h.start() < noun.start()]
        heading = local_headings[-1] if local_headings else None
        shared_heading = bool(heading and heading.group('scope').lower().startswith(('building', 'shared', 'community')))
        if shared_heading and units and left + local_left + units[-1].start() >= heading.end():
            shared_heading = False
        shared_adj = _SHARED_ADJ.search(prefix)
        after_shared = re.match(r'^\s*(?:(?:is|are)\s+)?(?:shared|common|communal)\b|^\s+for\s+(?:all\s+)?residents\b', after, re.I)
        semi = bool(private and re.search(r'\bsemi[ -]?$', prefix[:private.start()], re.I))
        negative = bool(_NEG.search(prefix) or _NEG_ACCESS.search(prefix) or _AFTER_NEG.search(after))
        not_private = bool(re.match(r'^\s*(?:is|are)\s+not\s+private\b', after, re.I))
        view = bool(_VIEW.search(prefix))
        shared = bool(shared_adj or after_shared or shared_heading or (building and not unit_override))
        multiple = bool(multi and not unit_override)
        # Garden-level is an indoor level name, not evidence of outdoor access.
        nonamenity = bool(noun.lastgroup == 'GARDEN' and re.match(r'^[ -]+(?:level|floor|apartment)\b', after, re.I))
        access = bool(_OFF_ROOM.search(after) or _FROM_ROOM.search(prefix) or _DOORS.search(prefix))
        unit_feature = bool(units and _UNIT_VERB.search(prefix[units[-1].end():]))
        # A later clause can change scope: "this unit has windows overlooking a
        # garden" must remain view evidence, despite its unit subject.
        future = bool(_FUTURE.search(prefix) or re.match(r'^\s*(?:is|are)\s+(?:planned|proposed|under construction)\b', after, re.I))
        flags = []
        if multiple: flags.append('multiple_unit_subject')
        if semi: flags.append('semi_private')
        if not_private: flags.append('explicit_not_private')
        if nonamenity: flags.append('indoor_level_wording')
        if shared and private: flags.append('private_wording_with_shared_scope')
        if future: flags.append('planned_or_hypothetical')
        if negative:
            scope, rule = 'negative', 'explicit_negation'
        elif nonamenity or multiple or semi or not_private:
            scope, rule = 'unresolved', 'scope_or_meaning_ambiguous'
        elif view:
            scope, rule = 'view', 'view_relation'
        elif future:
            scope, rule = 'planned', 'future_or_conditional_claim'
        elif shared:
            scope, rule = 'shared', 'shared_adjective_or_building_scope'
        elif private:
            scope, rule = 'private_explicit', 'direct_private_modifier'
        elif access:
            scope, rule = 'unit_access', 'room_or_door_access_relation'
        elif unit_feature:
            scope, rule = 'unit_access', 'unit_subject_feature_relation'
        else:
            scope, rule = 'unresolved', 'no_supported_access_relation'
        start = left + local_left + private.start() if private else noun.start()
        result.append({'type':noun.lastgroup, 'scope':scope, 'rule':rule, 'flags':flags,
                       'start':start, 'end':noun.end(), 'match':text[start:noun.end()],
                       'noun_start':noun.start(), 'noun_end':noun.end(),
                       'context_start':left, 'context_end':right, 'context':text[left:right],
                       'source_path':source_path})
    return result


def measure(captures: list[dict]) -> dict:
    """Measure one analytical advertisement's captures without overwriting sources.

    Shared and private evidence can coexist. Positive and negative claims of the
    same type are flagged for review; they are not reconciled by order or used to
    invent a validity interval. Capture dates alone do not date physical changes.
    """
    identities = {(c.get('audit_id'), c.get('source_listing_id'), c.get('unit_id')) for c in captures}
    if len(identities) > 1:
        raise ValueError('Outdoor scope captures must belong to one analytical advertisement')
    claims, seen = [], set()
    for capture in captures:
        if capture['capture_id'] in seen:
            raise ValueError('Duplicate outdoor scope capture_id')
        seen.add(capture['capture_id'])
        payload = {'description':capture.get('description'), 'propertyDetails':capture.get('property_details')}
        extraction = extract(payload)
        if extraction != capture.get('extraction'):
            raise ValueError('Source capture extraction mismatch')
        description, path = payload['description'], '/description'
        if isinstance(payload['propertyDetails'], dict) and isinstance(payload['propertyDetails'].get('description'), str):
            description, path = payload['propertyDetails']['description'], '/propertyDetails/description'
        for claim in scope_text(description, path):
            expected = 'PRIVATE_ROOF_DECK' if claim['type'] == 'ROOF_DECK' else claim['type']
            structured = [a for a in extraction['assertions'] if
                          (a['attribute']=='private_type' and a['value']==expected) or
                          (a['attribute']=='shared_type' and a['value']==claim['type'])]
            claims.append({**claim, **{k:capture.get(k) for k in ('capture_id','body_sha256','raw_listing_sha256','source_collected_at','description_interpreted_at')},
                           'structured_assertions':structured,
                           'basis':'text_and_structured_type' if structured else 'text_only'})
    types_by_scope = {scope:sorted({c['type'] for c in claims if c['scope']==scope}) for scope in SCOPES}
    positives = set(types_by_scope['private_explicit']) | set(types_by_scope['unit_access'])
    return {'version':VERSION, 'claims':claims, 'types_by_scope':types_by_scope,
            'private_and_shared_types':sorted(set(types_by_scope['private_explicit']) & set(types_by_scope['shared'])),
            'positive_and_negative_types':sorted(positives & set(types_by_scope['negative'])),
            'interpretation':'Positive advertised claims only. Unit access does not establish exclusivity; unknown does not mean absent. Coexisting occurrences are not collapsed into physical facts.'}
