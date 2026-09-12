"""Read-only local browser for the live archive. No StreetEasy requests are made."""
from __future__ import annotations

import fcntl
import gzip
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, abort, g, jsonify, render_template, request

from .extract import extract
from .store import building_coverage


def create_app(data_dir='data'):
    root = Path(data_dir).resolve()
    app = Flask(__name__)
    app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '[::1]']

    def db():
        if 'db' not in g:
            if not (root / 'archive.sqlite3').exists():
                abort(404, description='Archive not initialized. Run backfill or import-har first.')
            g.db = sqlite3.connect(f'file:{quote(str(root / "archive.sqlite3"))}?mode=ro', uri=True, timeout=5)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA query_only=ON')
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop('db', None)
        if connection is not None:
            connection.close()

    @app.after_request
    def local_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(400)
    @app.errorhandler(404)
    def http_error(error):
        return jsonify(error=error.description), error.code

    def generation():
        value = request.args.get('generation')
        if value:
            try:
                result = int(value)
            except ValueError:
                abort(400, description='Invalid generation')
        else:
            row = db().execute('SELECT MAX(id) FROM generations').fetchone()
            result = row[0]
        if result is not None and not db().execute('SELECT 1 FROM generations WHERE id=?', (result,)).fetchone():
            abort(404, description='Generation not found')
        return result

    def writer_running():
        path = root / 'crawler.lock'
        if not path.exists():
            return False
        with path.open('r') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(lock, fcntl.LOCK_UN)
                return False
            except BlockingIOError:
                return True

    @app.get('/')
    def index():
        return render_template('archive.html')

    @app.get('/api/summary')
    def summary():
        gen = generation()
        generations = [dict(row) for row in db().execute('SELECT * FROM generations ORDER BY id DESC LIMIT 200')]
        state = dict(db().execute('SELECT * FROM generations WHERE id=?', (gen,)).fetchone()) if gen else None
        queue = {row[0]: row[1] for row in db().execute('SELECT state,count(*) FROM frontier WHERE generation=? GROUP BY state', (gen,))}
        captured = {row[0]: row[1] for row in db().execute('''SELECT f.kind,count(*) FROM frontier f
            WHERE f.generation=? AND EXISTS(SELECT 1 FROM observations o WHERE o.url=f.url
            AND o.generation<=? AND o.error IS NULL AND o.body_hash IS NOT NULL
            AND (o.status BETWEEN 200 AND 299 OR o.status=304)) GROUP BY f.kind''', (gen, gen))}
        counts = db().execute('SELECT count(*),COALESCE(sum(size),0) FROM bodies').fetchone()
        errors = [dict(row) for row in db().execute("""SELECT e.id,e.url,e.status,e.error,e.fetched
            FROM observations e WHERE e.generation=? AND e.error IS NOT NULL AND e.error!='redirect observed'
            AND NOT EXISTS(SELECT 1 FROM frontier f WHERE f.generation=e.generation AND f.url=e.url AND f.kind='excluded')
            AND NOT EXISTS(SELECT 1 FROM observations good WHERE good.url=e.url AND good.error IS NULL
                AND (good.status BETWEEN 200 AND 299 OR good.status=304)
                AND (good.fetched>e.fetched OR (good.fetched=e.fetched AND good.id>e.id)))
            ORDER BY e.id DESC LIMIT 10""", (gen,))]
        profile_row = db().execute('SELECT value FROM metadata WHERE key=?', (f'crawl_profile:{gen}',)).fetchone()
        profile = json.loads(profile_row[0]) if profile_row else None
        scoped = {r[0]: r[1] for r in db().execute('SELECT f.state,count(*) FROM frontier f JOIN scope_urls s ON s.generation=f.generation AND s.url=f.url WHERE f.generation=? GROUP BY f.state', (gen,))}
        return jsonify(building_coverage=building_coverage(db(), gen), profile=profile, scope_queue=scoped, generation=state, generations=generations, queue=queue, captured=captured,
                       responses=db().execute('SELECT count(*) FROM observations').fetchone()[0],
                       unique_bodies=counts[0], body_bytes=counts[1], errors=errors,
                       writer_running=writer_running(), archive_path=str(root))

    @app.get('/api/pages')
    def pages():
        gen = generation()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            abort(400, description='Invalid page number')
        where = ['f.generation=?']
        params = [gen]
        kind = request.args.get('kind', '')
        state = request.args.get('state', '')
        query = request.args.get('q', '').strip()[:300]
        if kind:
            where.append('f.kind=?')
            params.append(kind)
        if query:
            where.append("f.url LIKE ? ESCAPE '\\'")
            params.append('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if state == 'captured':
            where.append('o.body_hash IS NOT NULL AND o.error IS NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304)')
        elif state == 'errors':
            where.append('o.error IS NOT NULL')
        elif state:
            if state not in ('pending', 'inflight', 'done', 'deferred', 'superseded', 'excluded'):
                abort(400, description='Invalid queue state')
            where.append('f.state=?')
            params.append(state)
        join = '''FROM frontier f LEFT JOIN observations o ON o.id=(SELECT id FROM observations
            WHERE url=f.url AND generation<=f.generation ORDER BY fetched DESC,id DESC LIMIT 1)'''
        condition = ' WHERE ' + ' AND '.join(where)
        total = db().execute('SELECT count(*) ' + join + condition, params).fetchone()[0]
        rows = db().execute('''SELECT f.url,f.kind,f.state,f.attempts,f.lastmod,o.id observation_id,
            o.status,o.fetched,o.body_hash,o.error ''' + join + condition +
            ' ORDER BY f.url LIMIT 40 OFFSET ?', [*params, (page - 1) * 40]).fetchall()
        return jsonify(items=[dict(row) for row in rows], page=page, total=total, page_size=40)

    @app.get('/api/page')
    def page_detail():
        url = request.args.get('url', '')
        gen = generation()
        row = db().execute('SELECT * FROM frontier WHERE generation=? AND url=?', (gen, url)).fetchone()
        if row is None:
            abort(404, description='Page not found')
        history = [dict(item) for item in db().execute('''SELECT id,generation,fetched,status,content_type,
            headers,body_hash,not_modified,error FROM observations WHERE url=? AND generation<=?
            ORDER BY fetched DESC,id DESC LIMIT 100''', (url, gen))]
        for item in history:
            item['headers'] = json.loads(item['headers'])
        return jsonify(page=dict(row), history=history,
                       observation_count=db().execute('SELECT count(*) FROM observations WHERE url=? AND generation<=?', (url, gen)).fetchone()[0])

    def observation(obs_id):
        row = db().execute('SELECT * FROM observations WHERE id=?', (obs_id,)).fetchone()
        if row is None:
            abort(404, description='Observation not found')
        return row

    def body_file(row):
        digest = row['body_hash']
        if not digest:
            abort(404, description='No body was captured for this observation')
        # Hashes are produced by the archive, never accepted as filesystem paths.
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            abort(404, description='Invalid archived body reference')
        path = root / 'bodies' / digest[:2] / (digest + '.gz')
        if not path.exists():
            abort(404, description='Archived body file is missing')
        return path

    @app.get('/api/observations/<int:obs_id>/extraction')
    def extraction(obs_id):
        row = observation(obs_id)
        snap = db().execute('SELECT extracted FROM snapshots WHERE generation=? AND url=? AND body_hash=?',
                            (row['generation'], row['url'], row['body_hash'])).fetchone()
        if snap:
            return Response(snap[0], mimetype='application/json')
        with gzip.open(body_file(row), 'rb') as source:
            body = source.read()
        try:
            return jsonify(extract(body, row['url'], row['content_type'] or ''))
        except Exception as exc:
            return jsonify(error=f'Extraction unavailable: {exc}'), 422

    @app.get('/api/observations/<int:obs_id>/raw')
    def raw(obs_id):
        row = observation(obs_id)
        with gzip.open(body_file(row), 'rb') as source:
            if request.args.get('download') == '1':
                response = Response(source.read(), mimetype='application/octet-stream')
                response.headers['Content-Disposition'] = f'attachment; filename="observation-{obs_id}.bin"'
                return response
            preview = source.read(200001)
        return jsonify(text=preview[:200000].decode('utf-8', errors='replace'),
                       truncated=len(preview) > 200000, body_hash=row['body_hash'])

    return app
