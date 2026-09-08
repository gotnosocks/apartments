"""One-request local experiments, with offline parser replay and no archive DB."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
import requests
from .extract import extract
from .oxylabs import API_URL, MAX_BODY, _credentials, _result_item, _safe_envelope, _target_url, build_payload


def probe(url, mode, output, replay=None, timeout=180):
    url = _target_url(url)
    if mode != 'html':
        if '/building/' not in url or '?' in url:
            raise ValueError('Inventory probes require a canonical building URL without query parameters')
        url += '?archive_view=unavailable-' + mode
    payload = build_payload(url)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    metadata = {'url': url, 'mode': mode, 'started_at': datetime.now(timezone.utc).isoformat(),
                'replay': str(replay) if replay else None, 'request_count': 0}
    started = time.monotonic()
    try:
        if replay:
            if Path(replay).stat().st_size > MAX_BODY:
                raise ValueError('Replay body exceeds size limit')
            body = Path(replay).read_bytes()
        else:
            auth = _credentials()
            (output/'request.json').write_text(json.dumps(payload, indent=2))
            metadata['request_count'] = 1
            print('Submitting one Oxylabs request; no automatic retries.', flush=True)
            with requests.post(API_URL, json=payload, auth=auth, timeout=timeout,
                               allow_redirects=False, stream=True) as response:
                metadata['api_status'] = response.status_code
                metadata['api_headers'] = {k:v for k,v in response.headers.items()
                    if k.lower().startswith('x-ratelimit-') or k.lower() == 'x-oxylabs-job-id'}
                response.raise_for_status()
                chunks = []; size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 2 * MAX_BODY:
                        raise ValueError('Provider envelope exceeds size limit')
                    chunks.append(chunk)
                envelope = json.loads(b''.join(chunks))
            (output/'response.json').write_text(json.dumps(_safe_envelope(envelope)))
            _, item, status, content = _result_item(envelope)
            metadata['target_status'] = status
            metadata['provider_metadata'] = _safe_envelope({k:v for k,v in item.items()
                                                           if k not in ('content', '_response', 'headers')})
            body = content.encode('utf-8') if isinstance(content, str) else content
            if len(body) > MAX_BODY:
                raise ValueError('Page body exceeds size limit')
            (output/'body.html').write_bytes(body)
            if not 200 <= status < 300:
                raise ValueError(f'Target returned HTTP {status}')
        data = extract(body, url)
        (output/'extracted.json').write_text(json.dumps(data))
        inventory = data.get('inventory', {})
        metadata.update(ok=True, body_bytes=len(body), inventory_count=inventory.get('count'),
                        detail_links=len(inventory.get('links', [])),
                        records=len(inventory.get('records', [])))
    except Exception as exc:
        # Do not include request objects, credentials, or raw response exceptions.
        metadata.update(ok=False, error_type=type(exc).__name__)
        if isinstance(exc, ValueError):
            metadata['error'] = str(exc)[:300]
    finally:
        metadata['elapsed_seconds'] = round(time.monotonic()-started, 3)
        (output/'metadata.json').write_text(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--mode', choices=['html', 'rentals', 'sales'], default='rentals')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--replay', type=Path, help='Parse a saved body without making a request')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180:
        parser.error('--timeout must be between 1 and 180 seconds')
    output = args.output or Path(__file__).resolve().parents[2]/'data/probes'/(
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    result = probe(args.url, args.mode, output, args.replay, args.timeout)
    print(json.dumps({'output': str(output.resolve()), **result}, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
