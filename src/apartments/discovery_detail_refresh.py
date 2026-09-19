"""Collect a verified rental-discovery queue through the bounded Oxylabs executor."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import fcntl
import json
from pathlib import Path
from urllib.parse import urlsplit

from . import candidate_refresh as refresh
from . import rental_search, unit_canonical
from .corrections import canonical
from .research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'bounded-discovery-detail-refresh-v1'


def code_paths():
    return [*refresh._code_paths(), Path(rental_search.__file__), Path(__file__)]


def prepare(review, discovery_report, output, *, max_targets=250):
    if type(max_targets) is not int or not 1 <= max_targets <= 500:
        raise ValueError('Choose an explicit target ceiling from 1 to 500')
    rm, rf = _verified_bundle(review, retain={'detail-review-queue.jsonl'})
    _, df = _verified_bundle(discovery_report, retain={'pages.jsonl'})
    if (rm.get('version') != 'bounded-rental-discovery-review-v1'
            or rm.get('discovery_report_manifest_sha256') != digest(Path(discovery_report) / 'complete.json')):
        raise ValueError('Reviewed queue does not bind the supplied discovery report')
    expected = defaultdict(list)
    for line in df['pages.jsonl'].decode().splitlines():
        page = json.loads(line)
        for card in page['cards']:
            if card['in_chelsea_scope']:
                expected[card['source_listing_id']].append({
                    'seed': page['seed_path'], 'page': page['page'], 'source_url': page['source_url'],
                    'source_clock': page['source_clock'], 'body_sha256': page['body_sha256'],
                    'capture_reference': page['capture_reference'], 'card': card})
    rows = [json.loads(line) for line in rf['detail-review-queue.jsonl'].decode().splitlines()]
    if len({r['source_listing_id'] for r in rows}) != len(rows) or {r['source_listing_id'] for r in rows} != expected.keys():
        raise ValueError('Discovery queue membership differs from in-scope cards')
    if not rows or len(rows) > max_targets:
        raise ValueError(f'Found {len(rows)} targets; choose an explicit ceiling (no silent truncation)')
    targets = []
    for row in sorted(rows, key=lambda r: r['source_listing_id']):
        identifier = row['source_listing_id']
        if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isdecimal() or int(identifier) < 1:
            raise ValueError('Numeric source advertisement ID required')
        observations = expected[identifier]
        urls = sorted({o['card']['canonical_url'] for o in observations})
        hrefs = sorted({o['card']['href'] for o in observations})
        if (row['observations'] != observations or len(urls) != 1
                or row['canonical_unit_url'] != urls[0] or row['observed_detail_urls'] != hrefs):
            raise ValueError('Reviewed detail evidence or identity differs')
        # The legacy review field is a canonicalized DETAIL URL. Nine real queue
        # entries are advertisement routes, not established physical-unit URLs.
        identities = [rental_search._detail_identity(url, identifier) for url in urls]
        units = {i['canonical_unit_url'] for i in identities} - {None}
        buildings = {i['building_path'] for i in identities} - {None}
        if len(units) > 1 or len(buildings) > 1:
            raise ValueError('Conflicting search identity requires review')
        unit = next(iter(units), None)
        targets.append({'source_listing_id': identifier, 'url': 'https://streeteasy.com/rental/' + identifier,
            'canonical_unit_url': unit, 'unit_id': unit_canonical.canonical_unit_id(unit) if unit else None,
            'expected_building_path': next(iter(buildings), None), 'observed_detail_urls': hrefs,
            'discovery_evidence': observations, 'previous_record': {},
            'identity_policy': 'Require advertisement identity and known unit/building path; establish unresolved unit identity only from the detail page canonical link.'})
    paths = code_paths()
    plan = {'version': VERSION, 'review_manifest_sha256': digest(Path(review) / 'complete.json'),
        'discovery_report_manifest_sha256': digest(Path(discovery_report) / 'complete.json'),
        'targets': targets, 'max_targets': max_targets, 'max_provider_submissions': 3 * len(targets),
        'transport': 'oxylabs', 'api_submissions_per_second': 1, 'concurrency': 1, 'render': False,
        'overlay': None, 'implementation_sha256': {p.name: digest(p) for p in paths},
        'scope': 'Detail capture of every in-scope advertisement in the verified discovery queue, regardless of rent, amenities, furnishings or concessions; no URL expansion.',
        'request_route_policy': 'Use the supported /rental/<observed advertisement ID> route to avoid listing turnover on unit landing pages; retain observed search links.',
        'limitations': ['This bounded queue is not a market census; missing search results do not prove inactivity.',
            'Search cards do not establish complete apartment attributes or analytical eligibility.',
            'All successfully parsed source statuses are retained; failures never revive older ACTIVE evidence.',
            'ACTIVE is source-reported at capture, not a guarantee of future availability.',
            'Source attributes remain uncorrected here; apply versioned review overlays before analytical use.']}
    ph = refresh._hash(plan)
    publish_bundle(Path(output) / 'plan', {'refresh-plan.json': canonical(plan) + '\n',
        **{p.name: p.read_text() for p in paths}}, {'version': VERSION, 'plan_sha256': ph})
    return plan, ph


def interpret(target, observation, body, plan_hash, *, interpreted_at, overlay=None):
    if overlay is not None:
        raise ValueError('Discovery detail collection leaves overlays to subsequent projection')
    resolved = dict(target)
    if (not observation['error'] and 200 <= observation['status'] < 300
            and not refresh.is_challenge(body)):
        try:
            parsed, _ = refresh.granular_parse.parse_listing(body, target['url'])
        except (ValueError, TypeError, KeyError):
            parsed = {}
        unit = parsed.get('canonical_unit_url')
        if (str(parsed.get('listing_id')) == target['source_listing_id']
                and not parsed.get('canonical_unit_error') and unit_canonical.unit_page(unit) == unit and unit):
            building_path = '/'.join(urlsplit(unit).path.split('/')[:3])
            expected = target['expected_building_path']
            if (expected is None or expected == building_path) and target['canonical_unit_url'] is None:
                resolved.update(canonical_unit_url=unit, unit_id=unit_canonical.canonical_unit_id(unit))
    result = refresh.interpret(resolved, observation, body, plan_hash, interpreted_at=interpreted_at)
    if result['status'] == 'parsed':
        result['changes'] = {}
        result['change_basis'] = 'initial_verified_detail_capture; search cards are not a prior full attribute record'
        result['candidate']['discovery_provenance'] = {
            'plan_sha256': plan_hash, 'source_listing_id': target['source_listing_id'],
            'expected_canonical_unit_url': target['canonical_unit_url'],
            'unit_identity_established_from_detail': target['canonical_unit_url'] is None,
            'observed_detail_urls': target['observed_detail_urls']}
    return result


async def collect(review, discovery_report, output, *, max_targets=250, max_new_requests=None, fetch=None):
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    if max_new_requests is not None and (type(max_new_requests) is not int or max_new_requests < 1):
        raise ValueError('Optional preflight limit must be a positive integer')
    with (root / '.refresh.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, ph = prepare(review, discovery_report, root, max_targets=max_targets)
        return await refresh.execute_prepared(plan, ph, root, max_new_requests=max_new_requests,
            fetch=fetch, code_paths=code_paths(), interpreter=interpret)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('review', 'discovery_report', 'output'):
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--max-targets', type=int, default=250)
    parser.add_argument('--max-new-requests', type=int)
    parser.add_argument('--plan-only', action='store_true')
    args = vars(parser.parse_args()); plan_only = args.pop('plan_only')
    if plan_only:
        args.pop('max_new_requests')
        plan, ph = prepare(**args)
        print(canonical({'plan_sha256': ph, 'targets': len(plan['targets']),
            'unresolved_unit_identities': sum(t['unit_id'] is None for t in plan['targets']),
            'max_provider_submissions': plan['max_provider_submissions']}))
    else:
        print(canonical(asyncio.run(collect(**args))))
