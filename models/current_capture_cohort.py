"""A new analysis month of current captures on the combined neighbourhood cohort.

`refresh_analysis_cohort` replaces current captures within one month of Chelsea's
reviewed cohort. This module moves the combined cohort
(`rentfrontier.cohort combine`, `combined-neighbourhood-cohort-v1`) to a later
analysis month:

- Every historical row of a month before the new one is kept exactly.
- The parent's current-capture rows (an earlier month's ACTIVE asks) are
  dropped; the new captures replace them.
- New rows come from verified bounded-refresh collections, the same way as
  `refresh_analysis_cohort`:
  - failed refreshes block older successes;
  - selection uses `fit_robust_analysis.current_rows`: ACTIVE captures in the
    analysis month, 0-5 bedrooms, 1-5 baths, $750-50,000;
  - bathrooms come from `bathroom_projection`.
- Each new row's neighbourhood is its discovery seed in the collection's review
  queue (`/for-rent/west-village` is West Village, any other seed Chelsea). It
  must agree with the neighbourhood of the building's earlier rows.
- The floor is the ad's own floor, else its unit label read as
  `rentfrontier.cohort.floor_of` reads it, against the smallest floor count the
  granular crawls' building pages report (`cohort.floor_counts`).
- A row is excluded when its building is not in the registry the feature sets
  read, since there is no location or lot for it.

    python -m models.current_capture_cohort --parent <combined dataset> \
        --collection <collection root> --review-queue <detail-review-queue.jsonl> \
        --registry <buildings.parquet> --granular <crawl> [--granular <crawl>] \
        --output <dir> --as-of <cutoff>
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from apartments.corrections import canonical, instant
from apartments.research_pipeline import digest, publish_bundle
from . import bathroom_projection, fit_robust_analysis, refresh_analysis_cohort as refresh

try:
    from rentfrontier import cohort
except ImportError:  # the frontier package is not installed in the project venv
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontier' / 'src'))
    from rentfrontier import cohort

VERSION = 'combined-current-capture-cohort-v1'
PARENT_VERSION = 'combined-neighbourhood-cohort-v1'
WEST_VILLAGE_SEED = '/for-rent/west-village'
HISTORICAL = 'historical_initial_own_advertisement_ask'
CURRENT = 'current_capture_gross_ask'


def seed_neighbourhoods(queue_rows):
    """source_listing_id -> neighbourhood from each queued ad's discovery seeds."""
    out = {}
    for row in queue_rows:
        seeds = {o.get('seed') for o in row.get('observations') or [] if o.get('seed')}
        names = {'West Village' if WEST_VILLAGE_SEED in urlsplit(s).path else 'Chelsea'
                 for s in seeds}
        if len(names) == 1:
            out[str(row['source_listing_id'])] = names.pop()
        elif names:
            out[str(row['source_listing_id'])] = None  # seeded from both: ambiguous
    return out


def unit_label(url):
    parts = urlsplit(url).path.strip('/').split('/')
    return parts[2] if len(parts) == 3 and parts[0] == 'building' else None


def assemble(parent_rows, candidates, failures, sources, neighbourhoods, registry, counts, *,
             as_of, max_age_days, evidence_of=refresh.capture_evidence):
    cutoff = instant(as_of); month = cutoff.strftime('%Y-%m-01')
    if any(instant(r['known_at']) > cutoff for r in parent_rows if r.get('known_at')):
        raise ValueError('Parent evidence is later than cutoff')
    history, dropped = [], []
    for row in parent_rows:
        if row['analysis_price_basis'] == HISTORICAL and row['period'] < month:
            history.append(row)
        elif row['analysis_price_basis'] == CURRENT and row['period'] < month:
            dropped.append(row['audit_id'])
        else:
            raise ValueError('Parent has rows in or after the new analysis month')
    known = defaultdict(set)
    for row in history:
        known[row['building']].add(row['neighbourhood'])
    units = {row['unit_id'] for row in history}
    available, excluded = refresh.combine_records(candidates, failures, as_of=as_of)
    fresh, selection_exclusions, selection = fit_robust_analysis.current_rows(
        available, as_of=as_of, max_age_days=max_age_days)
    excluded.extend(selection_exclusions)
    evidence, current = [], []
    for row in fresh:
        name = neighbourhoods.get(str(row['source_listing_id']))
        reason = ('no_or_ambiguous_discovery_seed' if name is None
                  else 'seed_disagrees_with_building_neighbourhood'
                  if known[row['building']] - {name}
                  else 'building_not_in_registry' if row['building'] not in registry
                  else None)
        if reason:
            excluded.append({'record': row, 'reason': reason}); continue
        source = evidence_of(row, sources[row['capture_id']])
        projected = bathroom_projection.project({**row, 'period': month}, [source])
        floor, why = cohort.floor_of(
            {'advertised_floor': row.get('advertised_floor')},
            [unit_label(row['canonical_unit_url'])], counts.get(row['building']))
        projected.update(neighbourhood=name, listed_floor=floor,
                         label_derived_floor=floor if why == 'label_proxy' else None,
                         floor_label_provenance={'status': why,
                                                 'building_floor_count': counts.get(row['building'])})
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
        'analysis_month': month, 'dropped_previous_current_rows': len(dropped),
        'current_by_neighbourhood': dict(Counter(r['neighbourhood'] for r in current)),
        'current_new_units': sum(r['unit_id'] not in units for r in current),
        'units': len(buildings), 'buildings': len({r['building'] for r in rows}),
        'historical_rows_preserved_exactly': True, 'selection': selection,
        'exclusions': dict(Counter(e['reason'] for e in excluded)),
        'current_floor_status': dict(Counter(r['floor_label_provenance']['status'] for r in current)),
        'current_bathroom_flags': dict(Counter(
            f for r in current for f in r['bathroom_count_evidence']['flags']))}
    return rows, evidence, excluded, summary, dropped


def run(parent, collections, review_queues, registry, granular, output, *, as_of, max_age_days=1):
    import pyarrow.parquet as pq

    if instant(as_of) > datetime.now(UTC):
        raise ValueError('Analysis cutoff is in the future')
    parent = Path(parent)
    manifest = json.loads((parent / 'complete.json').read_text())
    observations = (parent / 'observations.jsonl').read_bytes()
    if (manifest.get('version') != PARENT_VERSION or manifest['files']['observations.jsonl']
            != hashlib.sha256(observations).hexdigest()):
        raise ValueError('A verified combined neighbourhood cohort is required')
    candidates, failures, sources, bindings = [], [], {}, []
    for root in collections:
        c, f, s, b = refresh.load_collection(root)
        if sources.keys() & s.keys():
            raise ValueError('Collections have overlapping capture identities')
        candidates.extend(c); failures.extend(f); sources.update(s); bindings.append(b)
    neighbourhoods = {}
    for path in review_queues:
        neighbourhoods.update(seed_neighbourhoods(refresh.records(Path(path).read_bytes())))
    names = set(pq.read_table(registry, columns=['building']).column('building').to_pylist())
    counts = {}
    for crawl in granular:
        for building, n in cohort.floor_counts(Path(crawl)).items():
            counts[building] = min(n, counts.get(building, n))
    rows, evidence, excluded, summary, dropped = assemble(
        refresh.records(observations), candidates, failures, sources, neighbourhoods, names, counts,
        as_of=as_of, max_age_days=max_age_days)
    modules = (bathroom_projection, fit_robust_analysis, refresh, cohort)
    paths = [Path(__file__), *(Path(m.__file__) for m in modules)]
    files = {'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows),
        'current-source-evidence.jsonl': ''.join(canonical(r) + '\n' for r in evidence),
        'current-excluded.jsonl': ''.join(canonical(r) + '\n' for r in excluded),
        'summary.json': canonical(summary) + '\n'}
    return publish_bundle(output, files, {'version': VERSION, 'as_of': instant(as_of).isoformat(),
        'parent': str(parent), 'parent_manifest_sha256': digest(parent / 'complete.json'),
        'collections': bindings, 'review_queues': {str(p): digest(Path(p)) for p in review_queues},
        'registry': {'path': str(registry), 'sha256': digest(Path(registry))},
        'granular': {str(g): digest(Path(g) / 'complete.json') for g in granular},
        'max_age_days': float(max_age_days), 'summary': summary, 'dropped_current_audit_ids': dropped,
        'implementation_sha256': {p.name: digest(p) for p in paths},
        'policy': 'Historical rows unchanged; earlier current captures replaced by the new month\'s '
                  'ACTIVE captures. No backward filling, identity merges, model fit or promotion.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--collection', dest='collections', type=Path, action='append', required=True)
    parser.add_argument('--review-queue', dest='review_queues', type=Path, action='append', required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--granular', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--max-age-days', type=float, default=1)
    print(canonical(run(**vars(parser.parse_args()))['summary']))
