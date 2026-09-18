"""Conservative, source-bound research projection of advertised interior claims.

These are claims in one advertisement's captured text, not verified physical
attributes. A missing mention is unknown. Any ambiguous candidate or disagreement
between captures makes that feature unknown; no latest-capture rule is applied.
"""
from __future__ import annotations

import hashlib
import math
import re

from apartments.interior_evidence import screen

VERSION = 'advertised-interior-projection-v2'
FEATURES = {
    'ceiling_height': 'advertised_ceiling_feet',
    'levels': 'advertised_levels',
    'floor_through': 'floor_through_mention',
    'skylight': 'skylight_mention',
}
_PLANNED = re.compile(
    r'\b(?:undergoing|under construction|in renovation|renovation in progress|'
    r'currently renovating|pre[- ]renovation|planned renovation|proposed renovation|'
    r'will be renovated|to be renovated|renovations? (?:planned|pending|underway)|'
    r'renovations?\b[^.!?\n]{0,70}\b(?:will|soon|scheduled|expect(?:ed)?)|'
    r'(?:will|soon|scheduled|expect(?:ed)?)\b[^.!?\n]{0,70}\brenovat(?:ed|ion|ions|ing))\b', re.I)
_COMMERCIAL = re.compile(
    r'\b(?:commercial (?:space|lease|property)|retail (?:space|lease|storefront)|'
    r'office (?:space|lease)|storefront|no live[ /-]?work|not (?:for )?residential|'
    r'non[- ]residential|photo (?:shoot|studio)|event (?:space|rental))\b', re.I)
_LOCAL_SHARED = re.compile(
    r'\b(?:lobb(?:y|ies)|galler(?:y|ies)|commercial|retail|office space|showroom|'
    r'atrium|amenity (?:space|floor)|shared|common|residents? lounge|'
    r'fitness|gym|community|building amenities|building features|'
    r'play[ -]?rooms?|recreation(?:al)? (?:rooms?|areas?|spaces?)|rec rooms?|pools?)\b', re.I)
_EXTRA_AMBIGUITY = re.compile(
    r'\b(?:between|around|circa|roughly|approximately|approx|about|nearly|almost|'
    r'up to|over|more than|under|at least|at most|as high as|exceed(?:s|ing)?|'
    r'vary(?:ing)?|varies|maximum|minimum|plus|or more|or less)\b|[+~≈<>≥≤]', re.I)
_DIMENSION = re.compile(
    r'(?:\d[\d.]*\s*(?:feet|foot|ft\.?|inches|inch|in\.?|[\'’′"”″])?\s*[x×]\s*\d|'
    r'\d\s*[x×]\s*$|^\s*[x×]\s*\d)', re.I)
_BOUNDARY = re.compile(r'[;!?\n\r\u2028\u2029]|(?<!\d)\.(?!\d)|<br\s*/?>', re.I)
_MULTIPLE_UNITS = re.compile(
    r'\b(?:floor[ -](?:through|thru)|duplex|triplex|single[- ]level|two[- ]level|three[- ]level)'
    r'\s+(?:apartments|residences|homes|units|penthouses)\b|'
    r'\b(?:apartments|residences|homes|units)\b.{0,65}\b(?:feature|offer|have|include)\b', re.I)
_WINDOW_HEIGHT = re.compile(r'\bfloor[ -]+to[ -]+ceilings?\b', re.I)
_FLOORING = re.compile(r'\b(?:wood|wooden|hardwood|oak|tile|marble|parquet|bamboo)\s+floor[ -]+(?:through|thru)\b', re.I)
_OUTDOOR_LEVELS = re.compile(r'\b(?:roof(?:top)?|garden|terrace|deck|patio|backyard)\b', re.I)
_REVERSE_HEIGHT_GRAMMAR = re.compile(
    r'ceilings?(?:[ \t-]+heights?)?(?:[ \t]+(?:is|are|of|at|measures?))?[ \t:\-–—]*', re.I)
_PRECEDING_MEASUREMENT = re.compile(r'\d\s*(?:feet|foot|ft\.?|[\'’′"”″])\s*$', re.I)
_MALFORMED_MEASUREMENT_SUFFIX = re.compile(r'^\s*[?\'’′"”″]+\s*\d')
_ELEVATION_LEVEL = re.compile(
    r'\b(?:elevated|(?:one|two|three)[ -]+levels?\s+(?:up|above|below|down)|'
    r'(?:above|below|from)\s+(?:the\s+)?(?:ground|street|lobby)\s+(?:level|floor))\b', re.I)
_AMONG_UNITS = re.compile(r'\bamong\s+(?:the\s+)?(?:units|apartments|residences|homes)\b', re.I)


def _local(description, finding):
    start, end = finding['start'], finding['end']
    lower, upper = max(0, start - 220), min(len(description), end + 220)
    before = list(_BOUNDARY.finditer(description, lower, start))
    after = _BOUNDARY.search(description, end, upper)
    return description[before[-1].end() if before else lower:after.start() if after else upper]


def _validate(captures):
    if not isinstance(captures, list):
        raise ValueError('captures must be a list')
    seen = set()
    identities = {key: set() for key in ('audit_id', 'source_listing_id', 'canonical_unit_url', 'unit_id')}
    for capture in captures:
        if not isinstance(capture, dict):
            raise ValueError('Capture must be an object')
        identity = capture.get('capture_id')
        if isinstance(identity, bool) or not isinstance(identity, (int, str)) or str(identity) == '':
            raise ValueError('Capture requires a nonempty string or integer capture_id')
        if str(identity) in seen:
            raise ValueError('Duplicate capture identity')
        seen.add(str(identity))
        for key, values in identities.items():
            if capture.get(key) is not None:
                values.add(str(capture[key]))
                if len(values) > 1:
                    raise ValueError('Captures must describe one analytical row and advertisement')
        description = capture.get('description')
        if not isinstance(description, str):
            raise ValueError('Capture requires literal description text')
        if capture.get('description_sha256') is not None and hashlib.sha256(description.encode()).hexdigest() != capture['description_sha256']:
            raise ValueError('Description hash mismatch')
        # Re-screening the immutable screen enforces complete evidence as well as
        # literal Unicode offsets, measurement slices and advisory flags. A caller
        # cannot suppress a contradictory candidate by deleting one finding.
        if capture.get('findings') != screen(description):
            raise ValueError('Findings do not match source text and frozen screen')


def project(captures: list[dict]) -> dict:
    """Project claims for one analytical row from its same-advertisement captures.

    Audit records can include additional provenance fields; supplied provenance
    is retained in each evidence entry. Unknown captures do not assert absence.
    The caller must bind captures to the authoritative dataset and cutoff before
    calling this pure projection; this function checks their internal identity.
    """
    _validate(captures)
    evidence = []
    for capture in sorted(captures, key=lambda item: str(item['capture_id'])):
        description = capture['description']
        for finding in capture['findings']:
            feature = FEATURES[finding['feature']]
            reasons = set(finding['flags']) - {'room_specific_scope'}
            local = _local(description, finding)
            if _PLANNED.search(description):
                reasons.add('description_planned_feature_ambiguity')
            if _COMMERCIAL.search(description):
                reasons.add('description_nonresidential_scope_ambiguity')
            if _LOCAL_SHARED.search(local):
                reasons.add('local_nonunit_scope_ambiguity')
            if _MULTIPLE_UNITS.search(local):
                reasons.add('additional_multiple_units_scope_ambiguity')
            if _AMONG_UNITS.search(description):
                reasons.add('description_among_multiple_units_scope')
            if finding['feature'] == 'ceiling_height':
                value = finding.get('value_feet')
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or not 5 <= value <= 40
                        or finding.get('measurement_unit') != 'feet'):
                    reasons.add('no_unambiguous_scalar_feet')
                    value = None
                if _EXTRA_AMBIGUITY.search(local):
                    reasons.add('additional_height_bound_or_approximation')
                # Include immediately adjacent syntax even when decimal feet or
                # ft. punctuation created a sentence boundary in the screener.
                measurement_context = description[max(0, finding['measurement_start'] - 28):
                                                  min(len(description), finding['measurement_end'] + 28)]
                if _DIMENSION.search(measurement_context):
                    reasons.add('dimension_not_unambiguous_height')
                if _WINDOW_HEIGHT.search(local):
                    reasons.add('window_height_not_explicit_ceiling_height')
                if finding['start'] < finding['measurement_start']:
                    prefix = description[finding['start']:finding['measurement_start']]
                    if not _REVERSE_HEIGHT_GRAMMAR.fullmatch(prefix):
                        reasons.add('reverse_ceiling_link_not_explicit_height_grammar')
                before_measurement = description[max(0, finding['measurement_start'] - 30):finding['measurement_start']]
                after_measurement = description[finding['measurement_end']:finding['measurement_end'] + 20]
                if (_PRECEDING_MEASUREMENT.search(before_measurement)
                        or _MALFORMED_MEASUREMENT_SUFFIX.search(after_measurement)):
                    reasons.add('adjacent_malformed_or_compound_measurement')
            elif finding['feature'] == 'levels':
                value = finding.get('levels')
                if value not in (1, 2, 3):
                    value = None
                    reasons.add('no_explicit_level_count')
                if _OUTDOOR_LEVELS.search(local):
                    reasons.add('outdoor_vs_interior_level_scope_ambiguity')
                if _ELEVATION_LEVEL.search(local):
                    reasons.add('elevation_not_interior_level_count')
            else:
                value = 1
                if finding['feature'] == 'floor_through' and _FLOORING.search(local):
                    reasons.add('flooring_not_explicit_layout')
            evidence.append({
                'feature': feature,
                'capture_id': capture['capture_id'],
                'provenance': {key: capture[key] for key in (
                    'audit_id', 'source_listing_id', 'canonical_unit_url', 'unit_id',
                    'body_sha256', 'raw_listing_sha256', 'description_sha256',
                    'source_collected_at', 'description_interpreted_at', 'known_at') if key in capture},
                'finding': finding.copy(),
                'candidate_value': value,
                'accepted': not reasons,
                'rejection_reasons': sorted(reasons),
            })
    features, decisions = {}, {}
    for feature in FEATURES.values():
        candidates = [entry for entry in evidence if entry['feature'] == feature]
        accepted = [entry for entry in candidates if entry['accepted']]
        rejected = [entry for entry in candidates if not entry['accepted']]
        values = {entry['candidate_value'] for entry in accepted}
        reasons = sorted({reason for entry in rejected for reason in entry['rejection_reasons']})
        if rejected:
            reasons.append('ambiguous_candidate_present')
        if len(values) > 1:
            reasons.append('conflicting_accepted_values')
        if not candidates:
            reasons.append('unmentioned_unknown')
        value = next(iter(values)) if len(values) == 1 and not rejected else None
        features[feature] = value
        decisions[feature] = {
            'value': value,
            'status': 'advertised_claim' if value is not None else 'unknown',
            'accepted_capture_ids': sorted({entry['capture_id'] for entry in accepted}, key=str),
            'candidate_count': len(candidates),
            'accepted_candidate_count': len(accepted),
            'rejected_candidate_count': len(rejected),
            'reasons': reasons,
        }
    return {'version': VERSION, 'capture_count': len(captures),
            'features': features, 'decisions': decisions, 'evidence': evidence}
