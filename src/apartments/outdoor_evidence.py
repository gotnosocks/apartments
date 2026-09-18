"""Literal outdoor evidence from a single advertisement, without absence inference.

Structured fields assert only explicitly advertised types/presence. Description
matches are review candidates, never physical feature assertions. String offsets
refer to the original description; no HTML or Unicode normalization is applied.
"""
from __future__ import annotations

import re
from bisect import bisect_right

VERSION = 'outdoor-evidence-v1'
CONTEXT_RADIUS = 180
PRIVATE_TYPES = frozenset({'BALCONY', 'GARDEN', 'TERRACE', 'PATIO', 'PRIVATE_ROOF_DECK'})
SHARED_TYPES = frozenset({'ROOF_DECK', 'DECK', 'COURTYARD', 'GARDEN', 'PATIO'})
_OUTDOOR = (r'(?:private\s+roof\s+deck|roof(?:top)?[ -]+deck|roof[ -]*top\s+terrace|'
            r'outdoor\s+(?:space|area)s?|balcon(?:y|ies)|terraces?|patios?|gardens?|'
            r'courtyards?|back[ -]?yards?|decks?)')
_OUTDOOR_RE = re.compile(r'\b' + _OUTDOOR + r'\b', re.I)
_NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_UNITS = r'(?:sq(?:uare)?[. \t-]*(?:feet|foot|ft)[.]?|sf\b|ft[²2])'
_MEASURE = re.compile(rf'(?<![\w.,])(?P<number>{_NUMBER})[ \t-]*(?P<unit>{_UNITS})', re.I)
# Only a short attributive bridge is accepted. In particular "townhouse with a"
# or "living space and" cannot attach an indoor square footage to a terrace.
_AFTER = re.compile(r'^[ \t-]*(?:(?:of|a|an|the|private|shared|common|communal|exclusive|'
                    r'outdoor|landscaped|wraparound|wrap-around|roof|rooftop|total|usable|'
                    r'combined|large|beautiful|enclosed|covered|uncovered|expansive)[ \t-]+){0,5}'
                    r'(?P<outdoor>' + _OUTDOOR + r')\b', re.I)
_BEFORE = re.compile(r'\b(?P<outdoor>' + _OUTDOOR + r')'
                     r'(?:[ \t:,-]+(?:of|is|measures|measuring|has|offers|provides|with|'
                     r'approximately|about|over|nearly|totaling|totalling|spanning|at))'
                     r'{0,3}[ \t:,-]*$', re.I)
_BOUNDARY = re.compile(r'[;!?\n\r\u2028\u2029]|(?<!\d)\.(?!\d)|<br\s*/?>', re.I)
_HEADING = re.compile(r'(?:^|[\n\r.;]|<br\s*/?>)[ \t]*(?P<scope>building amenities|'
                      r'building features|community amenities|shared amenities|'
                      r'apartment features|unit features|home features)[ \t]*:?', re.I)
_FLAGS = [(flag, re.compile(pattern, re.I)) for flag, pattern in (
    ('negation_language', r'\b(?:no|not|without|lacks?|neither|except)\b'),
    ('planned_language', r'\b(?:planned|proposed|future|will|soon|to be|undergoing|under construction)\b'),
    ('hypothetical_language', r'\b(?:may|might|could|would|potential|optional|possible)\b'),
    ('explicit_private_language', r'\b(?:private|exclusive(?:ly)?|sole use)\b'),
    ('building_or_shared_scope', r'\b(?:shared|common|communal|community|building|residents?|rooftop lounge|roof lounge)\b'),
    ('view_or_exposure_language', r'\b(?:views?|overlooks?|overlooking|facing|exposure)\b'),
    ('other_or_multiple_units_scope', r'\b(?:some|select|selected|other|certain|all)\s+(?:units|apartments|homes|residences)\b'),
    ('approximate_or_bound_language', r'\b(?:approximately|approx|about|nearly|almost|up to|over|more than|under|at least)\b'),
    ('area_sum_or_total_language', r'\b(?:total|combined|aggregate|plus|together|including)\b|\+'),
    ('dimensions_language', r'\b\d+(?:\.\d+)?\s*(?:feet|ft|foot|[\'’′])?\s*[x×]\s*\d+'),
)]


def screen(description: str | None, source_path: str = '/description') -> list[dict]:
    """Return reviewable wording/explicit-square-footage candidates.

    No state is inferred from the presence or absence of candidates, and private
    and shared scope flags can both occur. Unflagged wording is not verified unit
    access. Area measurements require a local outdoor noun, not just a mention
    of outdoor space elsewhere in a listing.
    """
    if not isinstance(description, str) or not description:
        return []
    headings = list(_HEADING.finditer(description))
    starts = [item.start() for item in headings]
    candidates = []

    def add(feature, start, end, **extra):
        left, right = max(0, start - CONTEXT_RADIUS), min(len(description), end + CONTEXT_RADIUS)
        preceding = list(_BOUNDARY.finditer(description, left, start))
        local_start = preceding[-1].end() if preceding else left
        following = _BOUNDARY.search(description, end, right)
        local_end = following.start() if following else right
        local = description[local_start:local_end]
        flags = [flag for flag, pattern in _FLAGS if pattern.search(local)]
        heading = bisect_right(starts, start) - 1
        if heading >= 0 and headings[heading].group('scope').lower().startswith(('building', 'community', 'shared')):
            flags.append('shared_section_scope')
        if 'explicit_private_language' in flags and ('building_or_shared_scope' in flags or 'shared_section_scope' in flags):
            flags.append('mixed_private_shared_language')
        result = dict(feature=feature, start=start, end=end, match=description[start:end],
                      context=description[left:right], context_start=left, context_end=right,
                      source_path=source_path, flags=flags, **extra)
        candidates.append(result)
        return result

    for match in _OUTDOOR_RE.finditer(description):
        add('outdoor_wording', match.start(), match.end())
    for measurement in _MEASURE.finditer(description):
        after = _AFTER.search(description[measurement.end():measurement.end() + 100])
        before_start = max(0, measurement.start() - 100)
        before = _BEFORE.search(description[before_start:measurement.start()])
        if after:
            outdoor_start = measurement.end() + after.start('outdoor')
            outdoor_end = measurement.end() + after.end('outdoor')
        elif before:
            outdoor_start = before_start + before.start('outdoor')
            outdoor_end = before_start + before.end('outdoor')
        else:
            continue
        value = float(measurement.group('number').replace(',', ''))
        item = add('outdoor_area', min(measurement.start(), outdoor_start), max(measurement.end(), outdoor_end),
                   value_sqft=value, measurement_start=measurement.start(), measurement_end=measurement.end(),
                   measurement_text=measurement.group(), outdoor_start=outdoor_start, outdoor_end=outdoor_end,
                   outdoor_text=description[outdoor_start:outdoor_end])
        prefix = description[max(0, measurement.start() - 40):measurement.start()]
        range_match = re.search(rf'(?P<first>{_NUMBER})\s*(?:{_UNITS})?\s*(?:[-–—]|\bto)\s*$', prefix, re.I)
        if range_match:
            item['flags'].append('measurement_range')
            item['sqft_values'] = [float(range_match.group('first').replace(',', '')), value]
            item.pop('value_sqft')
        if re.search(r'[-−]\s*$', prefix) and not range_match:
            item['flags'].append('negative_or_dash_prefix')
            item.pop('value_sqft', None)
        if value <= 0 or value > 20000:
            item['flags'].append('unusual_outdoor_area')
    candidates.sort(key=lambda item: (item['start'], item['end'], item['feature']))
    return candidates


def extract(payload: dict | None) -> dict:
    """Extract source-literal outdoor assertions and description candidates.

    Accept either the propertyDetails object or an object containing it. Empty,
    missing or malformed arrays do not establish absence. Unknown codes remain
    visible as type assertions with warnings, without implying known presence.
    """
    result = dict(version=VERSION, assertions=[], description_candidates=[], warnings=[])
    if not isinstance(payload, dict):
        return result
    nested = isinstance(payload.get('propertyDetails'), dict)
    details = payload['propertyDetails'] if nested else payload
    prefix = '/propertyDetails' if nested else ''

    def warning(path, code, literal):
        result['warnings'].append(dict(source_path=path, code=code, literal=literal))

    def array(section, field):
        path = prefix + '/' + section + '/' + field
        container = details.get(section)
        if container is None:
            return path, []
        if not isinstance(container, dict):
            warning(prefix + '/' + section, 'invalid_section_type', container)
            return path, []
        values = container.get(field)
        if values is None:
            return path, []
        if not isinstance(values, list):
            warning(path, 'invalid_array_type', values)
            return path, []
        return path, values

    def assertion(attribute, value, path, literal):
        result['assertions'].append(dict(attribute=attribute, value=value, source_path=path, literal=literal))

    for scope, section, field, known in (
        ('private', 'features', 'privateOutdoorSpaceTypes', PRIVATE_TYPES),
        ('shared', 'amenities', 'sharedOutdoorSpaceTypes', SHARED_TYPES),
    ):
        path, values = array(section, field)
        for index, value in enumerate(values):
            item_path = path + '/' + str(index)
            if not isinstance(value, str) or not value:
                warning(item_path, 'invalid_type_code', value)
                continue
            assertion(scope + '_type', value, item_path, value)
            if value in known:
                assertion(scope + '_outdoor', True, item_path, value)
            else:
                warning(item_path, 'unknown_type_code', value)
        list_path, items = array(section, 'list')
        marker = scope.upper() + '_OUTDOOR_SPACE'
        for index, value in enumerate(items):
            if value == marker:
                assertion(scope + '_outdoor', True, list_path + '/' + str(index), value)
    description = details.get('description')
    description_path = prefix + '/description'
    if nested and not isinstance(description, str) and isinstance(payload.get('description'), str):
        description, description_path = payload['description'], '/description'
    result['description_candidates'] = screen(description, description_path)
    return result
