"""Redaction for persisted transport metadata (never for archived page bodies)."""
from __future__ import annotations


_PRIVATE_KEYS = {
    'authorization', 'proxyauthorization', 'cookie', 'cookies', 'setcookie',
    'wwwauthenticate', 'xapikey', 'apikey', 'password', 'passwd', 'username',
    'credentials', 'auth', 'token', 'accesstoken', 'refreshtoken', 'secret',
    'request', 'sessioninfo',
}


def _private(key):
    return str(key).lower().replace('-', '').replace('_', '') in _PRIVATE_KEYS


def redact(value):
    """Remove credential/session fields, including HAR-style header arrays."""
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items() if not _private(key)}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value
                if not (isinstance(item, dict) and _private(item.get('name', '')))]
    return value


def capture_metadata(meta, transport):
    """Capture each response independently of parsing and snapshot deduplication."""
    result = {'transport': transport}
    if meta.get('archive_provider'):
        provider = dict(meta['archive_provider'])
        # HTML already has immutable content-addressed storage. Repeating it in
        # every observation would inflate the database and conflate raw content
        # with transport metadata.
        provider['results'] = [{k: v for k, v in item.items() if k != 'content'}
                               for item in provider.get('results', [])]
        result['provider'] = provider
    if meta.get('archive_browser'):
        result['browser'] = meta['archive_browser']
    return redact(result)
