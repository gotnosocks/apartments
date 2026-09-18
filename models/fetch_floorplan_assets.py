"""Bounded, source-bound floor-plan image acquisition exclusively via Oxylabs.

API contract: https://developers.oxylabs.io/scraping-solutions/web-scraper-api/features/result-processing-and-storage/download-images
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, UTC
import fcntl
import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
import requests
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from streeteasy_archive.oxylabs import API_URL, _credentials, _safe_envelope

VERSION = 'source-bound-floorplan-acquisition-v1'
MAX_BYTES = 16*1024*1024


def targets(references, listing_ids):
    manifest, files = _verified_bundle(references, retain={'selected-comparisons.jsonl'})
    rows = [json.loads(s) for s in files['selected-comparisons.jsonl'].decode().split('\n') if s.strip()]
    selected = []
    for ad in listing_ids:
        matches = [r for r in rows if str(r['source_listing_id']) == str(ad)]
        if len(matches) != 1:
            raise ValueError('Each selected advertisement must have exactly one source record')
        row = matches[0]
        images = row['recommended_images']
        if len(images) != 1:
            raise ValueError('Choose advertisements with one explicitly recommended floor-plan asset')
        image = images[0]
        parsed = urlparse(image['image_url'])
        if (parsed.scheme != 'https' or parsed.hostname != 'photos.zillowstatic.com'
                or parsed.username or parsed.password or parsed.port is not None
                or image.get('explicit_floorplan_label') != 'mediaType=floor_plan'
                or image.get('variant') != 'full'):
            raise ValueError('Expected an exact, explicitly labeled archived floor-plan URL')
        selected.append({'source': row, 'image': image})
    return manifest, selected


def decode_response(envelope):
    results = envelope.get('results')
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError('Expected exactly one provider result')
    item = results[0]
    if item.get('status_code', item.get('status')) != 200:
        raise ValueError('Image origin did not return200')
    content = item.get('content')
    if not isinstance(content, str) or len(content) > MAX_BYTES*4//3+8:
        raise ValueError('Missing or oversized encoded image')
    body = base64.b64decode(content, validate=True)
    if not body or len(body) > MAX_BYTES:
        raise ValueError('Missing or oversized image bytes')
    with Image.open(BytesIO(body)) as image:
        width, height = image.size
        if image.format not in ('JPEG', 'PNG', 'WEBP') or width*height > 32_000_000:
            raise ValueError('Unsupported image format or dimensions')
        kind = image.format
        image.verify()
    return body, {'format': kind, 'width': width, 'height': height,
                  'image_sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def run(references, output, listing_ids):
    if not 1 <= len(listing_ids) <= 4 or len(set(listing_ids)) != len(listing_ids):
        raise ValueError('Choose one to four distinct advertisement IDs')
    source, selected = targets(references, listing_ids)
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = {'version': VERSION, 'reference_manifest_sha256': digest(Path(references)/'complete.json'),
            'targets': selected, 'max_provider_submissions': len(selected), 'provider': 'oxylabs',
            'implementation_sha256': digest(__file__), 'content_encoding': 'base64',
            'clock_contract': 'New image bytes are collected now from an archived same-advertisement reference; no claim these bytes were known at the HTML capture time.',
            'failure_policy': 'One submission per asset; no automatic retry of uncertain or failed jobs.'}
        ph = hashlib.sha256(canonical(plan).encode()).hexdigest()
        publish_bundle(root/'plan', {'acquisition.json': canonical(plan)+'\n', 'fetch_floorplan_assets.py': Path(__file__).read_text()},
                       {'version': VERSION, 'plan_sha256': ph})
        results = []
        for target in selected:
            ad = str(target['source']['source_listing_id']); folder = root/'assets'/ad
            folder.mkdir(parents=True, exist_ok=True)
            if (folder/'complete.json').exists():
                manifest, files = _verified_bundle(folder, retain={'metadata.json'})
                if manifest.get('plan_sha256') != ph:
                    raise ValueError('Saved asset belongs to another acquisition plan')
                results.append(json.loads(files['metadata.json'])); continue
            if (folder/'submitted.json').exists():
                raise RuntimeError('Prior submission is incomplete or failed; inspect it before starting any new acquisition')
            started = datetime.now(UTC).isoformat()
            (folder/'submitted.json').write_text(canonical({'started_at': started, 'plan_sha256': ph})+'\n')
            payload = {'source': 'universal', 'url': target['image']['image_url'], 'content_encoding': 'base64'}
            try:
                response = requests.post(API_URL, json=payload, auth=_credentials(), timeout=180, allow_redirects=False)
                if response.status_code != 200:
                    raise RuntimeError('Oxylabs API returned HTTP '+str(response.status_code))
                envelope = response.json()
                (folder/'provider-response.json').write_text(canonical(_safe_envelope(envelope))+'\n')
                body, metadata = decode_response(envelope)
                filename = 'floorplan.' + {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[metadata['format']]
                (folder/filename).write_bytes(body)
                metadata.update(source_listing_id=ad, audit_id=target['source']['audit_id'],
                    asset_id=target['image']['asset_id'], image_url=payload['url'], file=filename,
                    collected_at=datetime.now(UTC).isoformat(), started_at=started,
                    reference_capture_id=target['source']['capture_id'], reference_body_sha256=target['source']['body_sha256'],
                    reference_raw_listing_sha256=target['source']['raw_listing_sha256'],
                    reference_manifest_sha256=plan['reference_manifest_sha256'], plan_sha256=ph,
                    meaning=plan['clock_contract'])
                (folder/'metadata.json').write_text(canonical(metadata)+'\n')
                (folder/'source-reference.json').write_text(canonical(target)+'\n')
                files = {p.name: digest(p) for p in folder.iterdir() if p.is_file() and p.name != 'complete.json.tmp'}
                temporary = folder/'complete.json.tmp'
                temporary.write_text(canonical({'version': VERSION, 'plan_sha256': ph, 'files': files})+'\n')
                temporary.replace(folder/'complete.json')
                _verified_bundle(folder)
                results.append(metadata)
                print(canonical({'advertisement': ad, 'status': 'captured', 'bytes': len(body), 'width': metadata['width'], 'height': metadata['height']}), flush=True)
            except Exception as error:
                # Exception class only: request objects and credentials never enter logs.
                (folder/'failure.json').write_text(canonical({'error_type': type(error).__name__, 'failed_at': datetime.now(UTC).isoformat()})+'\n')
                raise RuntimeError('Floor-plan acquisition failed for advertisement '+ad+' ('+type(error).__name__+')') from None
        if digest(__file__) != plan['implementation_sha256']:
            raise ValueError('Acquisition implementation changed')
        return publish_bundle(root/'summary', {'assets.jsonl': ''.join(canonical(r)+'\n' for r in results)},
                              {'version': VERSION, 'plan_sha256': ph, 'assets': len(results)})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--listing-ids', nargs='+', required=True)
    args = p.parse_args()
    run(args.references, args.output, args.listing_ids)
