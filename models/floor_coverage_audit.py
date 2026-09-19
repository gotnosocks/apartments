"""Explain selected floor coverage and inventory unmodeled label formats.

This is a source measurement audit. Hypotheses below never alter model floors.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from apartments import floor_label_projection as projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'floor-label-coverage-audit-v1'


def normalized(label):
    return label.strip().removeprefix('#').strip().upper() if label else ''


def family(label):
    value = normalized(label)
    if not value:
        return 'missing_label'
    if re.fullmatch(r'[0-9]+', value):
        return 'numeric_' + str(len(value)) + '_digits'
    if re.fullmatch(r'[0-9]+[A-Z]+', value):
        return 'digits_then_letters'
    if re.fullmatch(r'[A-Z]+[0-9]+[A-Z]*', value):
        return 'letter_prefix'
    return 'other_format'


def hypotheses(label):
    """Named review candidates, not a production extraction rule."""
    value = normalized(label)
    if re.fullmatch(r'[1-9][0-9]{2,3}', value):
        return {'numeric_hundreds': int(value)//100}
    match = re.fullmatch(r'[NS]([1-9][0-9]?)[A-Z]', value)
    if match:
        return {'north_south_wing_prefix': int(match[1])}
    match = re.fullmatch(r'([1-9][0-9]?)(?:FE|FW|RE|RW|FR|RR|FF|RF)', value)
    if match:
        return {'front_rear_suffix': int(match[1])}
    match = re.fullmatch(r'([1-9][0-9]?)(?:ST|ND|RD|TH)(?:FL|FLOOR)', value)
    if match:
        return {'explicit_ordinal_label': int(match[1])}
    return {}


def run(dataset, output):
    dataset, output = Path(dataset), Path(output)
    manifest, files = _verified_bundle(dataset, retain={'observations.jsonl', projection.SIDECAR})
    rows, changes = ([json.loads(line) for line in files[name].decode().split('\n') if line.strip()]
                     for name in ('observations.jsonl', projection.SIDECAR))
    # Reconstruct and hash the complete ordered parent, and replay every v1 rule.
    projection.parent_rows(manifest, rows, changes)
    statuses, missing_families, candidate_counts = Counter(), Counter(), Counter()
    unit_known = defaultdict(set)
    missing, candidates, references = [], [], []
    known = current = current_known = 0
    mixed_capture_labels = conflicting_candidates = missing_labels = 0
    excluded = set(manifest['excluded_buildings'])
    for row, change in zip(rows, changes, strict=True):
        floor = row.get('listed_floor')
        if floor is None:
            floor = row.get('advertised_floor')
        available = floor is not None
        is_current = row['analysis_price_basis'] == 'current_capture_gross_ask'
        known += available; current += is_current; current_known += available and is_current
        unit_known[row['unit_id']].add(available)
        status = row['floor_label_provenance']['status']
        statuses[status] += 1
        captures = change['captures']
        literals = list(dict.fromkeys(c['literal'] for c in captures))
        nonnull = {c['candidate_floor'] for c in captures if c['candidate_floor'] is not None}
        common = {**{k: row[k] for k in ('audit_id', 'source_listing_id', 'unit_id', 'building')},
                  'literal_labels': literals, 'model_floor': floor, 'projection_status': status,
                  'current_capture': is_current,
                  'building_floor_count_limit': row['floor_label_provenance']['building_floor_count_limit']}
        if not available:
            kind = family(literals[0]) if len(literals) == 1 else 'different_literal_labels'
            missing_families[kind] += 1
            mixed_capture_labels += len(literals) > 1
            conflicting_candidates += len(nonnull) > 1
            missing_labels += all(label is None or not label.strip() for label in literals)
            missing.append({**common, 'label_family': kind, 'captures': captures})
        options = [hypotheses(c['literal']) for c in captures]
        if not options or any(o != options[0] for o in options[1:]):
            continue
        for rule, suggested in options[0].items():
            limit = common['building_floor_count_limit']
            guard = ('excluded_building' if row['building'] in excluded else
                     'missing_building_count' if limit is None else
                     'above_building_count' if suggested > limit else 'compatible')
            item = {**common, 'hypothesis': rule, 'candidate_floor': suggested,
                    'existing_building_guard': guard}
            if available:
                # Only explicit-floor rows, not model proxies, are references.
                if status == 'explicit_source_floor':
                    references.append({**item, 'comparison': 'agrees' if floor == suggested else 'disagrees'})
            else:
                candidates.append(item); candidate_counts[rule] += 1
    def grouped(items, key):
        groups = defaultdict(list)
        for item in items:
            groups[item[key]].append(item)
        return {k: {'rows': len(v), 'units': len({r['unit_id'] for r in v}),
            'current_rows': sum(r['current_capture'] for r in v),
            'building_guards': dict(Counter(r['existing_building_guard'] for r in v))}
            for k, v in sorted(groups.items())}
    summary = {'version': VERSION, 'observations': len(rows), 'known_floor_observations': known,
        'known_floor_percent': 100*known/len(rows), 'units': len(unit_known),
        'units_with_any_known_floor': sum(True in v for v in unit_known.values()),
        'units_with_mixed_knownness': sum(len(v) > 1 for v in unit_known.values()),
        'current_observations': current, 'current_known_floor': current_known,
        'statuses': dict(statuses), 'missing_floor_rows': len(missing),
        'missing_label_families': dict(missing_families), 'missing_rows_without_label': missing_labels,
        'missing_rows_with_different_capture_labels': mixed_capture_labels,
        'missing_rows_with_conflicting_numeric_candidates': conflicting_candidates,
        'review_candidates': grouped(candidates, 'hypothesis'),
        'reference_comparisons': dict(Counter(r['hypothesis']+':'+r['comparison'] for r in references)),
        'policy': 'Complete source-bound census. Candidate formats are hypotheses requiring source review, not certified recoveries or a changed analytical dataset. Existing explicit floors are selected source claims, not independent ground truth. Building count compatibility alone does not establish numbering.'}
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'missing.jsonl': ''.join(canonical(r)+'\n' for r in missing),
        'candidates.jsonl': ''.join(canonical(r)+'\n' for r in candidates),
        'reference-comparisons.jsonl': ''.join(canonical(r)+'\n' for r in references),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'source_manifest_sha256': digest(dataset/'complete.json'),
         'source_observations_sha256': manifest['files']['observations.jsonl'],
         'floor_projection_sha256': manifest['files'][projection.SIDECAR]})
    print(canonical(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(**vars(parser.parse_args()))
