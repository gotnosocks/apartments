"""Check full floor-source reader integration and matched model design before fitting."""
import argparse
import json
from pathlib import Path

from apartments import bayesian_evidence, direct_floor_projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_spline_design as floor
from docs.analysis.scripts import verify_residual_scope_readers as design_verifier


def run(reference, candidate, evidence, output):
    reference, candidate, evidence, output = map(Path, (reference, candidate, evidence, output))
    implementations = {p.name: p for p in runner.implementation_paths()}
    implementations.update({Path(m.__file__).name: Path(m.__file__) for m in (bayesian_evidence, floor, design_verifier)})
    implementations[Path(__file__).name] = Path(__file__)
    hashes = {name: digest(path) for name, path in implementations.items()}
    bindings = {name: digest(path/'complete.json') for name, path in
                [('reference', reference), ('candidate', candidate), ('evidence', evidence)]}
    cm, cf = _verified_bundle(candidate, retain={'observations.jsonl', direct_floor_projection.SIDECAR})
    rm, rf = _verified_bundle(reference, retain={'observations.jsonl'})
    records = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    original, revised = records(rf['observations.jsonl']), records(cf['observations.jsonl'])
    if direct_floor_projection.parent_rows(cm, revised, records(cf[direct_floor_projection.SIDECAR])) != (rm, original):
        raise ValueError('Floor parent inverse differs')
    print('Verifying literal evidence and complete lineage', flush=True)
    old = bayesian_evidence.load_evidence(reference, evidence)
    new = bayesian_evidence.load_evidence(candidate, evidence)
    if old != new:
        raise ValueError('Floor projection changed literal evidence')
    print('Verifying fit loaders and matched feature design', flush=True)
    frames = [runner.load_data(path)[0] for path in (reference, candidate)]
    for frame, rows in zip(frames, (original, revised), strict=True):
        if frame.audit_id.tolist() != [r['audit_id'] for r in rows]:
            raise ValueError('Fit reader changed source order')
    designs = [floor.FeatureDesign(frame, 'full_half_balance', floor_prior_scale=.10) for frame in frames]
    design = design_verifier.compare_designs(designs, frames)
    result = {'passed': True, 'rows': len(revised), 'floor_additions': len(records(cf[direct_floor_projection.SIDECAR])),
        'literal_evidence_identical': True, 'literal_captures': sum(map(len, new.values())),
        'exact_parent_inverse': True, 'full_lineage_readers_passed': True, **design,
        'fit_performed': False, 'main_selection_changed': False}
    if hashes != {name: digest(path) for name, path in implementations.items()}:
        raise ValueError('Reader code changed during verification')
    if bindings != {name: digest(path/'complete.json') for name, path in
                   [('reference', reference), ('candidate', candidate), ('evidence', evidence)]}:
        raise ValueError('Input changed during verification')
    publish_bundle(output, {'verification.json': canonical(result)+'\n',
        **{name: path.read_text() for name, path in implementations.items()}},
        {'version': 'direct-floor-reader-verification-v1', 'inputs': bindings, 'implementation_sha256': hashes})
    _verified_bundle(output)
    print(canonical({'passed': True, 'rows': len(revised), 'manifest_sha256': digest(output/'complete.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'evidence', 'output'):
        parser.add_argument('--'+name, required=True)
    run(**vars(parser.parse_args()))
