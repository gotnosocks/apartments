"""Loopback-only read gateway; archive processing remains in authenticated Modal RPC."""
from __future__ import annotations

import re
from flask import Flask, Response, abort, jsonify, request

APP_NAME = 'chelsea-archive-browser'
FUNCTION_NAME = 'read'
MAX_RESPONSE_BYTES = 32*1024*1024
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def allowed_path(path):
    return (path == '/' or
            bool(re.fullmatch(r'/(?:api|static)/[A-Za-z0-9_./-]+', path))
            and not any(part in ('.', '..', '') for part in path.split('/')[1:]))


def create_app(remote_read=None):
    app = Flask(__name__, static_folder=None)
    app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '[::1]']
    function = None

    def invoke(path, query):
        nonlocal function
        if remote_read is not None:
            return remote_read(path, query)
        if function is None:
            import modal
            function = modal.Function.from_name(APP_NAME, FUNCTION_NAME)
        return function.remote(path, query)

    @app.before_request
    def validate_request():
        if request.method != 'GET':
            abort(405)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(403)
        if len(request.path) > 2048 or not allowed_path(request.path):
            abort(404)
        if len(request.query_string) > 8192:
            abort(400)

    @app.after_request
    def response_headers(response):
        response.headers['Content-Security-Policy'] = CSP
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    @app.get('/<path:unused>')
    def read(unused=''):
        try:
            query = request.query_string.decode('ascii')
        except UnicodeDecodeError:
            abort(400)
        try:
            # No browser headers, cookies, credentials or remote destinations are forwarded.
            result = invoke(request.path, query)
            status, body = result['status'], result['body']
            if not isinstance(status,int) or not 200 <= status <= 599:
                raise ValueError('Invalid remote response')
            if not isinstance(body,bytes) or len(body) > MAX_RESPONSE_BYTES:
                raise ValueError('Remote response is invalid or too large')
            headers = {}
            for key, value in result.get('headers', {}).items():
                if key.lower() in ('content-type','content-disposition'):
                    if not isinstance(value,str) or len(value)>1024 or '\r' in value or '\n' in value:
                        raise ValueError('Invalid remote header')
                    headers[key] = value
            return Response(body, status=status, headers=headers)
        except Exception:
            # Authentication diagnostics belong in the SDK/terminal, never in browser payloads.
            return jsonify(error='Cloud archive unavailable. Check Modal login and the deployed archive browser.'), 502

    return app
