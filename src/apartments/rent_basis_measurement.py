"""Literal rent-basis research signals; never a price correction or cohort rule.

Descriptions can postdate the historical target. Equality with a quoted amount
is recorded as evidence for review, not proof of the target's economic basis.
"""
from decimal import Decimal
import re

VERSION = 'literal-rent-basis-measurement-v4'
LABEL = r'(?P<label>net(?:[\s-]+effective)?(?:\s+(?:monthly\s+)?(?:rent|price))?|gross(?:\s+(?:monthly\s+)?(?:rent|price))?|legal(?:\s+rent)?)'
MONEY = r'\$\s*(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d{3,6})(?:\.\d{1,2})?)(?!\d|[,.]\d)'
CONNECT = r'(?:\s|[:=–—-]|\b(?:is|of|just|only|at|the|a|an|monthly|per[ \t]+month)\b){0,35}'
AMOUNTS = [re.compile(r'\b'+LABEL+CONNECT+r'(?:\([^()$]{0,100}\)'+CONNECT+r')?'+MONEY, re.I),
           re.compile(MONEY+r'[ \t]*(?:(?:is|per[ \t]+month|a[ \t]+month)[ \t]*)?\(?[ \t]*'+LABEL+r'\b', re.I)]
MENTION = re.compile(r'\bnet(?:[\s-]+effective)?(?:\s+(?:rent|price))?\b|\beffective\s+(?:rent|price)\b', re.I)
STATEMENTS = [
    re.compile(r'\bnet[\s-]+effective\s+(?:rent|price)\s+(?:(?:is|as)\s+)?(?:listed|advertised)\b', re.I),
    re.compile(r'\b(?:advertised|listed)\s+(?:rent|price)\s+(?:(?:is|as|the)\s+)*net(?:[\s-]+effective)?\b', re.I),
    re.compile(r'\b(?:rent|price)\s+(?:is\s+)?(?:advertised|listed)\s+(?:as\s+)?net(?:[\s-]+effective)?\b', re.I),
]
NEGATION = re.compile(r'\b(?:not|never|no|isn[’\x27]t|rather than|instead of)\s+(?:(?:a|an|the)\s+)?$', re.I)
ADMINISTRATIVE = re.compile(r'\b(?:approv\w*|qualif\w*|income|salary|eligib\w*|earn\w*)\b', re.I)


def span(text, match):
    start, end = match.span()
    # Context is diagnostic only; it never changes the literal character offsets.
    context = text[max(0, start-100):min(len(text), end+100)]
    return {'start': start, 'end': end, 'literal': text[start:end], 'context': context,
            'preceded_by_negation': bool(NEGATION.search(text[max(0, start-45):start])),
            'administrative_context': bool(ADMINISTRATIVE.search(context))}


def measure(description, asking_rent):
    if description is None:
        return {'version': VERSION, 'description_available': False, 'mentions': [], 'amounts': [],
                'advertised_net_statements': [], 'target_matches': []}
    if not isinstance(description, str): raise ValueError('Description must be literal text or None')
    target = Decimal(str(asking_rent))
    if not target.is_finite() or target <= 0: raise ValueError('Positive finite target required')
    amounts, used_amounts, used_labels = [], set(), set()
    leading = list(AMOUNTS[0].finditer(description))
    explicit_leading = {m.start('label') for m in leading if re.search(
        r'\b(?:is|of|just|only|at)\b|[:=]', description[m.end('label'):m.start('amount')], re.I)}
    candidates = [(m, 0) for m in leading]+[(m, 1) for m in AMOUNTS[1].finditer(description)]
    for match, direction in sorted(candidates, key=lambda item: (item[0].start(), item[0].end())):
        label_position, amount_position = match.start('label'), match.span('amount')
        # Explicit "net rent is $X" overrides an apparent trailing label on an
        # earlier amount. Otherwise resolve in text order, using each literal
        # label/amount once. This handles both "Gross $X Net $Y" and "$X Gross - $Y Net".
        if direction == 1 and label_position in explicit_leading: continue
        if label_position in used_labels or amount_position in used_amounts: continue
        amount = Decimal(match['amount'].replace(',', ''))
        basis = match['label'].lower().split()[0].split('-')[0]
        used_labels.add(label_position); used_amounts.add(amount_position)
        amounts.append({**span(description, match), 'basis_label': basis, 'amount': float(amount),
                        'equals_analytical_target': amount == target})
    statements = {m.span(): span(description, m) for pattern in STATEMENTS for m in pattern.finditer(description)}
    matches = sorted({a['basis_label'] for a in amounts if a['equals_analytical_target']
                      and not a['preceded_by_negation']})
    return {'version': VERSION, 'description_available': True,
            'mentions': [span(description, m) for m in MENTION.finditer(description)],
            'amounts': sorted(amounts, key=lambda a: (a['start'], a['end'], a['basis_label'])),
            'advertised_net_statements': [statements[k] for k in sorted(statements)],
            'target_matches': matches}
