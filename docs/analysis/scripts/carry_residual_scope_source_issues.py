"""Rebind unchanged unresolved annotations to the retained residual-scope cohort.

The original review clock and findings remain unchanged. This is a verified
carry-forward across a source revision, not a new physical-attribute review.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from apartments import bayesian_evidence, source_issues, residual_scope_projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'retained-residual-scope-source-issue-linkage-v1'


def records(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def verify_retained(issues, original, retained, captures):
    """Require complete typed equality, including literal span coordinates."""
    for issue in issues:
        identity = issue['audit_id']
        if (identity not in original or identity not in retained
                or canonical(original[identity]) != canonical(retained[identity])):
            raise ValueError('Annotated source observation changed or disappeared')
        attached = [item['capture'] for item in issue['captures']]
        if canonical(attached) != canonical(captures.get(identity)):
            raise ValueError('Annotated capture evidence changed or disappeared')
    clocks = {(issue['reviewed_at'], issue['reviewer']) for issue in issues}
    if len(clocks) != 1:
        raise ValueError('Public publisher requires a shared original review clock and reviewer')
    return next(iter(clocks))


def run(reference, candidate, evidence, previous, output, linkage):
    reference, candidate, evidence, previous, output, linkage = map(
        Path, (reference, candidate, evidence, previous, output, linkage))
    inputs = {'reference': reference, 'candidate': candidate, 'evidence': evidence, 'previous_issues': previous}
    input_hashes = {name: digest(path/'complete.json') for name, path in inputs.items()}
    implementations = {Path(m.__file__).name: Path(m.__file__) for m in
        (source_issues, bayesian_evidence, residual_scope_projection)}
    # Bind all transitive lineage code exercised by the evidence reader.
    from models.bayesian_feature_experiment_v3 import implementation_paths
    implementations.update({p.name: p for p in implementation_paths()})
    implementations[Path(__file__).name] = Path(__file__)
    code_hashes = {name: digest(path) for name, path in implementations.items()}
    print('Loading and fully verifying the original source annotations', flush=True)
    original_notes = source_issues.load_source_issues(reference, previous, evidence=evidence)
    _, old_files = _verified_bundle(previous, retain={'issues.jsonl', 'specifications.json'})
    issues, specs = records(old_files['issues.jsonl']), json.loads(old_files['specifications.json'])
    if len(issues) != 4 or len(original_notes) != 3:
        raise ValueError('Expected the four existing unresolved issues on three observations')
    manifests, indexed = [], []
    for path in (reference, candidate):
        manifest, files = _verified_bundle(path, retain={'observations.jsonl'})
        rows = records(files['observations.jsonl'])
        table = {row['audit_id']: row for row in rows}
        if len(table) != len(rows):
            raise ValueError('Duplicate source identity')
        manifests.append(manifest); indexed.append(table)
    if (manifests[1].get('version') != residual_scope_projection.VERSION
            or manifests[1].get('source_manifest') != manifests[0]
            or manifests[1].get('source_manifest_sha256') != input_hashes['reference']):
        raise ValueError('Expected the exact residual-scope child of the original annotation source')
    print('Verifying retained annotated observations and complete own-ad evidence', flush=True)
    captures = bayesian_evidence.load_evidence(candidate, evidence)
    reviewed_at, reviewer = verify_retained(issues, *indexed, captures)
    del indexed, captures
    print('Publishing with the original review timing and independently reloading', flush=True)
    notes = source_issues.publish_source_issues(candidate, evidence, deepcopy(specs), output,
        reviewed_at=reviewed_at, reviewer=reviewer)
    loaded = source_issues.load_source_issues(candidate, output, evidence=evidence)
    _, new_files = _verified_bundle(output, retain={'issues.jsonl', 'specifications.json'})
    if (canonical(notes) != canonical(original_notes) or canonical(loaded) != canonical(original_notes)
            or old_files['issues.jsonl'] != new_files['issues.jsonl']
            or old_files['specifications.json'] != new_files['specifications.json']):
        raise ValueError('Carried annotations differ from the complete original review')
    if input_hashes != {name: digest(path/'complete.json') for name, path in inputs.items()}:
        raise ValueError('An input manifest changed')
    if code_hashes != {name: digest(path) for name, path in implementations.items()}:
        raise ValueError('An implementation changed')
    result = {'version': VERSION, 'passed': True, 'inputs': input_hashes,
        'output_manifest_sha256': digest(output/'complete.json'), 'issues': 4, 'observations': 3,
        'source_listing_ids': sorted({issue['source_listing_id'] for issue in issues}),
        'issue_ids': [issue['issue_id'] for issue in issues],
        'reviewed_at': reviewed_at, 'reviewer': reviewer,
        'complete_annotated_rows_equal': True, 'complete_attached_captures_equal': True,
        'issue_records_byte_equal': True, 'specifications_byte_equal': True,
        'original_review_timing_preserved': True, 'independent_public_load_passed': True,
        'main_selection_changed': False, 'source_or_fit_changed': False,
        'limits': ['Carries existing unresolved findings only; no correction or new physical-attribute effective date.',
            'Original review timing is preserved. This linkage records validation against a new retained dataset.',
            'No posterior fitting, contribution calculation or UI validation is performed.']}
    publish_bundle(linkage, {'linkage.json': canonical(result)+'\n',
        **{name: path.read_text() for name, path in implementations.items()}},
        {'version': VERSION, 'inputs': input_hashes, 'output_manifest_sha256': digest(output/'complete.json'),
         'implementation_sha256': code_hashes})
    print(canonical({'issues': 4, 'observations': 3, 'independent_public_load_passed': True,
        'output_manifest_sha256': digest(output/'complete.json'),
        'linkage_manifest_sha256': digest(linkage/'complete.json')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'evidence', 'previous', 'output', 'linkage'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
