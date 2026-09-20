"""Verify bathroom/area research leads against complete archived listing bodies."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical
from apartments.granular_parse import parse_listing
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


EXPECTED = {
    '1741581': ({90956}, {'fullBathroomCount': 4, 'halfBathroomCount': 0, 'livingAreaSize': 3800},
                'bathroom_composition_conflict',
                'Structured four full/zero half conflicts with explicit prose two baths/two powder rooms. Candidate composition 2 full/2 half requires a reviewed projection; no physical effective date inferred.'),
    '4730943': ({44510, 120895}, {'fullBathroomCount': 2, 'halfBathroomCount': 2, 'livingAreaSize': 5500},
                'bathroom_composition_ambiguous',
                'Structured two full/two half conflicts with summary two full/one powder room. Later studio full-bath wording prevents unambiguous enumeration; preserve conflict without a numeric replacement.'),
    '2851560': ({20318}, {'fullBathroomCount': 4, 'halfBathroomCount': 1, 'livingAreaSize': None},
                'missing_interior_area',
                'Structured area is absent; prose explicitly reports 3840 square feet interior and 162 exterior. Candidate interior area 3840 must remain distinct from outdoor area and retain retrospective own-ad timing.'),
}


def run(inputs, archive, bodies, output):
    inputs, archive, bodies, output = map(Path, (inputs, archive, bodies, output))
    if digest(inputs/'complete.json') != 'cd8d5229dd8dc83ec3058ebe9f7828422caab22b5b913c83a2da70c8ac546031':
        raise ValueError('Reviewed input differs')
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    cases = [json.loads(s) for s in files['cases.jsonl'].decode().split('\n') if s]
    witnesses, findings = [], []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for case in cases:
            row = case['observation']; ad = row['source_listing_id']
            if ad not in EXPECTED:
                continue
            ids, fields, kind, finding = EXPECTED[ad]
            assert set(row['capture_ids']) == {c['capture_id'] for c in case['descriptions']} == ids
            for capture in case['descriptions']:
                records = db.execute('SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                    [str(archive/'listing_observations/*.parquet'), capture['capture_id']]).fetchall()
                assert len(records) == 1
                raw = records[0][0]
                assert hashlib.sha256(raw.encode()).hexdigest() == capture['raw_listing_sha256']
                original = json.loads(raw)
                assert str(original['id']) == ad
                body_hash = capture['body_sha256']
                body = gzip.decompress((bodies/body_hash[:2]/(body_hash+'.gz')).read_bytes())
                assert hashlib.sha256(body).hexdigest() == body_hash
                parsed, _ = parse_listing(body, 'https://streeteasy.com/rental/'+ad)
                assert parsed['parse_status'] == 'ok'
                recovered = json.loads(parsed['raw_listing_json'])
                assert str(recovered['id']) == ad
                assert recovered['description'] == capture['description']
                assert hashlib.sha256(recovered['description'].encode()).hexdigest() == capture['description_sha256']
                assert {k: v for k, v in original.items() if k != 'description'} == {
                    k: v for k, v in recovered.items() if k != 'description'}
                assert {k: original['propertyDetails'].get(k) for k in fields} == fields
                witnesses.append({**capture, 'raw_listing_json': raw,
                    'recovered_raw_listing_json': parsed['raw_listing_json'],
                    'non_description_fields_identical': True})
            findings.append({'source_listing_id': ad, 'kind': kind, 'finding': finding,
                'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
                'source_row': row, 'capture_ids': sorted(ids), 'source_or_model_changes': False})
    assert len(findings) == 3 and len(witnesses) == 4
    publish_bundle(output, {'findings.jsonl': ''.join(canonical(r)+'\n' for r in findings),
        'raw-witnesses.jsonl': ''.join(canonical(r)+'\n' for r in witnesses),
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'reviewed-movement-measurements-v1', 'cases': 3, 'captures': 4,
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': manifest['source_manifest_sha256'],
        'parser_sha256': digest(__import__('apartments.granular_parse', fromlist=['']).__file__),
        'source_or_model_changes': False,
        'limitation': 'Own-ad claims corroborate source conflicts, not historical physical truth. No correction applied.'})
    _verified_bundle(output)
    return {'output': str(output), 'manifest_sha256': digest(output/'complete.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'archive', 'bodies', 'output'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
