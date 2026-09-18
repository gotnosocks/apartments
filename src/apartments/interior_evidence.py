"""Review-only interior-language candidates from one captured advertisement.

Matches are not unit attributes. In particular, absence of a match is unknown,
and even unflagged matches require scope review. Offsets address the original
Unicode string, without HTML decoding, whitespace normalization or case folding.
"""
from __future__ import annotations

import re
from bisect import bisect_right

VERSION = 'interior-evidence-screen-v1'
CONTEXT_RADIUS = 180

_NUMBER = r'\d{1,3}(?:\.\d{1,2})?'
_FOOT = r"(?:feet\b|foot\b|ft\b\.?|['’′])"
_INCH = r'(?:inches\b|inch\b|in\b\.?|["”″])'
_UNIT = rf'(?:{_FOOT}|{_INCH})'
_DASH = r'[-–—−]'
_UNIT_JOIN = r'[ \t\-–—]*'
_MEASUREMENT = (
    rf'(?<![\w.]){_NUMBER}(?:{_UNIT_JOIN}{_UNIT})?\s*'
    rf'(?:{_DASH}|\bto\b)\s*{_NUMBER}{_UNIT_JOIN}{_UNIT}'
    rf'|(?<![\w.]){_NUMBER}{_UNIT_JOIN}{_FOOT}\s*{_NUMBER}{_UNIT_JOIN}{_INCH}'
    rf'|(?<![\w.]){_NUMBER}{_UNIT_JOIN}{_UNIT}'
)
_MEASUREMENT_RE = re.compile(_MEASUREMENT, re.I)
_FOOT_RE = re.compile(_FOOT, re.I)
_INCH_RE = re.compile(_INCH, re.I)
_NUMBER_RE = re.compile(_NUMBER)
# Bounded joins prevent an unrelated dimension elsewhere in the description
# from attaching to "ceiling" and avoid scans proportional to whole documents.
_CEILING_AFTER = re.compile(r'^[ \t\-–—]*(?:[A-Za-z]+[ \t\-–—]+){0,4}ceilings?\b', re.I)
_CEILING_BEFORE = re.compile(r'\bceilings?(?:[ \t\-–—:]+[A-Za-z]+){0,4}[ \t\-–—:]*$', re.I)
_FEATURES = (
    ('levels', re.compile(r'\b(?:duplex(?:es)?|triplex(?:es)?|(?:multi|single|one|two|three)[ \t\-–—]+level(?:s|ed)?)\b', re.I)),
    ('floor_through', re.compile(r'\bfloor[ \t\-–—]+(?:through|thru)\b', re.I)),
    ('skylight', re.compile(r'\b(?:skylights?|skylit|sky[ \t\-–—]+lights?|sky[ \t\-–—]+lit)\b', re.I)),
)
_HEADING = re.compile(
    r'(?:^|[\n\r.;]|<br\s*/?>)[ \t]*'
    r'(?P<scope>building amenities|building features|community amenities|shared amenities|'
    r'apartment features|unit features|home features)[ \t]*:?', re.I)
_BOUNDARY = re.compile(r'[;.!?\n\r\u2028\u2029]|<br\s*/?>', re.I)
_FLAGS = (
    ('negation_language', r'\b(?:no|not|without|lacks?|neither|except|unless)\b'),
    ('hypothetical_language', r'\b(?:may|might|could|would|potential|option(?:al)?|possib(?:le|ility)|convert(?:ible)?|conversion)\b'),
    ('planned_language', r'\b(?:planned|proposed|future|undergoing|renovat(?:e|ed|ion|ions|ing)|will|soon|to be|pre[- ]renovation)\b'),
    ('building_or_shared_scope', r'\b(?:lobby|lobbies|gym|fitness|shared|common|community|residents? lounge|building amenities|building features)\b'),
    ('other_or_multiple_units_scope', r'\b(?:some|many|select|selected|certain|other|most)\b.{0,35}\b(?:units|homes|residences|apartments|penthouses)\b|\b(?:duplexes|triplexes)\b|\b(?:duplex|triplex)\s+(?:penthouses|apartments|units|residences|homes)\b|\b(?:units|homes|residences|apartments|penthouses)\s+(?:available|feature|offer)\b'),
    ('room_specific_scope', r'\b(?:living[ -]?room|bedroom|kitchen|bathroom|dining[ -]?room|foyer|mezzanine)\b'),
    ('approximate_or_bound_language', r'\b(?:approximately|approx|about|nearly|almost|up to|over|more than|under|at least|as high as)\b'),
)
_FLAG_PATTERNS = [(flag, re.compile(pattern, re.I)) for flag, pattern in _FLAGS]


def screen(description: str | None) -> list[dict]:
    """Return deterministic literal candidates; never resolve physical features.

    ``value_feet`` exists only for scalar explicit feet; ``feet_values`` retains
    range endpoints. Inches and mixed-unit strings are retained for review and
    never silently reinterpreted as feet. Flags are advisory: their absence is
    not evidence of correct unit scope, present-day condition or positive polarity.
    """
    if not isinstance(description, str) or not description:
        return []
    headings = list(_HEADING.finditer(description))
    heading_starts = [heading.start() for heading in headings]
    candidates = []

    def add(feature, start, end, **extra):
        left, right = max(0, start - CONTEXT_RADIUS), min(len(description), end + CONTEXT_RADIUS)
        # Advisory scope uses the local sentence, bounded on either side. The
        # returned context remains wider so a reviewer can inspect exclusions.
        preceding = list(_BOUNDARY.finditer(description, left, start))
        local_start = preceding[-1].end() if preceding else left
        following = _BOUNDARY.search(description, end, right)
        local_end = following.start() if following else right
        local = description[local_start:local_end]
        flags = [flag for flag, pattern in _FLAG_PATTERNS if pattern.search(local)]
        prior_index = bisect_right(heading_starts, start) - 1
        if prior_index >= 0 and headings[prior_index].group('scope').lower().startswith(('building', 'community', 'shared')):
            flags.append('shared_section_scope')
        item = dict(feature=feature, start=start, end=end, match=description[start:end],
                    context=description[left:right], context_start=left, context_end=right,
                    source_path='/description', flags=flags, **extra)
        candidates.append(item)
        return item

    for measurement in _MEASUREMENT_RE.finditer(description):
        after = _CEILING_AFTER.search(description[measurement.end():measurement.end() + 75])
        before_start = max(0, measurement.start() - 75)
        before = _CEILING_BEFORE.search(description[before_start:measurement.start()])
        if not after and not before:
            continue
        start = measurement.start() if after else before_start + before.start()
        end = measurement.end() + after.end() if after else measurement.end()
        literal = measurement.group()
        numbers = [float(value) for value in _NUMBER_RE.findall(literal)]
        has_inches = bool(_INCH_RE.search(literal))
        has_feet = bool(_FOOT_RE.search(literal))
        item = add('ceiling_height', start, end, measurement_text=literal,
                   measurement_start=measurement.start(), measurement_end=measurement.end(),
                   measurement_unit='mixed' if has_inches and has_feet else 'inches' if has_inches else 'feet')
        if has_inches:
            item['flags'].append('mixed_units_review_required' if has_feet else 'inch_units_not_feet')
        else:
            item['feet_values'] = numbers
            if len(numbers) == 1:
                item['value_feet'] = numbers[0]
            else:
                item['flags'].append('measurement_range')
            if any(value < 5 or value > 40 for value in numbers):
                item['flags'].append('unusual_ceiling_height')
    for feature, pattern in _FEATURES:
        for match in pattern.finditer(description):
            extra = {}
            if feature == 'levels':
                token = match.group().lower()
                if token.startswith(('single', 'one')):
                    extra['levels'] = 1
                elif token.startswith(('duplex', 'two')):
                    extra['levels'] = 2
                elif token.startswith(('triplex', 'three')):
                    extra['levels'] = 3
            add(feature, match.start(), match.end(), **extra)
    heights = {tuple(item['feet_values']) for item in candidates if 'feet_values' in item}
    if len(heights) > 1:
        for item in candidates:
            if item['feature'] == 'ceiling_height':
                item['flags'].append('differing_height_candidates')
    candidates.sort(key=lambda item: (item['start'], item['end'], item['feature']))
    return candidates
