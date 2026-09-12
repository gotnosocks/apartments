"""SQLite frontier and an append-only, content-addressed response archive."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SENSITIVE = {'cookie', 'set-cookie', 'authorization', 'proxy-authorization',
             'www-authenticate', 'x-api-key'}


def _headers(value):
    return {str(k): v for k, v in (value or {}).items() if str(k).lower() not in SENSITIVE}


def building_coverage(db, generation):
    """Separate building resources, inventory intents, and URL queue bookkeeping."""
    import re
    rows = db.execute('''SELECT f.url,f.kind,f.state,EXISTS(SELECT 1 FROM observations o
        WHERE o.generation=f.generation AND o.url=f.url AND o.error IS NULL
        AND o.body_hash IS NOT NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304)) captured
        FROM frontier f WHERE f.generation=? AND f.kind IN ('building','inventory')''', (generation,)).fetchall()
    return {
        'known_scope_roots': db.execute('SELECT count(*) FROM scope_buildings WHERE generation=?', (generation,)).fetchone()[0],
        'main_pages_captured': sum(bool(captured) for url, kind, state, captured in rows
                                   if re.fullmatch(r'https://streeteasy.com/building/[^/?#]+', url)),
        'expanded_inventories_captured': sum(bool(captured) for url, kind, state, captured in rows if kind == 'inventory'),
        'building_urls_done': sum(state == 'done' for url, kind, state, captured in rows if kind == 'building'),
        'building_urls_superseded': sum(state == 'superseded' for url, kind, state, captured in rows if kind == 'building'),
    }


class ArchiveStore:
    def __init__(self, data_dir='data'):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'bodies').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'archive.sqlite3', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS generations(id INTEGER PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active', cooldown REAL);
        CREATE TABLE IF NOT EXISTS frontier(generation INTEGER NOT NULL, url TEXT NOT NULL, kind TEXT, lastmod TEXT, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, etag TEXT, modified TEXT, PRIMARY KEY(generation,url));
        CREATE INDEX IF NOT EXISTS frontier_ready ON frontier(generation,state,next_attempt);
        CREATE TABLE IF NOT EXISTS bodies(hash TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, url TEXT NOT NULL, fetched REAL NOT NULL, status INTEGER, content_type TEXT, headers TEXT NOT NULL, body_hash TEXT, not_modified INTEGER NOT NULL DEFAULT 0, error TEXT);
        CREATE INDEX IF NOT EXISTS observations_url ON observations(url,id);
        CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, url TEXT NOT NULL, body_hash TEXT NOT NULL, observed REAL NOT NULL, extraction_version INTEGER, extracted TEXT, UNIQUE(generation,url,body_hash));
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scope_urls(generation INTEGER NOT NULL, url TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(generation,url));
        CREATE TABLE IF NOT EXISTS scope_buildings(generation INTEGER NOT NULL, url TEXT NOT NULL, PRIMARY KEY(generation,url));
        CREATE TABLE IF NOT EXISTS url_aliases(generation INTEGER NOT NULL, url TEXT NOT NULL, target_url TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(generation,url));
        CREATE TABLE IF NOT EXISTS har_entries(fingerprint TEXT PRIMARY KEY);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_xinfo(frontier)')}
        if 'priority' not in columns:
            self.db.execute("ALTER TABLE frontier ADD COLUMN priority INTEGER GENERATED ALWAYS AS (CASE kind WHEN 'listing' THEN 0 WHEN 'sitemap' THEN 1 WHEN 'search' THEN 3 ELSE 2 END) VIRTUAL")
        self.db.execute('CREATE INDEX IF NOT EXISTS frontier_priority ON frontier(generation,state,priority)')
        self.db.commit()

    def close(self):
        self.db.close()

    @contextmanager
    def _tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def current_generation(self):
        row = self.db.execute('SELECT id FROM generations ORDER BY id DESC LIMIT 1').fetchone()
        return row[0] if row else None

    def new_generation(self, name='backfill'):
        with self._tx():
            row = self.db.execute("SELECT generation FROM frontier WHERE state IN ('pending','inflight') LIMIT 1").fetchone()
            if row:
                raise RuntimeError(f'generation {row[0]} still has queued work; resume it first')
            row = self.db.execute('SELECT id FROM generations WHERE cooldown>? LIMIT 1', (time.time(),)).fetchone()
            if row:
                raise RuntimeError(f'generation {row[0]} is cooling down; resume it later')
            self.db.execute("UPDATE generations SET status='complete'")
            return self.db.execute('INSERT INTO generations(name,created) VALUES(?,?)', (name, time.time())).lastrowid

    def _remember_alias(self, generation, url, target_url, reason='canonical URL normalization'):
        """Keep the discovered spelling and transfer scope, without fabricating a fetch."""
        self.db.execute('INSERT OR IGNORE INTO url_aliases VALUES(?,?,?,?,?)',
                        (generation, url, target_url, reason, time.time()))
        self.db.execute('''INSERT OR IGNORE INTO scope_urls(generation,url,reason)
            SELECT generation,?,reason FROM scope_urls WHERE generation=? AND url=?''',
            (target_url, generation, url))

    def _enqueue(self, generation, items):
        from .extract import canonical_url
        for item in items:
            original = item['url']
            url = canonical_url(original) or original
            if url != original:
                self._remember_alias(generation, original, url)
            self.db.execute('''INSERT INTO frontier(generation,url,kind,lastmod) VALUES(?,?,?,?)
                ON CONFLICT(generation,url) DO UPDATE SET
                state=CASE WHEN frontier.state='deferred' AND excluded.lastmod IS NOT NULL
                    AND excluded.lastmod IS NOT frontier.lastmod THEN 'pending' ELSE frontier.state END,
                kind=COALESCE(excluded.kind,frontier.kind),
                lastmod=COALESCE(excluded.lastmod,frontier.lastmod)''',
                (generation, url, item.get('kind'), item.get('lastmod')))

    def enqueue(self, generation, items):
        with self._tx():
            self._enqueue(generation, items)

    def seed(self, generation):
        self.enqueue(generation, [
            {'url': 'https://streeteasy.com/sitemaps/secure/nyc_sitemap_index.xml', 'kind': 'sitemap'},
            {'url': 'https://streeteasy.com/buildings/nyc', 'kind': 'directory'},
            {'url': 'https://streeteasy.com/for-sale/nyc', 'kind': 'search'},
            {'url': 'https://streeteasy.com/for-rent/nyc', 'kind': 'search'},
        ])

    def revisit_known(self, generation, interval=0, include_listings=True):
        """Copy latest URL state; keep deferred rows to prevent rediscovery bypass."""
        cutoff = time.time() - max(0, interval)
        rows = self.db.execute('''SELECT f.*,
            (SELECT MAX(o.fetched) FROM observations o WHERE o.url=f.url AND o.error IS NULL
             AND (o.status BETWEEN 200 AND 299 OR o.status=304)) fetched
            FROM frontier f JOIN (SELECT url,MAX(generation) g FROM frontier
            WHERE generation<? GROUP BY url) latest ON f.url=latest.url AND f.generation=latest.g''',
            (generation,)).fetchall()
        from .extract import canonical_url
        # Old completed variants remain in the archive. Refresh each canonical
        # request only once; validators and freshness belong to the exact URL.
        selected = {}
        aliases = []
        for row in rows:
            url = canonical_url(row['url']) or row['url']
            if url != row['url']:
                aliases.append((row['url'], url))
            if url not in selected or row['url'] == url:
                selected[url] = row
        with self._tx():
            for old_url, url in aliases:
                self._remember_alias(generation, old_url, url)
            for url, row in selected.items():
                allowed = ('sitemap', 'directory', 'search', 'building', 'listing', 'inventory')
                if row['kind'] not in allowed:
                    continue
                if not include_listings and row['kind'] in ('listing', 'inventory'):
                    continue
                exact = url == row['url']
                deferred = exact and row['kind'] in ('building', 'listing') and row['fetched'] is not None and row['fetched'] > cutoff
                self.db.execute('''INSERT INTO frontier(generation,url,kind,lastmod,state,etag,modified)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(generation,url) DO UPDATE SET
                    etag=excluded.etag,modified=excluded.modified,lastmod=excluded.lastmod''',
                    (generation, url, row['kind'], row['lastmod'] if exact else None,
                     'deferred' if deferred else 'pending', row['etag'] if exact else None,
                     row['modified'] if exact else None))

    def recover_inflight(self, generation=None):
        with self._tx():
            self.db.execute("UPDATE frontier SET state='pending' WHERE state='inflight'" +
                            (' AND generation=?' if generation else ''), (generation,) if generation else ())

    def note_response(self, minimum_delay=5):
        with self._tx():
            self.db.execute("INSERT INTO metadata VALUES('next_request',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(time.time() + minimum_delay),))

    def request_delay(self):
        row = self.db.execute("SELECT value FROM metadata WHERE key='next_request'").fetchone()
        return max(0, float(row[0]) - time.time()) if row else 0

    def claim(self, generation, now=None, url_prefix=None, scoped=False, prefer_inventory=False):
        now = time.time() if now is None else now
        with self._tx():
            row = self.db.execute('''SELECT f.* FROM frontier f JOIN generations g ON g.id=f.generation
                WHERE f.generation=? AND f.state='pending' AND f.next_attempt<=?
                AND (g.cooldown IS NULL OR g.cooldown<=?)
                AND (?=0 OR EXISTS(SELECT 1 FROM scope_urls scope WHERE scope.generation=f.generation AND scope.url=f.url))
                AND (? IS NULL OR f.url=? OR substr(f.url,1,length(?)+1)=? || '/' OR substr(f.url,1,length(?)+1)=? || '?')
                -- Unavailable inventories are the source of historical unit
                -- discovery. Give them a durable turn before the growing
                -- listing queue; listings still precede buildings/searches.
                ORDER BY CASE WHEN ? THEN CASE WHEN f.kind='inventory' THEN 0 ELSE f.priority + 1 END
                           ELSE f.priority END, f.rowid LIMIT 1''',
                (generation, now, now, int(scoped), url_prefix, url_prefix, url_prefix, url_prefix, url_prefix, url_prefix,
                 int(prefer_inventory))).fetchone()
            if row:
                self.db.execute("UPDATE frontier SET state='inflight',attempts=attempts+1 WHERE generation=? AND url=?", (generation, row['url']))
                self.db.execute("UPDATE generations SET status='active',cooldown=NULL WHERE id=?", (generation,))
                self.db.execute("INSERT INTO metadata VALUES('next_request',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(now + 5),))
            return row

    def resolve_obsolete_url(self, generation, old_url, new_url=None, kind=None):
        """Retire old aliases or excluded endpoints without claiming a download."""
        with self._tx():
            if new_url:
                self._remember_alias(generation, old_url, new_url)
                self._enqueue(generation, [{'url': new_url, 'kind': kind}])
            self.db.execute("UPDATE frontier SET state=? WHERE generation=? AND url=?",
                            ('superseded' if new_url else 'excluded', generation, old_url))

    def deduplicate_building_views(self, generation, dry_run=False):
        """Retire queued main-page aliases only with successful same-generation evidence.

        Expanded inventories, pagination and unknown query intent remain separate.
        Historical observations and completed frontier rows are never rewritten.
        Call under the archive writer lock, before starting network requests.
        """
        from .extract import canonical_url
        from urllib.parse import urlsplit
        import re
        with self._tx():
            rows = self.db.execute("SELECT url,state FROM frontier WHERE generation=? AND kind='building'",
                                   (generation,)).fetchall()
            result = {'aliases': 0, 'superseded': 0, 'awaiting_canonical_capture': 0,
                      'already_superseded': 0, 'dry_run': dry_run}
            for row in rows:
                original = row['url']
                target = canonical_url(original)
                if (not target or target == original or urlsplit(target).query
                        or not re.fullmatch(r'/building/[^/]+', urlsplit(target).path)):
                    continue
                result['aliases'] += 1
                if not dry_run:
                    self._remember_alias(generation, original, target, 'equivalent main building view')
                if row['state'] == 'superseded':
                    result['already_superseded'] += 1
                if row['state'] not in ('pending', 'deferred'):
                    continue
                success = self.db.execute('''SELECT 1 FROM frontier f WHERE f.generation=? AND f.url=?
                    AND f.state='done' AND EXISTS(SELECT 1 FROM observations o
                        WHERE o.generation=f.generation AND o.url=f.url AND o.error IS NULL
                        AND o.body_hash IS NOT NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304))''',
                    (generation, target)).fetchone()
                if not success:
                    result['awaiting_canonical_capture'] += 1
                    continue
                result['superseded'] += 1
                if not dry_run:
                    self.db.execute("UPDATE frontier SET state='superseded' WHERE generation=? AND url=?",
                                    (generation, original))
            return result

    def conditional_headers(self, generation, url):
        row = self.db.execute('SELECT etag,modified FROM frontier WHERE generation=? AND url=?', (generation, url)).fetchone()
        result = {}
        if row and row['etag']:
            result['If-None-Match'] = row['etag']
        if row and row['modified']:
            result['If-Modified-Since'] = row['modified']
        return result

    def body_path(self, digest):
        return self.root / 'bodies' / digest[:2] / (digest + '.gz')

    def put_body(self, body):
        digest = hashlib.sha256(body).hexdigest()
        path = self.body_path(digest)
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            tmp = path.with_suffix('.tmp')
            with tmp.open('wb') as out:
                out.write(gzip.compress(body, mtime=0))
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        with self._tx():
            self.db.execute('INSERT OR IGNORE INTO bodies VALUES(?,?,?,?)',
                            (digest, str(path.relative_to(self.root)), len(body), time.time()))
        return digest

    def get_body(self, digest):
        return gzip.decompress(self.body_path(digest).read_bytes())

    def latest_response(self, url):
        return self.db.execute('''SELECT * FROM observations WHERE url=? AND body_hash IS NOT NULL
            AND error IS NULL AND (status BETWEEN 200 AND 299 OR status=304) ORDER BY fetched DESC,id DESC LIMIT 1''', (url,)).fetchone()

    def latest_body(self, generation, url):
        row = self.latest_response(url)
        return row['body_hash'] if row else None

    def record(self, generation, url, status, headers, body=None, content_type='',
               extracted=None, error=None, discovered=None, fetched=None, har_fingerprint=None):
        collected_at = time.time() if fetched is None else fetched
        headers = _headers(headers)
        lower = {k.lower(): v for k, v in headers.items()}
        unchanged = status == 304
        previous = self.latest_response(url) if unchanged else None
        if unchanged and not previous:
            raise ValueError('304 response has no archived successful body')
        digest = previous['body_hash'] if unchanged else self.put_body(body) if body is not None else None
        if unchanged:
            content_type = content_type or previous['content_type']
        with self._tx():
            self.db.execute('''INSERT INTO observations(generation,url,fetched,status,content_type,headers,body_hash,not_modified,error)
                VALUES(?,?,?,?,?,?,?,?,?)''', (generation, url, collected_at,
                status, content_type, json.dumps(headers), digest, int(unchanged), error))
            previous_success = self.latest_response(url)
            update_frontier = fetched is None or previous_success is None or fetched >= previous_success['fetched']
            if update_frontier:
                self.db.execute('''UPDATE frontier SET state=?,
                etag=CASE WHEN ? THEN COALESCE(?,etag) ELSE ? END,
                modified=CASE WHEN ? THEN COALESCE(?,modified) ELSE ? END
                WHERE generation=? AND url=?''', ('done' if error is None else 'pending',
                unchanged, lower.get('etag'), lower.get('etag'), unchanged,
                lower.get('last-modified'), lower.get('last-modified'), generation, url))
            self._enqueue(generation, discovered or [])
            if extracted is not None and digest:
                self.db.execute('''INSERT OR IGNORE INTO snapshots(generation,url,body_hash,observed,extraction_version,extracted)
                    VALUES(?,?,?,?,?,?)''', (generation, url, digest, collected_at,
                    extracted.get('extraction_version'), json.dumps(extracted)))
            if har_fingerprint:
                self.db.execute('INSERT OR IGNORE INTO har_entries VALUES(?)', (har_fingerprint,))
        return digest

    def record_gap(self, generation, url, status, headers, reason, discovered=None,
                   body=None, content_type='', complete=True, pause_seconds=None,
                   retry_seconds=None):
        digest = self.put_body(body) if body is not None else None
        with self._tx():
            self.db.execute('''INSERT INTO observations(generation,url,fetched,status,content_type,headers,body_hash,error)
                VALUES(?,?,?,?,?,?,?,?)''', (generation, url, time.time(), status, content_type,
                json.dumps(_headers(headers)), digest, reason))
            self.db.execute('UPDATE frontier SET state=? WHERE generation=? AND url=?',
                            ('done' if complete else 'pending', generation, url))
            if retry_seconds is not None:
                self.db.execute('UPDATE frontier SET next_attempt=? WHERE generation=? AND url=?',
                                (time.time() + max(0, retry_seconds), generation, url))
            self._enqueue(generation, discovered or [])
            if pause_seconds is not None:
                self.db.execute("UPDATE generations SET status='paused',cooldown=? WHERE id=?",
                                (time.time() + max(0, pause_seconds), generation))

    def cooldown(self, generation, seconds, reason=''):
        with self._tx():
            self.db.execute("UPDATE generations SET cooldown=?,status='paused' WHERE id=?", (time.time() + max(0, seconds), generation))
            self.db.execute("UPDATE frontier SET state='pending' WHERE generation=? AND state='inflight'", (generation,))
            if reason:
                self.db.execute('''INSERT INTO observations(generation,url,fetched,headers,error)
                    VALUES(?,?,?,?,?)''', (generation, '__cooldown__', time.time(), '{}', reason))

    def finish(self, generation):
        with self._tx():
            if not self.db.execute("SELECT 1 FROM frontier WHERE generation=? AND state IN ('pending','inflight') LIMIT 1", (generation,)).fetchone():
                self.db.execute("UPDATE generations SET status='complete',cooldown=NULL WHERE id=?", (generation,))
            else:
                self.db.execute("UPDATE generations SET status='active' WHERE id=? AND status='complete'", (generation,))

    def status(self, generation=None):
        generation = generation or self.current_generation()
        if not generation:
            return {'generation': None}
        row = self.db.execute('SELECT * FROM generations WHERE id=?', (generation,)).fetchone()
        if row is None:
            raise ValueError(f'unknown generation {generation}')
        counts = dict.fromkeys(('pending', 'inflight', 'done', 'deferred'), 0)
        counts.update({r[0]: r[1] for r in self.db.execute('SELECT state,count(*) FROM frontier WHERE generation=? GROUP BY state', (generation,))})
        errors = self.db.execute("SELECT count(*) FROM observations WHERE generation=? AND error IS NOT NULL AND error!='redirect observed'", (generation,)).fetchone()[0]
        current_errors = self.db.execute('''SELECT count(*) FROM observations o
            WHERE o.generation=? AND o.error IS NOT NULL AND o.error!='redirect observed'
              AND o.id=(SELECT max(o2.id) FROM observations o2 WHERE o2.url=o.url)''', (generation,)).fetchone()[0]
        last_error = self.db.execute('SELECT url,error FROM observations WHERE generation=? AND error IS NOT NULL ORDER BY id DESC LIMIT 1', (generation,)).fetchone()
        kinds = {r[0]: r[1] for r in self.db.execute('SELECT kind,count(*) FROM frontier WHERE generation=? GROUP BY kind', (generation,))}
        profile_row = self.db.execute('SELECT value FROM metadata WHERE key=?', (f'crawl_profile:{generation}',)).fetchone()
        profile = json.loads(profile_row[0]) if profile_row else None
        scoped = {r[0]: r[1] for r in self.db.execute('SELECT f.state,count(*) FROM frontier f JOIN scope_urls s ON s.generation=f.generation AND s.url=f.url WHERE f.generation=? GROUP BY f.state', (generation,))}
        return {'building_coverage': building_coverage(self.db, generation), 'profile': profile, 'scope_queue': scoped, 'generation': generation, 'name': row['name'], 'status': row['status'],
                'cooldown': row['cooldown'], 'coverage_gaps': errors,
                'current_coverage_gaps': current_errors, 'by_kind': kinds,
                'last_error': dict(last_error) if last_error else None, **counts}

    def observations(self, generation):
        return self.db.execute('SELECT * FROM observations WHERE generation=? ORDER BY id', (generation,))
