"""Command-line workflows. Every writer locks before opening the archive."""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import math
import sys
import time
from pathlib import Path

from .crawler import approved_links, is_challenge
from .extract import canonical_url, extract, kind_for
from .store import ArchiveStore


def acquire_lock(data):
    import fcntl
    path = Path(data)
    path.mkdir(parents=True, exist_ok=True)
    lock = (path / 'crawler.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except OSError:
        lock.close()
        print('another archive writer is active', file=sys.stderr)
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(prog='streeteasy-archive')
    parser.add_argument('--data', default='data', help='archive directory (default: ./data)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('backfill', 'update', 'resume'):
        command = sub.add_parser(name)
        command.add_argument('--transport', choices=('http', 'firefox'))
        command.add_argument('--firefox-binary')
        command.add_argument('--neighborhood', choices=('chelsea',), help='persistent Chelsea + West Chelsea scope, excluding Hudson Yards')
        command.add_argument('--delay', type=float, help='average delay seconds; randomized half to 1.5 times this value')
        command.add_argument('--wait-for-cooldown', action='store_true', help='wait for an existing cooldown once; a new challenge still exits')
        command.add_argument('--building', help='restrict this run to a building URL and child detail URLs; repeat on resume')
        command.add_argument('--max-requests', type=int, default=0, help='request budget; zero is unlimited')
        command.add_argument('--revisit-interval', type=float, default=0, help='update interval in seconds for known buildings/listings')
    sub.add_parser('status').add_argument('--generation', type=int)
    sub.add_parser('serve').add_argument('--port', type=int, default=8765)
    sub.add_parser('import-har').add_argument('path')
    export_parser = sub.add_parser('export')
    export_parser.add_argument('path')
    export_parser.add_argument('--generation', type=int)
    export_parser.add_argument('--offline-reextract', action='store_true')
    args = parser.parse_args(argv)
    if getattr(args, 'max_requests', 0) < 0 or getattr(args, 'revisit_interval', 0) < 0 or not math.isfinite(getattr(args, 'revisit_interval', 0)):
        parser.error('request budget and interval must be finite nonnegative numbers')
    if args.command == 'serve':
        if not 1 <= args.port <= 65535:
            parser.error('port must be between 1 and 65535')
        from .web import create_app
        from waitress import serve
        print(f'Archive browser: http://127.0.0.1:{args.port}', flush=True)
        serve(create_app(args.data), host='127.0.0.1', port=args.port, threads=4)
        return 0
    lock = None
    if args.command not in ('status', 'export'):
        lock = acquire_lock(args.data)
        if lock is None:
            return 2
    store = None
    try:
        store = ArchiveStore(args.data)
        generation = store.current_generation()
        if args.command == 'status':
            print(json.dumps(store.status(args.generation), indent=2))
            return 0
        if args.command == 'import-har':
            return import_har(store, args.path)
        if args.command == 'export':
            return export(store, args.generation, args.path, args.offline_reextract)
        previous_profile = store.db.execute('SELECT value FROM metadata WHERE key=?', (f'crawl_profile:{generation}',)).fetchone()
        if args.command == 'update':
            generation = store.new_generation('update')
            store.seed(generation)
            store.revisit_known(generation, args.revisit_interval)
        elif generation is None:
            if args.command == 'resume':
                raise ValueError('no existing crawl; start with backfill or import-har')
            generation = store.new_generation('backfill')
            store.seed(generation)
        profile_key = f'crawl_profile:{generation}'
        row = store.db.execute('SELECT value FROM metadata WHERE key=?', (profile_key,)).fetchone()
        profile = json.loads(row[0]) if row else json.loads(previous_profile[0]) if previous_profile else {}
        args.neighborhood = args.neighborhood or profile.get('neighborhood')
        args.transport = args.transport or profile.get('transport', 'firefox' if args.neighborhood else 'http')
        args.delay = args.delay if args.delay is not None else profile.get('delay', 60 if args.neighborhood else 10)
        if not math.isfinite(args.delay) or args.delay < 10:
            raise ValueError('--delay must be finite and at least 10 seconds')
        if args.neighborhood and args.building:
            raise ValueError('use either --neighborhood or --building')
        if args.neighborhood:
            from .scope import configure
            configure(store, generation)
            with store._tx():
                store.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (profile_key, json.dumps({'neighborhood': args.neighborhood, 'transport': args.transport, 'delay': args.delay})))
        if args.building:
            building = canonical_url(args.building)
            if not building or kind_for(building) != 'building':
                raise ValueError('--building requires a StreetEasy building page URL')
            args.building = building.rstrip('/')
            store.enqueue(generation, [{'url': args.building, 'kind': 'building'}])
        state = store.status(generation)
        while args.wait_for_cooldown and state['cooldown'] and state['cooldown'] > time.time():
            print(f"Waiting for cooldown until {state['cooldown']}; no site requests", flush=True)
            time.sleep(min(60, state['cooldown'] - time.time()))
            state = store.status(generation)
        if state['cooldown'] and state['cooldown'] > time.time():
            print(json.dumps(state, indent=2))
            print('crawl is cooling down; resume after the reported UTC epoch timestamp', file=sys.stderr)
            return 3
        if not state['pending'] and not state['inflight']:
            store.finish(generation)
            print(json.dumps(store.status(generation), indent=2))
            return 0
        store.recover_inflight(generation)
        store.close()
        store = None
        return run_crawler(args, generation, lock)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()
        if lock is not None:
            lock.close()


def import_har(store, path):
    doc = json.loads(Path(path).read_text())
    generation = store.current_generation()
    if generation is None:
        generation = store.new_generation('backfill')
        store.seed(generation)
    imported = skipped = 0
    for entry in doc.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        response = entry.get('response', {})
        url = canonical_url(request.get('url', ''))
        if not url or (not kind_for(url) and url != 'https://streeteasy.com/'):
            skipped += 1
            continue
        content = response.get('content', {})
        if 'text' not in content:
            skipped += 1
            continue
        raw = base64.b64decode(content['text'], validate=True) if content.get('encoding') == 'base64' else content['text'].encode('utf-8')
        status = int(response.get('status', 0))
        capture = entry.get('startedDateTime')
        try:
            fetched = datetime.datetime.fromisoformat(capture.replace('Z', '+00:00')).timestamp() if capture else None
        except (ValueError, AttributeError):
            fetched = None
        fingerprint = hashlib.sha256(json.dumps([request.get('method'), url, capture, status,
                                                hashlib.sha256(raw).hexdigest()]).encode()).hexdigest()
        if store.db.execute('SELECT 1 FROM har_entries WHERE fingerprint=?', (fingerprint,)).fetchone():
            skipped += 1
            continue
        headers = {h['name']: h.get('value', '') for h in response.get('headers', []) if h.get('name')}
        content_type = content.get('mimeType', '')
        if status == 304:
            previous = store.latest_response(url)
            if previous is None:
                skipped += 1
                continue
            raw = store.get_body(previous['body_hash'])
            content_type = content_type or previous['content_type'] or ''
        error = None
        if not (200 <= status < 300 or status == 304) or is_challenge(raw):
            error = f'HAR HTTP {status} or challenge coverage gap'
        try:
            data = extract(raw, url, content_type)
        except Exception as exc:
            data = {'extraction_version': 1, 'url': url, 'links': [], 'error': str(exc)}
            error = f'HAR parser coverage gap: {exc}'
        # Do not alter live queue/validators when adding an older capture.
        previous = store.latest_response(url)
        if previous is None or fetched is None or fetched >= previous['fetched']:
            store.enqueue(generation, [{'url': url, 'kind': kind_for(url) or 'homepage'}])
        store.record(generation, url, status, headers, raw, content_type, data,
                     error=error, discovered=approved_links(data['links'], url) if error is None else [],
                     fetched=fetched, har_fingerprint=fingerprint)
        imported += 1
    store.finish(generation)
    print(json.dumps({'generation': generation, 'imported': imported, 'skipped': skipped}))
    return 0


def export(store, generation, path, offline):
    generations = [generation] if generation else [r[0] for r in store.db.execute('SELECT id FROM generations ORDER BY id')]
    output = Path(path).resolve()
    if (output.parent == store.root and (output.name.startswith('archive.sqlite3') or output.name == 'crawler.lock')) or store.root / 'bodies' in output.parents:
        raise ValueError('export destination must not overwrite archive storage')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as out:
        for gen in generations:
            for row in store.observations(gen):
                data = None
                if row['body_hash']:
                    snap = store.db.execute('SELECT extracted FROM snapshots WHERE generation=? AND url=? AND body_hash=?',
                                            (gen, row['url'], row['body_hash'])).fetchone()
                    if snap and not offline:
                        data = json.loads(snap[0])
                    else:
                        try:
                            data = extract(store.get_body(row['body_hash']), row['url'], row['content_type'] or '')
                        except Exception as exc:
                            data = {'error': str(exc)}
                item = dict(row)
                item['headers'] = json.loads(item['headers'])
                item['body_sha256'] = item.pop('body_hash')
                item['body_path'] = str(store.body_path(item['body_sha256']).relative_to(store.root)) if item['body_sha256'] else None
                item['extraction'] = data
                out.write(json.dumps(item, ensure_ascii=False) + '\n')
    return 0


def run_crawler(args, generation, lock=None):
    from scrapy.crawler import CrawlerProcess
    from .crawler import ArchiveSpider
    settings = {'LOG_LEVEL': 'INFO'}
    if args.transport == 'firefox':
        settings['DOWNLOAD_HANDLERS'] = {'https': 'streeteasy_archive.browser.FirefoxDownloadHandler'}
        settings['ARCHIVE_FIREFOX_BINARY'] = args.firefox_binary
    process = CrawlerProcess(settings=settings)
    errors = []
    crawler = process.create_crawler(ArchiveSpider)
    deferred = process.crawl(crawler, data_dir=args.data, generation=generation, max_requests=args.max_requests, building=args.building, neighborhood=args.neighborhood, delay=args.delay)
    deferred.addErrback(lambda failure: errors.append(str(failure)))
    process.start()
    store = ArchiveStore(args.data)
    try:
        state = store.status(generation)
        print(json.dumps(state, indent=2))
    finally:
        store.close()
    if errors or crawler.stats.get_value('spider_exceptions/count', 0):
        print('\n'.join(errors) or 'crawler callback failed; resume after fixing the error', file=sys.stderr)
        return 2
    return 3 if state['status'] == 'paused' else 0


if __name__ == '__main__':
    sys.exit(main())
