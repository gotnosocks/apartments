"""Bounded Oxylabs-only rental pagination with durable, never-retried intents.

No listing-detail requests, archive writes, or market-completeness claims.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile

from apartments import rental_search
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from streeteasy_archive import probe as capture_probe
from streeteasy_archive.oxylabs import _result_item, build_payload
from streeteasy_archive.scope import SEEDS as CONFIGURED_SEEDS

VERSION = 'bounded-rental-discovery-v2'
SEEDS = tuple(url for url in CONFIGURED_SEEDS if url in
              {'https://streeteasy.com' + path for path in rental_search.AREAS})
RAW_FILES = ('request.json', 'response.json', 'body.html', 'extracted.json', 'metadata.json')
CODE_FILES = ('apartments/rental_discovery.py', 'apartments/rental_search.py',
              'apartments/research_pipeline.py', 'apartments/corrections.py',
              'streeteasy_archive/probe.py', 'streeteasy_archive/oxylabs.py',
              'streeteasy_archive/capture.py', 'streeteasy_archive/extract.py',
              'streeteasy_archive/flight.py', 'streeteasy_archive/crawler.py',
              'streeteasy_archive/scope.py')


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n'


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _once(path, data):
    """Exclusive atomic publication, durable before the next side effect."""
    path = Path(path)
    data = data.encode() if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError('Durable record differs: ' + path.name)
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.pending-', delete=False) as handle:
        temp = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temp, path)  # Never replaces an existing ledger record.
        _sync_dir(path.parent)
    finally:
        temp.unlink()


def _implementation_paths():
    return {name: Path(__file__).parents[1] / name for name in CODE_FILES}


def _check_run(root, protocol):
    """Revalidate fixed intent and live/frozen code at each external boundary."""
    if (protocol.get('version') != VERSION or protocol.get('seeds') != list(SEEDS)
            or protocol.get('transport') != 'existing_one_request_oxylabs_probe_html'
            or type(protocol.get('max_requests')) is not int or protocol['max_requests'] < 1
            or type(protocol.get('timeout')) is not int or not 1 <= protocol['timeout'] <= 180
            or not isinstance(protocol.get('preflights'), list)
            or len(protocol['preflights']) > protocol['max_requests']):
        raise ValueError('Invalid frozen protocol seeds/transport/ceiling/timeout')
    expected = _json(protocol).encode()
    for name in ('protocol.json', 'frozen-protocol.json'):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError('Frozen protocol changed')
    hashes = protocol.get('implementation_sha256')
    if not isinstance(hashes, dict) or set(hashes) != set(CODE_FILES):
        raise ValueError('Incomplete frozen implementation hashes')
    for name, live in _implementation_paths().items():
        frozen = root / 'implementation' / name
        if (live.is_symlink() or frozen.is_symlink() or not live.is_file() or not frozen.is_file()
                or digest(live) != hashes[name] or digest(frozen) != hashes[name]):
            raise ValueError('Live or frozen implementation changed: ' + name)


def _hashes(directory):
    return {name: digest(directory / name) for name in RAW_FILES if (directory / name).is_file()}


def _verify_files(directory, hashes):
    for name, expected in hashes.items():
        path = directory / name
        if name not in RAW_FILES or path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Capture integrity failure: ' + name)


def _page(directory, url):
    metadata = json.loads((directory / 'metadata.json').read_text())
    if (metadata.get('url') != url or metadata.get('mode') != 'html'
            or metadata.get('replay') is not None or metadata.get('request_count') != 1):
        raise ValueError('Capture URL, mode, or provider submission contract differs')
    if metadata.get('ok') is not True or metadata.get('api_status') != 200 or metadata.get('target_status') != 200:
        raise ValueError('Capture not successful HTTP 200')
    if json.loads((directory / 'request.json').read_text()) != build_payload(url):
        raise ValueError('Capture request is not the expected Oxylabs payload')
    body = (directory / 'body.html').read_bytes()
    if len(body) != metadata.get('body_bytes'):
        raise ValueError('Capture body size disagrees')
    _, _, status, content = _result_item(json.loads((directory / 'response.json').read_text()))
    content = content.encode() if isinstance(content, str) else content
    if status != 200 or content != body:
        raise ValueError('Saved provider response and body disagree')
    return rental_search.parse_page(body, url, source_clock={
        'capture_started_at': metadata['started_at'], 'elapsed_seconds': metadata['elapsed_seconds'],
        'meaning': 'Provider request clock; not advertisement publication or modification time.'})


def _preflights(bundle):
    if bundle is None:
        return [], None
    bundle = Path(bundle).resolve()
    _, blobs = _verified_bundle(bundle, retain={'pages.jsonl'})
    if 'pages.jsonl' not in blobs:
        raise ValueError('Preflight bundle lacks verified pages')
    entries = []
    for row in (json.loads(line) for line in blobs['pages.jsonl'].decode().split('\n') if line.strip()):
        evidence = row['probe_evidence']
        directory = Path(evidence['directory']).resolve()
        hashes = evidence['file_sha256']
        if set(hashes) != set(RAW_FILES):
            raise ValueError('Incomplete preflight file bindings')
        _verify_files(directory, hashes)
        page = _page(directory, row['source_url'])
        if (row.get('version') != rental_search.VERSION or page['body_sha256'] != row['body_sha256']
                or page['cards'] != row['cards']):
            raise ValueError('Preflight parser/source binding differs')
        entries.append({'url': row['source_url'], 'source_directory': str(directory),
                        'file_sha256': hashes, 'body_sha256': page['body_sha256']})
    # Require a source-backed continuous prefix, rather than letting supplied
    # captures silently authorize arbitrary later pages.
    _pending([_page(Path(e['source_directory']), e['url']) for e in entries])
    return entries, {'path': str(bundle), 'manifest_sha256': digest(bundle / 'complete.json')}


def _pending(pages):
    by_key = {}
    for page in pages:
        key = rental_search._route(page['source_url'])
        if key in by_key:
            raise ValueError('Duplicate seed/page capture')
        by_key[key] = page
    pending, consumed = [], set()
    for seed in SEEDS:
        url = seed
        while True:
            key = rental_search._route(url)
            page = by_key.get(key)
            if page is None:
                pending.append(url)
                break
            if key in consumed:
                raise ValueError('Pagination cycle')
            consumed.add(key)
            url = page['pagination']['next_url']
            if url is None:
                break
    if consumed != set(by_key):
        raise ValueError('Supplied pages do not form observed seed prefixes')
    return pending


def _outcome(directory, intent):
    capture = directory / 'capture'
    saved = directory / 'outcome.json'
    if saved.exists():
        value = json.loads(saved.read_text())
        _verify_files(capture, value['file_sha256'])
        if _hashes(capture) != value['file_sha256']:
            raise ValueError('Capture changed after outcome publication')
        if value['status'] == 'accepted':
            page = _page(capture, intent['url'])
            if page != value['page']:
                raise ValueError('Accepted page replay differs')
        return value
    files = _hashes(capture)
    # The legacy probe closes files but does not fsync them. Make saved evidence
    # durable before recording an outcome or issuing another request.
    _verify_files(capture, files)
    for name in files:
        with (capture / name).open('rb') as handle:
            os.fsync(handle.fileno())
    if capture.exists():
        _sync_dir(capture)
        _sync_dir(directory)
    if 'metadata.json' not in files:
        # Could have been submitted before interruption. Never retry it.
        return {'status': 'uncertain', 'file_sha256': files,
                'reason': 'Intent exists without finalized provider metadata; submission is unknown.'}
    try:
        metadata = json.loads((capture / 'metadata.json').read_text())
        if metadata.get('ok') is not True:
            value = {'status': 'capture_failed', 'file_sha256': files,
                     'error_type': metadata.get('error_type'), 'target_status': metadata.get('target_status')}
        else:
            value = {'status': 'accepted', 'file_sha256': files, 'page': _page(capture, intent['url'])}
    except Exception as exc:
        value = {'status': 'capture_rejected', 'file_sha256': files, 'error_type': type(exc).__name__}
    _once(saved, _json(value))
    return value


def _state(root, protocol):
    pages, attempts = [], []
    for index, entry in enumerate(protocol['preflights'], 1):
        target = root / 'preflights' / f'{index:04d}'
        for name, expected in entry['file_sha256'].items():
            path = target / name
            if not path.exists():
                source = Path(entry['source_directory']) / name
                if digest(source) != expected:
                    raise ValueError('Preflight source changed during copy')
                _once(path, source.read_bytes())
        _verify_files(target, entry['file_sha256'])
        pages.append({**_page(target, entry['url']), 'capture_reference': {
            'run_relative_directory': str(target.relative_to(root)), 'file_sha256': entry['file_sha256']}})
    intents = sorted((root / 'attempts').glob('*/intent.json'))
    for number, path in enumerate(intents, 1):
        intent = json.loads(path.read_text())
        if intent['sequence'] != number or path.parent.name != f'{number:04d}':
            raise ValueError('Noncontiguous request ledger')
        allowed = _pending(pages)
        if attempts and attempts[-1]['outcome']['status'] != 'accepted':
            raise ValueError('Ledger continues after unresolved request')
        if intent['url'] not in allowed or intent['protocol_sha256'] != digest(root / 'protocol.json'):
            raise ValueError('Request intent not authorized by observed pagination')
        outcome = _outcome(path.parent, intent)
        attempts.append({'intent': intent, 'intent_sha256': digest(path), 'outcome': outcome})
        if outcome['status'] == 'accepted':
            pages.append({**outcome['page'], 'capture_reference': {
                'run_relative_directory': str((path.parent / 'capture').relative_to(root)),
                'file_sha256': outcome['file_sha256'], 'intent_sha256': digest(path)}})
    if len(protocol['preflights']) + len(attempts) > protocol['max_requests']:
        raise ValueError('Ledger exceeds request ceiling')
    return pages, attempts


def _publish(root, protocol, pages, attempts, reason):
    _check_run(root, protocol)
    coverage = rental_search.coverage(pages)
    report = {'version': VERSION, 'protocol_sha256': digest(root / 'protocol.json'),
              'stop_reason': reason, 'market_coverage_status': 'unverified',
              'reused_provider_submissions': len(protocol['preflights']),
              'new_request_intents': len(attempts),
              'global_reserved_requests': len(protocol['preflights']) + len(attempts),
              'max_requests': protocol['max_requests'], 'pending_observed_urls': _pending(pages),
              'attempts': attempts, 'preflights': protocol['preflights'],
              'complete_inventory': False}
    key = rental_search.fingerprint({'report': report, 'coverage': coverage})
    target = root / 'reports' / key
    _check_run(root, protocol)
    publish_bundle(target, {'run.json': _json(report), 'coverage.json': _json(coverage),
        'pages.jsonl': ''.join(json.dumps(p, sort_keys=True) + '\n' for p in pages)},
        {'version': VERSION, 'protocol_sha256': report['protocol_sha256'], 'state_sha256': key})
    return {'report_directory': str(target), **report}


def run(output, *, max_requests=None, preflight_bundle=None, resume=False, replay_only=False, timeout=180):
    """Start/resume one immutable protocol; replay_only can never submit requests.

    Ceiling counts reused submissions plus durable new intents. Uncertain or
    failed captures stop the pass permanently; a new run requires explicit review.
    """
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protocol_path = root / 'protocol.json'
        code = {name: digest(path) for name, path in _implementation_paths().items()}
        if resume:
            protocol = json.loads(protocol_path.read_text())
            if (protocol['version'] != VERSION or protocol['implementation_sha256'] != code
                    or (max_requests is not None and max_requests != protocol['max_requests'])
                    or preflight_bundle is not None):
                raise ValueError('Resume protocol differs; use original settings and sources')
        else:
            if any(p.name != '.run.lock' for p in root.iterdir()):
                raise ValueError('New run requires an unused output directory')
            if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 1:
                raise ValueError('An explicit positive request ceiling is required')
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 180:
                raise ValueError('Timeout must be between 1 and 180 seconds')
            entries, bundle = _preflights(preflight_bundle)
            if len(entries) > max_requests:
                raise ValueError('Reused submissions exceed request ceiling')
            protocol = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                        'seeds': list(SEEDS), 'max_requests': max_requests, 'timeout': timeout,
                        'transport': 'existing_one_request_oxylabs_probe_html',
                        'preflights': entries, 'preflight_bundle': bundle, 'implementation_sha256': code}
            for name, source in _implementation_paths().items():
                _once(root / 'implementation' / name, source.read_bytes())
            _once(root / 'frozen-protocol.json', _json(protocol))
            _once(protocol_path, _json(protocol))
        _check_run(root, protocol)
        try:
            while True:
                _check_run(root, protocol)
                pages, attempts = _state(root, protocol)
                pending = _pending(pages)
                if attempts and attempts[-1]['outcome']['status'] != 'accepted':
                    reason = attempts[-1]['outcome']['status']
                elif not pending:
                    reason = 'pagination_pass_finished_inventory_unverified'
                elif len(protocol['preflights']) + len(attempts) >= protocol['max_requests']:
                    reason = 'request_ceiling'
                elif replay_only:
                    reason = 'offline_replay_only'
                else:
                    _check_run(root, protocol)
                    sequence = len(attempts) + 1
                    directory = root / 'attempts' / f'{sequence:04d}'
                    intent = {'sequence': sequence, 'url': pending[0],
                              'protocol_sha256': digest(protocol_path),
                              'recorded_at': datetime.now(timezone.utc).isoformat(),
                              'budget_slot_reserved': True}
                    _once(directory / 'intent.json', _json(intent))
                    _sync_dir(directory.parent)
                    _sync_dir(root)
                    _check_run(root, protocol)
                    capture_probe.probe(intent['url'], 'html', directory / 'capture', timeout=protocol['timeout'])
                    continue
                return _publish(root, protocol, pages, attempts, reason)
        except BaseException:
            # Preserve a reviewable interrupted checkpoint without hiding failure.
            pages, attempts = _state(root, protocol)
            _publish(root, protocol, pages, attempts, 'interrupted_or_error')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-requests', type=int, help='Global ceiling including reused submissions; required for new runs')
    parser.add_argument('--preflight-bundle', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--replay-only', action='store_true')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    result = run(**vars(args))
    print(_json({key: result[key] for key in ('report_directory', 'stop_reason', 'reused_provider_submissions',
                                             'new_request_intents', 'global_reserved_requests', 'complete_inventory')}))


if __name__ == '__main__':
    main()
