"""Conservative, auditable attributes from a single StreetEasy listing payload.

This describes the captured advertisement, not an independently verified unit.
It never reads latestListing, propertyHistory, unit labels, or building outdoor
amenities to infer the unit's features. Empty source arrays mean unknown.
"""
from __future__ import annotations

from collections import defaultdict
import math
import re

VERSION = 'attribute-evidence-v7'
NAMED_UNIT_FLOOR_RULE = 'named-unit-initial-offer-floor-v1'
_ORDINAL_FLOORS = dict(zip((
    'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth',
    'ninth', 'tenth', 'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth',
    'sixteenth', 'seventeenth', 'eighteenth', 'nineteenth', 'twentieth'), range(1, 21)))
_NAMED_UNIT_FLOOR = re.compile(
    r'\A\s*(?:welcome\s+to\s+)?(?P<claim>(?:apartment|unit|residence)\s+'
    r'#?(?=[a-z0-9]*[0-9])[a-z0-9]{1,8}\s+on\s+(?:the\s+)?'
    r'(?P<floor>[0-9]{1,3}(?:st|nd|rd|th)?|' + '|'.join(_ORDINAL_FLOORS) + r')\s+floor\b)', re.I)
VIEWS = ('street', 'courtyard', 'garden', 'city', 'skyline', 'water', 'park')
DIRECTIONS = ('north', 'east', 'south', 'west')
SCALARS = ('bedrooms', 'bathrooms', 'square_feet', 'advertised_floor',
           'physical_floor', 'floors_above_ground', 'elevator', 'laundry_type',
           'doorman_type', 'hvac_type', 'pet_policy')


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _named_unit_floor(description):
    """Return only an explicit location in a named dwelling's initial offer.

    Labels delimit the claim; their digits never supply the floor value. Scope
    checks cover the introducing sentence across wrapped lines and deliberately
    have no "this dwelling" exception for reference or shared-space language.
    """
    match = _NAMED_UNIT_FLOOR.match(description)
    if match is None:
        return None
    sentence_end = re.search(r'[.!?;]', description[match.end():])
    if sentence_end and sentence_end.group() == '?':
        return None
    end = match.end() + sentence_end.start() if sentence_end else len(description)
    sentence = description[:end]
    if re.search(
        r'\b(?:photos?|photographs?|pictures?|images?|videos?|tours?|model|sample|reference|'
        r'example|illustrative|similar|comparable|compar(?:ed|ing|es)|another|different|other|unlike|versus|'
        r'roof\s*deck|rooftop|fitness|gym|lobby|lounge|common|shared|amenit(?:y|ies)|'
        r'may|might|could|would|should|will|if|unless|whether|optional|potential|'
        r'possibly|perhaps|probably|apparently|reportedly|supposed(?:ly)?|estimated|assum(?:ed|ing)|'
        r'no|not|without|never|except)\b|\brather\s+than\b|n[’\']t\b', sentence, re.I):
        return None
    token = match['floor'].lower()
    value = _ORDINAL_FLOORS.get(token)
    if value is None:
        numeric = re.fullmatch(r'([0-9]{1,3})(st|nd|rd|th)?', token)
        value = int(numeric[1])
        suffix = 'th' if 10 <= value % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')
        if value < 1 or (numeric[2] and numeric[2] != suffix):
            return None
    return match, value


def _reference_floor_claim(prefix: str, claim: str) -> bool:
    """Recognize reference-unit scope immediately governing a floor match.

    A mention of photography elsewhere in the sentence is insufficient: the
    media/reference phrase must lead directly into the matched dwelling noun.
    """
    if re.match(r'this\b', claim, re.I):
        return False  # Explicitly identifies the advertised dwelling itself.
    reference = r'(?:same|similar|comparable|another|different|model|sample|reference|example|illustrative)'
    if re.search(r'\b'+reference+r'\s+$', prefix, re.I):
        return True
    media = r'(?:photos?|photographs?|pictures?|images?|videos?|virtual tours?)'
    relation = r'(?:of|show(?:s|ing)?|depict(?:s|ing)?|feature(?:s|ing)?|taken (?:in|from))'
    determiners = r'(?:(?:the|a|an|'+reference+r')\s+)*'
    return bool(re.search(r'\b'+media+r'\b[^.!?;\n]*?\b'+relation+r'\s+'+determiners+r'$', prefix, re.I))


def extract_attribute_evidence(raw_listing: dict) -> dict:
    """Return attributes, literal evidence, conflicts, and extraction warnings.

    Provenance paths are JSON pointers into the supplied raw listing. Description
    evidence contains exact substrings and character offsets. Conflicting
    assertions produce null, preserving every assertion for human review. A
    generic doorman code and a more specific subtype are compatible; in-unit and
    building laundry can coexist and resolve to the in-unit category.
    A 'not:' categorical evidence value denies only that subtype; it cannot
    establish absence of all laundry or HVAC equipment.
    """
    details = raw_listing.get('propertyDetails') or {}
    if not isinstance(details, dict):
        details = {}
    evidence, warnings, ambiguous_attributes = [], [], set()

    def add(attribute, value, path, literal, method='structured', **extra):
        evidence.append(dict(attribute=attribute, value=value, source_path=path,
                             literal=literal, method=method, **extra))

    for source, attribute in [('bedroomCount', 'bedrooms'), ('livingAreaSize', 'square_feet'),
                              ('floor', 'advertised_floor'), ('listedFloor', 'advertised_floor'),
                              ('physicalFloor', 'physical_floor'), ('floorsAboveGround', 'floors_above_ground')]:
        number = _number(details.get(source))
        if number is not None and (number >= 0 if attribute != 'square_feet' else number > 0):
            add(attribute, number, '/propertyDetails/' + source, details[source])
    full, half = _number(details.get('fullBathroomCount')), _number(details.get('halfBathroomCount'))
    if full is not None and full >= 0 and (half is None or half >= 0):
        # Missing half count does not establish zero; source bathroomCount may
        # still provide an explicit total below.
        if half is not None:
            add('bathrooms', full + half * .5, '/propertyDetails',
                {'fullBathroomCount': full, 'halfBathroomCount': half}, 'structured_sum')
    total = _number(details.get('bathroomCount'))
    if total is not None and total >= 0:
        add('bathrooms', total, '/propertyDetails/bathroomCount', total)

    mapping = {'ELEVATOR': ('elevator', True), 'WASHER_DRYER': ('laundry_type', 'in_unit'),
               'LAUNDRY': ('laundry_type', 'in_building'), 'DOORMAN': ('doorman_type', 'unspecified'),
               'CENTRAL_AC': ('hvac_type', 'central_ac'),
               'PETS_ALLOWED': ('pet_policy', 'allowed_restrictions_unknown')}
    for section in ('features', 'amenities'):
        obj = details.get(section) or {}
        values = obj.get('list', []) if isinstance(obj, dict) else obj
        if isinstance(values, list):
            for index, code in enumerate(values):
                if isinstance(code, str) and code in mapping:
                    attr, value = mapping[code]
                    suffix = f'/list/{index}' if isinstance(obj, dict) else f'/{index}'
                    add(attr, value, '/propertyDetails/' + section + suffix, code)
        if not isinstance(obj, dict):
            continue
        subtypes = obj.get('doormanTypes')
        if section == 'amenities' and isinstance(subtypes, list):
            for index, code in enumerate(subtypes):
                if code in ('FULL_TIME', 'PART_TIME', 'VIRTUAL'):
                    add('doorman_type', code.lower(), f'/propertyDetails/amenities/doormanTypes/{index}', code)
        views = obj.get('views')
        if section == 'features' and isinstance(views, list):
            for index, code in enumerate(views):
                if isinstance(code, str) and code.lower() in VIEWS:
                    add('view_exposures.' + code.lower(), True, f'/propertyDetails/features/views/{index}', code)

    description = raw_listing.get('description')
    if isinstance(description, str) and re.fullmatch(r'\$[A-Za-z0-9]+', description.strip()):
        warnings.append('unresolved_description_reference')
        description = None
    if description is not None and not isinstance(description, str):
        warnings.append('unsupported_description_shape')
        description = None

    # High precision deliberately takes priority over coverage. Complex negation,
    # optional amenities and references to common spaces are left for review.
    if description:
        # Section labels carry scope across newline/HTML bullet lists. A common
        # terrace's views do not become unit views just because its line omits
        # the word "community" used in the preceding heading.
        headings = list(re.finditer(
            r'(?:^|[.;\n\r]|<br\s*/?>)\s*(?P<scope>community amenities|building amenities|building features|'
            r'shared amenities|apartment features|unit features|home features)\s*:?', description, re.I))

        roof_headings = list(re.finditer(
            r"(?:^|[\n\r]|<br\s*/?>)[ \t]*(?:CHELSEA['’]S FINEST )?ROOF DECK[ \t]*(?=[\n\r]|<br\s*/?>|$)",
            description, re.I))

        def scan(pattern, attribute, value, *, negative=None, unit_specific=False):
            for match in re.finditer(pattern, description, re.I):
                start = max(description.rfind('.', 0, match.start()), description.rfind(';', 0, match.start()),
                            description.rfind('\n', 0, match.start())) + 1
                end_match = re.search(r'[.;\n]', description[match.end():])
                end = match.end() + end_match.start() if end_match else len(description)
                sentence = description[start:end]
                before = description[max(start, match.start()-65):match.start()]
                after = description[match.end():min(end, match.end()+45)]
                if attribute == 'advertised_floor' and _reference_floor_claim(description[start:match.start()], match.group()):
                    # Reviewed ads 4501831/4592739/4637006/4668696/4758888
                    # describe photos of a same-layout unit on another floor.
                    if 'reference_unit_floor_claim_withheld' not in warnings:
                        warnings.append('reference_unit_floor_claim_withheld')
                    continue
                if re.search(r'\b(?:may|might|could|optional|potential|permission|hookups?|connections?|installation|install)\b', sentence, re.I):
                    continue
                # Permission to install equipment is not installed equipment.
                if attribute == 'hvac_type' and re.match(
                    r'\s+(?:(?:units?|systems?|equipment)\s+)?(?:(?:is|are)\s+)?(?:permitted|allowed)\b', after, re.I):
                    continue
                # A pedestrian route says nothing about elevator availability.
                if attribute == 'elevator' and re.fullmatch(r'walk[- ]up', match.group(), re.I):
                    if (re.search(r'\b(?:minutes?|mins?)\s*$', before, re.I)
                            or re.match(r'\s+to\b', after, re.I)
                            or re.match(r'\s+(?:\w+\s+){0,3}(?:avenue|street|road|block|broadway)\b', after, re.I)):
                        continue
                if unit_specific:
                    if re.search(r'\b(?:some|many|select|selected|certain|most|other) (?:of (?:the|our) )?(?:apartments|units|homes|residences)\b', sentence, re.I):
                        continue
                    if attribute.startswith(('view_exposures.', 'window_exposures.')):
                        prior_roof = [h for h in roof_headings if h.start() < match.start()]
                        prior_unit = [h for h in headings if h.start() < match.start()
                                      and h.group('scope').lower().startswith(('apartment', 'unit', 'home'))]
                        if prior_roof and (not prior_unit or prior_roof[-1].start() > prior_unit[-1].start()):
                            if not re.search(r'\b(?:this|the|your) (?:apartment|unit|home|residence)\b', sentence, re.I):
                                continue
                    if re.search(r'\b(?:roof\s*deck|rooftop|fitness|gym|lobby|residents? lounge|common|shared|amenit(?:y|ies)|building features)\b', sentence, re.I):
                        continue
                    prior = [h for h in headings if h.start() < match.start()]
                    if prior and prior[-1].group('scope').lower().startswith(('community', 'building', 'shared')):
                        if not re.search(r'\b(?:this|the|your) (?:apartment|unit|home|residence)\b', sentence, re.I):
                            continue
                # Scope short adjacent negation; broader unresolved negation is
                # skipped rather than converted into a positive assertion.
                negated = bool(re.search(r'\b(?:no|without|not|lacks?)(?:\s+|-)(?:an?\s+|any\s+)?$', before, re.I)
                               or re.match(r'\s+(?:is\s+|are\s+)?(?:not\s+(?:allowed|permitted|available)|prohibited)\b', after, re.I))
                if attribute == 'elevator':
                    # Ads 4417318/4931353 say "non-elevator building";
                    # 5118079 uses "non elevator building". The noun alone
                    # must not become a positive elevator assertion.
                    non_prefix = r'non(?:\s+|[-\u2010-\u2014]\s*)$'
                    if re.search(r'\b(?:not|no|without)\s+(?:an?\s+)?'+non_prefix, before, re.I):
                        continue  # Do not resolve a double negation into a physical claim.
                    negated |= bool(re.search(r'\b'+non_prefix, before, re.I))
                if attribute == 'laundry_type':
                    # Ad 4800947 says the building "doesn't have on-site
                    # laundry". Keep this as a scoped denial, including when
                    # the source separately flags a private washer/dryer.
                    negated |= bool(re.search(
                        r"\b(?:does not|doesn['’]t|do not|don['’]t)\s+(?:have|offer|provide)\s+(?:any\s+)?$",
                        before, re.I) or re.match(
                        r"\s+(?:is not|isn['’]t|are not|aren['’]t)\s+(?:available|provided|offered)\b",
                        after, re.I))
                if not negated and (re.search(r'\b(?:no|not|without|lacks?|except|unless)\b', before, re.I)
                                    or re.match(r'\s+(?:is\s+|are\s+)?not\b', after, re.I)):
                    continue
                if negated and negative is None:
                    continue
                val = negative if negated else (value(match) if callable(value) else value)
                # Retain context for the actual negation, not just the noun.
                left, right = (start, end) if negated else (match.start(), match.end())
                ambiguity = attribute == 'hvac_type' and val == 'central_ac' and bool(re.search(
                    r'\bwall[- ]mounted split (?:unit|system)\b', sentence, re.I))
                if ambiguity:
                    ambiguous_attributes.add(attribute)
                    if 'ambiguous_central_vs_wall_mounted_split' not in warnings:
                        warnings.append('ambiguous_central_vs_wall_mounted_split')
                add(attribute, val, '/description', description[left:right], 'description_pattern',
                    start=left, end=right, **({'ambiguous_equipment_description': sentence} if ambiguity else {}))

        scan(r'\belevator\b', 'elevator', True, negative=False)
        scan(r'\bwalk[- ]up\b', 'elevator', False)
        scan(r'\b(?:in[- ]unit (?:(?:stacked )?washer(?:\s*(?:and|&|/)\s*dryer)?|laundry)|washer\s*(?:and|&|/)\s*dryer in (?:the |this |your )?(?:unit|apartment))\b',
             'laundry_type', 'in_unit', negative='not:in_unit', unit_specific=True)
        scan(r'\b(?:laundry (?:room |facilities )?in (?:the )?building|on[- ]site laundry)\b',
             'laundry_type', 'in_building', negative='not:in_building')
        scan(r'\b(?:24[- ]hour|full[- ]time) doorman\b', 'doorman_type', 'full_time')
        scan(r'\bpart[- ]time doorman\b', 'doorman_type', 'part_time')
        scan(r'\bvirtual doorman\b', 'doorman_type', 'virtual')
        scan(r'\bdoorman\b', 'doorman_type', 'unspecified', negative='none')
        scan(r'\bcentral (?:air(?: conditioning)?|a/?c)\b', 'hvac_type', 'central_ac', negative='not:central_ac', unit_specific=True)
        scan(r'\b(?:mini[- ]split|ductless)(?: (?:air conditioning|a/?c|system))?\b', 'hvac_type', 'mini_split', negative='not:mini_split', unit_specific=True)
        scan(r'\b(?:window (?:air condition(?:er|ing)s?|a/?c)|through[- ]the[- ]wall (?:air conditioning|a/?c))\b', 'hvac_type', 'room_ac', negative='not:room_ac', unit_specific=True)
        scan(r'\b(?:PTAC|packaged terminal air condition(?:er|ing))\b', 'hvac_type', 'ptac', negative='not:ptac', unit_specific=True)
        scan(r'\bpets\b', 'pet_policy', None, negative='not_allowed')
        scan(r'\b(?:pets (?:are )?(?:allowed|welcome)|pet[- ]friendly)\b', 'pet_policy', 'allowed_restrictions_unknown')
        scan(r'\bpets (?:are )?(?:allowed )?(?:on|upon|subject to) (?:(?:board|owner|landlord) )?approval\b', 'pet_policy', 'approval_required')
        scan(r'\bpets (?:are )?(?:allowed[,]?\s*)?(?:on a |on |a )?case[- ]by[- ]case(?: basis)?\b',
             'pet_policy', 'approval_required')
        # Require the sentence to identify this dwelling: a second-floor gym is
        # not the apartment's floor. Do not infer actual elevation from labeling.
        scan(r'\b(?:this (?:apartment|unit|home)|the apartment|apartment|unit|residence) (?:is (?:located |situated )?|located |situated )?on (?:the )?(\d{1,3})(?:st|nd|rd|th)? floor\b',
             'advertised_floor', lambda m: int(m.group(1)), unit_specific=True)
        named_floor = _named_unit_floor(description)
        if named_floor is not None:
            match, value = named_floor
            start, end = match.span('claim')
            add('advertised_floor', value, '/description', description[start:end],
                'description_pattern', start=start, end=end, rule=NAMED_UNIT_FLOOR_RULE)
        cardinal = r'(?:north(?:ern)?|east(?:ern)?|south(?:ern)?|west(?:ern)?)'
        separator = r'\s*(?:,|/|&|\band\b)\s*'
        for direction in DIRECTIONS:
            coordinated = rf'(?:{cardinal}{separator})*{direction}(?:ern)?(?:{separator}{cardinal})*'
            scan(r'\b' + coordinated + r'[- ](?:facing windows?|facing exposures?|exposures?)\b',
                 'window_exposures.' + direction, True, negative=False, unit_specific=True)
            scan(r'\bwindows? fac(?:e|ing) ' + coordinated + r'\b',
                 'window_exposures.' + direction, True, negative=False, unit_specific=True)
        for view in VIEWS:
            scan(r'\b' + view + r'[- ](?:facing windows?|views?)\b',
                 'view_exposures.' + view, True, negative=False, unit_specific=True)
            scan(r'\b(?:windows? (?:overlooking|fac(?:e|ing))|views? of) (?:the |a )?' + view + r'\b',
                 'view_exposures.' + view, True, negative=False, unit_specific=True)

    # Null values from deliberately narrow pet negation rules are not evidence.
    evidence = [item for item in evidence if item['value'] is not None]
    assertions = defaultdict(list)
    for item in evidence:
        if item['value'] not in assertions[item['attribute']]:
            assertions[item['attribute']].append(item['value'])
    attributes = dict.fromkeys(SCALARS)
    attributes['view_exposures'] = dict.fromkeys(VIEWS)
    attributes['window_exposures'] = dict.fromkeys(DIRECTIONS)
    conflicts = {}
    for attr, values in assertions.items():
        absent = [v[4:] for v in values if isinstance(v, str) and v.startswith('not:')]
        candidates = [v for v in values if not (isinstance(v, str) and v.startswith('not:'))]
        contradicted = any(v in absent for v in candidates)
        if attr == 'doorman_type' and len(candidates) > 1 and 'unspecified' in candidates:
            candidates.remove('unspecified')
        if attr == 'laundry_type' and set(candidates) == {'in_unit', 'in_building'}:
            candidates = ['in_unit']
        if attr == 'pet_policy' and set(candidates) == {'allowed_restrictions_unknown', 'approval_required'}:
            candidates = ['approval_required']
        if len(candidates) > 1 or contradicted or attr in ambiguous_attributes:
            conflicts[attr] = values + (['ambiguous_wall_mounted_split_description'] if attr in ambiguous_attributes else [])
            value = None
        else:
            value = candidates[0] if candidates else None
        if '.' in attr:
            group, leaf = attr.split('.')
            attributes[group][leaf] = value
        else:
            attributes[attr] = value
    return {'version': VERSION, 'attributes': attributes, 'evidence': evidence,
            'conflicts': conflicts, 'warnings': warnings}
