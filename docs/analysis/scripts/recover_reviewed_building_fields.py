"""Recover literal building fields for the six reviewed access-support buildings."""
import argparse
import gzip
import json
from pathlib import Path

from apartments import building_field_recovery as recovery
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(review, bodies, output):
    review, bodies, output = map(Path, (review, bodies, output))
    if digest(review/'complete.json') != '34ebbadb89f6ad71251a5049eb893dfc0fbeb72bb0a9e13e8c9d4b9ec7efd963':
        raise ValueError('Reviewed building evidence differs')
    _, files = _verified_bundle(review, retain={'building-witnesses.jsonl'})
    witnesses = [json.loads(s) for s in files['building-witnesses.jsonl'].decode().split('\n') if s]
    rows = []
    for witness in witnesses:
        sha = witness['body_sha256']
        with gzip.open(bodies/sha[:2]/(sha+'.gz'), 'rb') as stream:
            body = stream.read(32*1024*1024+1)
        if len(body) > 32*1024*1024:
            raise ValueError('Building body exceeds recovery limit')
        recovered = recovery.recover(body, witness['raw_building_json'], body_sha256=sha,
                                    raw_building_sha256=witness['raw_building_sha256'])
        assert recovered['building_slug'] == witness['building']
        rows.append({'source': witness, 'recovered': recovered, 'applied': False})
    assert len(rows) == 10 and len({r['source']['building'] for r in rows}) == 6
    classes = {}
    for row in rows:
        building = row['source']['building']
        nyc = row['recovered']['fields']['nyc']['resolved']
        value = {'code': nyc.get('buildingClass'), 'description': nyc.get('buildingClassDescription')}
        if building in classes and classes[building] != value:
            raise ValueError('Repeated captures disagree on class; explicit review required')
        classes[building] = value
    summary = {'captures': len(rows), 'buildings': len(classes), 'literal_class_labels': classes,
        'source_or_model_changes': False,
        'interpretation': 'Literal captured labels only. Missing or empty amenities are not elevator absence; no class-to-elevator inference or historical propagation applied.'}
    publish_bundle(output, {'recovered.jsonl': ''.join(canonical(r)+'\n' for r in rows),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text(),
        Path(recovery.__file__).name: Path(recovery.__file__).read_text()},
        {'version': recovery.VERSION, 'review_manifest_sha256': digest(review/'complete.json')})
    _verified_bundle(output)
    print(canonical({'captures': len(rows), 'buildings': len(classes), 'manifest_sha256': digest(output/'complete.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('review', 'bodies', 'output'):
        parser.add_argument('--'+name, required=True)
    run(**vars(parser.parse_args()))
