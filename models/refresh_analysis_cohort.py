"""Replace current-month evidence while preserving every reviewed historical row.

This deterministic transformation does not fit or select a model. New current
source evidence remains available for review before a Bayesian run is accepted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import candidate_search, corrections, granular_parse, pricing, research_pipeline, robust_pricing
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bathroom_projection, bathroom_evidence_audit, fit_robust_analysis

VERSION = 'capture-refreshed-reviewed-analysis-v1'
PARENT_VERSION = 'reviewed-scope-composition-projection-v2'
COLLECTION_VERSIONS = {'bounded-candidate-refresh-v1', 'bounded-discovery-detail-refresh-v1'}


def records(blob):
    return [json.loads(line) for line in blob.decode().splitlines() if line.strip()]


def hashed(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_collection(root):
    root = Path(root)
    pm, pf = _verified_bundle(root / 'plan', retain={'refresh-plan.json'})
    sm, sf = _verified_bundle(root / 'snapshot', retain={'candidates.jsonl', 'report.json'})
    plan = json.loads(pf['refresh-plan.json']); report = json.loads(sf['report.json'])
    ph = hashed(plan)
    if (plan.get('version') not in COLLECTION_VERSIONS or pm.get('plan_sha256') != ph
            or sm.get('snapshot_version') != 'bounded-refreshed-candidates-v1'
            or sm.get('plan_sha256') != ph or sm.get('report') != report
            or report['targets'] != len(plan['targets'])):
        raise ValueError('Collection plan/snapshot binding differs')
    results = []
    for index, target in enumerate(plan['targets']):
        rm, rf = _verified_bundle(root / 'results' / f'{index:04d}', retain={'result.json'})
        result = json.loads(rf['result.json'])
        if (rm.get('plan_sha256') != ph or rm.get('index') != index
                or rm.get('target_sha256') != hashed(target)
                or result.get('source_listing_id') != target['source_listing_id']
                or result.get('url') != target['url'] or result.get('status') not in {'parsed', 'failed'}):
            raise ValueError('Result differs from collection target')
        if instant(result['interpreted_at']) < instant(result['collected_at']):
            raise ValueError('Result knowledge predates collection')
        results.append(result)
    candidates = records(sf['candidates.jsonl'])
    if [r['candidate'] for r in results if r['status'] == 'parsed'] != candidates:
        raise ValueError('Candidates differ from completed results')
    if (report['parsed'] != len(candidates) or report['failed'] != len(results) - len(candidates)):
        raise ValueError('Collection completion counts differ')
    sources = {}
    for row in candidates:
        capture = row['capture_id']
        if capture in sources:
            raise ValueError('Duplicate collection capture')
        sources[capture] = root
    failures = [r for r in results if r['status'] == 'failed']
    binding = {'plan_sha256': ph, 'plan_manifest_sha256': digest(root / 'plan/complete.json'),
               'snapshot_manifest_sha256': digest(root / 'snapshot/complete.json'),
               'result_manifest_sha256': [digest(root / 'results' / f'{i:04d}' / 'complete.json') for i in range(len(results))]}
    return candidates, failures, sources, binding


def combine_records(candidates, failures, *, as_of):
    """Visible failures block older successes for that ad, without asserting inactivity."""
    cutoff = instant(as_of)
    barriers = defaultdict(list)
    for failure in failures:
        if max(instant(failure['collected_at']), instant(failure['interpreted_at'])) <= cutoff:
            barriers[str(failure['source_listing_id'])].append(failure)
    identities = defaultdict(set)
    for row in candidates:
        if max(instant(row['collected_at']), instant(row['known_at'])) <= cutoff:
            identities[str(row['source_listing_id'])].add((row['unit_id'], row['canonical_unit_url']))
    retained, excluded = [], []
    for row in candidates:
        ad = str(row['source_listing_id'])
        later = [f for f in barriers[ad] if instant(f['collected_at']) >= instant(row['collected_at'])]
        reason = ('advertisement_identity_changed' if len(identities[ad]) > 1
                  else 'later_refresh_failed_no_fallback' if later else None)
        if reason:
            excluded.append({'record': row, 'reason': reason, 'failures': later})
        else:
            retained.append(row)
    return retained, excluded


def capture_evidence(row, root):
    provenance = row['refresh_provenance']; sha = provenance['body_sha256']
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
        raise ValueError('Invalid source body hash')
    body = gzip.decompress((Path(root) / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
    if hashlib.sha256(body).hexdigest() != sha:
        raise ValueError('Current source body changed')
    parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
    raw = parsed.get('raw_listing_json') or ''
    if (str(parsed.get('listing_id')) != str(row['source_listing_id'])
            or parsed.get('canonical_unit_url') != row['canonical_unit_url']
            or hashlib.sha256(raw.encode()).hexdigest() != row['source_raw_sha256']):
        raise ValueError('Current source identity or raw hash differs')
    payload = json.loads(raw)
    return {'capture_id': row['capture_id'], 'unit_id': row['unit_id'],
            'source_listing_id': row['source_listing_id'], 'canonical_unit_url': row['canonical_unit_url'],
            'body_sha256': sha, 'raw_listing_sha256': row['source_raw_sha256'],
            'collected_at': row['collected_at'], 'known_at': row['known_at'],
            'bathroom_fields': bathroom_evidence_audit.reported_bathrooms(payload),
            'description': payload.get('description'),
            'review_findings': bathroom_evidence_audit.screen(payload.get('description'))}


def assemble(parent_rows, candidates, failures, sources, *, as_of, max_age_days):
    cutoff = instant(as_of); month = cutoff.strftime('%Y-%m-01')
    if any(instant(r['known_at']) > cutoff for r in parent_rows):
        raise ValueError('Parent evidence is later than cutoff')
    history, old_current = [], {}
    for row in parent_rows:
        if row['analysis_price_basis'] == 'historical_initial_own_advertisement_ask' and row['period'] < month:
            history.append(row)
        elif row['analysis_price_basis'] == 'current_capture_gross_ask' and row['period'] == month:
            old_current[row['capture_id']] = row
        else:
            raise ValueError('Only same-month refresh of this reviewed cohort is supported')
    available, excluded = combine_records(candidates, failures, as_of=as_of)
    fresh, selection_exclusions, selection = fit_robust_analysis.current_rows(
        available, as_of=as_of, max_age_days=max_age_days)
    excluded.extend(selection_exclusions)
    evidence = []; current = []
    for row in fresh:
        capture = row['capture_id']
        source = capture_evidence(row, sources[capture])
        projected = bathroom_projection.project({**row, 'period': month}, [source])
        if capture in old_current:
            # Never drop an existing review or numeric correction merely because
            # a same-capture projection was rebuilt. Such cases need a new policy.
            old = old_current[capture]
            keys = ('asking_rent', 'bedrooms', 'bathrooms', 'reported_full_bathrooms',
                    'reported_half_bathrooms', 'bathroom_count_evidence')
            if any(old.get(k) != projected.get(k) for k in keys) or old.get('research_review_history'):
                raise ValueError('Existing current review requires explicit reapplication')
        source['audit_id'] = projected['audit_id']
        evidence.append(source); current.append(projected)
    if not current:
        raise ValueError('No eligible current rows')
    rows = sorted(history + current, key=lambda r: (r['period'], r['unit_id']))
    if (len({r['audit_id'] for r in rows}) != len(rows)
            or len({(r['unit_id'], r['period']) for r in rows}) != len(rows)):
        raise ValueError('Duplicate analytical identity or unit-month')
    buildings = defaultdict(set)
    for row in rows:
        buildings[row['unit_id']].add(row['building'])
    if any(len(b) != 1 for b in buildings.values()):
        raise ValueError('Conflicting unit/building identity')
    summary = {'rows': len(rows), 'historical_rows': len(history), 'current_rows': len(current),
        'units': len(buildings), 'buildings': len({r['building'] for r in rows}),
        'historical_rows_preserved_exactly': True, 'selection': selection,
        'exclusions': dict(Counter(e['reason'] for e in excluded)),
        'current_bathroom_flags': dict(Counter(f for r in current for f in r['bathroom_count_evidence']['flags'])),
        'retained_previous_current_captures': sorted(set(old_current) & {r['capture_id'] for r in current}),
        'replaced_previous_current_captures': sorted(set(old_current) - {r['capture_id'] for r in current}),
        'new_current_captures': sorted({r['capture_id'] for r in current} - set(old_current))}
    return rows, evidence, excluded, summary


def run(parent, collections, output, *, as_of, max_age_days=7):
    if instant(as_of) > datetime.now(UTC):
        raise ValueError('Analysis cutoff is in the future')
    pm, pf = _verified_bundle(parent, retain={'observations.jsonl'})
    if pm.get('version') != PARENT_VERSION:
        raise ValueError('Reviewed scope/composition parent required')
    candidates, failures, sources, bindings = [], [], {}, []
    for root in collections:
        c, f, s, b = load_collection(root)
        if sources.keys() & s.keys():
            raise ValueError('Collections have overlapping capture identities')
        candidates.extend(c); failures.extend(f); sources.update(s); bindings.append(b)
    rows, evidence, excluded, summary = assemble(records(pf['observations.jsonl']), candidates, failures,
        sources, as_of=as_of, max_age_days=max_age_days)
    modules = (bathroom_projection, bathroom_evidence_audit, fit_robust_analysis, candidate_search,
               granular_parse, corrections, pricing, robust_pricing, research_pipeline)
    paths = [Path(__file__), *(Path(m.__file__) for m in modules)]
    files = {'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows),
        'current-source-evidence.jsonl': ''.join(canonical(r) + '\n' for r in evidence),
        'current-excluded.jsonl': ''.join(canonical(r) + '\n' for r in excluded),
        'refresh-failures.jsonl': ''.join(canonical(r) + '\n' for r in failures),
        'summary.json': canonical(summary) + '\n', **{p.name: p.read_text() for p in paths}}
    return publish_bundle(output, files, {'version': VERSION, 'as_of': instant(as_of).isoformat(),
        'parent_manifest_sha256': digest(Path(parent) / 'complete.json'),
        'parent_observations_sha256': pm['files']['observations.jsonl'], 'collections': bindings,
        'max_age_days': float(max_age_days), 'summary': summary,
        'implementation_sha256': {p.name: digest(p) for p in paths},
        'review_status': 'current_source_review_pending',
        'policy': 'Same-month current evidence replacement only; historical rows and their review overlays are unchanged. Failed refreshes never resurrect older advertisements. No backward filling, identity merges, model fit or promotion.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--collection', dest='collections', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--max-age-days', type=float, default=7)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
