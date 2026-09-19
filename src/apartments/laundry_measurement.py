"""Experimental capture-local laundry claims; not yet a fitted measurement.

Keep private equipment, shared facilities and same-floor access separate. Empty
source lists and missing prose never establish absence. This extractor favors
explicit clauses and abstains on ambiguous hallway/location descriptions.
"""
import re

VERSION = 'scoped-laundry-measurement-v4'
SCOPES = ('private', 'shared_building', 'shared_same_floor')
_PAIR = r'(?:washer\s*(?:and|&|/)\s*dryer|washer[-/]dryer)'
_LAUNDRY = r'laundry(?:\s+(?:rooms?|facilities|machines?))?'
_FLOOR = r'(?:each|every|the same|the|your)\s+(?:residential\s+)?floor\b(?!\s+(?:above|below|beneath|over|under|of)\b)'
_CLAUSES = re.compile(r'[^.;!?\n\r<>]+')
_EQUIPMENT = rf'(?:{_PAIR}|washer|dryer|laundry)'
_UNCERTAIN = re.compile(
    rf'\b(?:{_EQUIPMENT})\b[^,;.!?]{{0,35}}\b(?:hook[- ]?ups?|connections?)\b'
    rf'|\b(?:hook[- ]?ups?|connections?)\b[^,;.!?]{{0,35}}\b{_EQUIPMENT}\b'
    rf'|\b(?:may|might|could|can|will|would)\s+(?:be\s+)?(?:install(?:ed)?|add(?:ed)?|include(?:d)?|provid(?:e|ed)|have)\b[^;.!?]{{0,100}}\b{_EQUIPMENT}\b'
    rf'|\b{_EQUIPMENT}\b[^,;.!?]{{0,35}}\b(?:may|might|could|can|will|would)\s+be\s+(?:installed|added|provided|available)\b'
    rf'|\b(?:planned|proposed|coming|future|optional)\s+(?:in[- ]unit\s+)?{_EQUIPMENT}\b'
    rf'|\b{_EQUIPMENT}\b[^,;.!?]{{0,35}}\b(?:coming|planned|proposed)\b'
    rf'|\b(?:permission|permitted|allowed)\s+to\s+install\b[^;.!?]{{0,50}}\b{_EQUIPMENT}\b', re.I)
_INVENTORY = re.compile(r'\b(?:some|select|selected|certain|other|most)\s+(?:of\s+(?:the|our)\s+)?(?:units|apartments|homes|residences)\b', re.I)
_NEGATION = re.compile(r"\b(?:no|not|without|lack(?:s|ing)?|doesn['’]t|isn['’]t|aren['’]t)\b", re.I)


def extract(raw):
    claims, review = [], []
    details = raw.get('propertyDetails')
    details = details if isinstance(details, dict) else {}

    def add(scope, present, literal, path, **extra):
        claims.append({'scope': scope, 'present': present, 'literal': literal,
                       'source_path': path, **extra})

    for section in ('features', 'amenities'):
        value = details.get(section)
        codes = value.get('list', []) if isinstance(value, dict) else value
        if not isinstance(codes, list):
            continue
        for index, code in enumerate(codes):
            if code not in ('WASHER_DRYER', 'LAUNDRY'):
                continue
            path = f'/propertyDetails/{section}' + ('/list' if isinstance(value, dict) else '') + f'/{index}'
            add('private' if code == 'WASHER_DRYER' else 'shared_building', True, code, path,
                method='structured', equipment='washer_dryer' if code == 'WASHER_DRYER' else 'unspecified')

    text = raw.get('description')
    if not isinstance(text, str) or re.fullmatch(r'\s*\$[A-Za-z0-9]+\s*', text):
        text = ''
    positive = [
        ('private', rf'\b(?:in[- ]unit\s+{_PAIR}|{_PAIR}\s+in\s+(?:the |this |your )?(?:unit|apartment))\b'),
        ('shared_building', rf'\b(?:{_LAUNDRY}\s+in\s+(?:the\s+)?building|(?:shared|common|building)\s+{_LAUNDRY})\b'),
        ('shared_same_floor', rf'\b{_LAUNDRY}\s+(?:(?:is|are)\s+)?(?:located\s+|available\s+|right\s+)?on\s+{_FLOOR}'),
        ('shared_same_floor', rf'\blaundry\s+with\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?(?:{_PAIR}|machines?)\s+on\s+{_FLOOR}'),
        # Residents' access to equipment on every floor is a shared claim.
        # Bare equipment "on a floor" could instead be inside a duplex.
        ('shared_same_floor', rf'\bresidents\s+(?:here\s+)?(?:enjoy|have)\s+(?:the\s+convenience\s+of\s+|access\s+to\s+)?(?:a\s+)?{_PAIR}\s+on\s+(?:each|every)\s+(?:residential\s+)?floor\b(?!\s+(?:above|below|beneath|over|under|of)\b)'),
        ('shared_same_floor', rf'\blaundry\s+and\s+(?:a\s+)?roof\s+deck\s+(?:right\s+)?on\s+{_FLOOR}'),
        ('shared_same_floor', rf'\b(?:each|every)\s+(?:residential\s+)?floor\s+(?:has|offers|features)\s+(?:a\s+)?{_LAUNDRY}\b'),
        ('shared_same_floor', rf'\b(?:shared|common|building)\s+{_LAUNDRY}\s+(?:is\s+)?(?:just\s+)?(?:down|across)\s+the\s+hall\b'),
    ]
    negative = [
        ('private', rf'\b(?:no|without)\s+(?:an?\s+)?(?:in[- ]unit\s+(?:{_PAIR}|laundry)|{_PAIR}\s+in\s+(?:the\s+)?(?:unit|apartment))\b'),
        ('shared_building', rf'\bno\s+(?:shared|common|building)\s+{_LAUNDRY}\b|\bno\s+{_LAUNDRY}\s+in\s+(?:the\s+)?building\b'),
        ('shared_building', r'\bno\s+laundry\s+rooms?\s+on[- ]site\b'),
    ]
    for clause in _CLAUSES.finditer(text):
        literal = clause.group()
        if not re.search(r'\b(?:laundry|washer|dryer)\b', literal, re.I):
            continue
        context = {'literal': literal, 'start': clause.start(), 'end': clause.end()}
        if _INVENTORY.search(literal):
            review.append({'kind': 'inventory_scope', **context})
            continue
        if _UNCERTAIN.search(literal):
            review.append({'kind': 'optional_or_uninstalled', **context})
            continue
        if re.search(r'\b(?:except|excluding)\b', literal, re.I):
            review.append({'kind': 'location_exception', **context})
            continue
        denied = set()
        for scope, pattern in negative:
            if re.search(pattern, literal, re.I):
                denied.add(scope)
                add(scope, False, literal, '/description', method='description', start=clause.start(), end=clause.end())
        # A comprehensive explicit denial can establish the none category.
        if re.search(r'\bno\s+laundry\s+(?:anywhere\s+)?(?:on[- ]site|in\s+(?:the\s+)?(?:unit|apartment)\s+or\s+(?:the\s+)?building)\b', literal, re.I):
            for scope in ('private', 'shared_building'):
                if scope not in denied:
                    add(scope, False, literal, '/description', method='description', start=clause.start(), end=clause.end())
                    denied.add(scope)
        if _NEGATION.search(literal):
            if not denied:
                review.append({'kind': 'unresolved_negation_scope', **context})
            continue
        matched = False
        for scope, pattern in positive:
            for match in re.finditer(pattern, literal, re.I):
                start, end = clause.start()+match.start(), clause.start()+match.end()
                add(scope, True, text[start:end], '/description', method='description', start=start, end=end)
                matched = True
        if not matched:
            review.append({'kind': 'unresolved_equipment_or_location', **context})

    values = {scope: {c['present'] for c in claims if c['scope'] == scope} for scope in SCOPES}
    # Derive scope implications while retaining the original literal claims.
    if True in values['shared_same_floor']:
        values['shared_building'].add(True)
    if False in values['shared_building']:
        values['shared_same_floor'].add(False)
    conflicts = [scope for scope in SCOPES if len(values[scope]) > 1]
    states = {scope: next(iter(v)) if len(v) == 1 else None for scope, v in values.items()}
    installation_review = states['private'] is True and any(r['kind'] == 'optional_or_uninstalled' for r in review)
    unresolved_denial = any(r['kind'] == 'unresolved_negation_scope' for r in review)
    if conflicts or installation_review or unresolved_denial:
        category = None
    elif states['private'] is True:
        category = 'in_unit'
    elif states['shared_same_floor'] is True:
        category = 'on_floor'
    elif states['shared_building'] is True:
        category = 'in_building'
    elif states['private'] is False and states['shared_building'] is False:
        category = 'none'
    else:
        category = None
    return {'version': VERSION, 'states': states, 'claims': claims, 'conflicts': conflicts,
            'review': review, 'installation_review_required': installation_review,
            'most_convenient_reported_option': category}
