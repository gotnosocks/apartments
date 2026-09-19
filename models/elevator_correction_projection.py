"""Project the reviewed elevator ledger, preserving an exact reversible source."""
import argparse
import json
from pathlib import Path

from apartments import bayesian_evidence, corrections, elevator_corrections as lineage
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .elevator_negation_audit import VERSION as AUDIT_VERSION, PATTERN


def records(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def verify_capture(row, literal, replay, edit):
    if any(replay.get(k) != v for k, v in literal.items()):
        raise ValueError('Replay and literal source capture differ')
    if (replay.get('building') != row['building'] or replay.get('stored_elevator') is not True
            or replay['after']['value'] is not edit['patch'][-1]['value']
            or instant(literal['known_at']) > instant(edit['recorded_at'])):
        raise ValueError('Replay value, source identity or knowledge clock differs')
    claims = replay['after']['claims']
    negative = [c for c in claims if c.get('value') is False]
    positive = [c for c in claims if c.get('value') is True]
    if not negative or len(negative)+len(positive) != len(claims):
        raise ValueError('Explicit elevator assertions required')
    for claim in negative:
        start, end = claim.get('start'), claim.get('end')
        text = literal['description']
        if (claim.get('attribute') != 'elevator' or claim.get('method') != 'description_pattern'
                or claim.get('source_path') != '/description' or not isinstance(text, str)
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                or text[start:end] != claim.get('literal') or not PATTERN.search(claim['literal'])):
            raise ValueError('Exact literal denial required')
    after = edit['patch'][-1]['value']
    if ((after is False and (positive or replay['after']['conflicts']))
            or (after is None and (not positive or set(replay['after']['conflicts']) != {True, False}))):
        raise ValueError('Opposing assertions must remain unknown')


def project(rows, evidence, replay, overlay):
    by_capture = {(c['audit_id'], type(c['capture_id']).__name__, c['capture_id']): c for c in replay}
    if len(by_capture) != len(replay): raise ValueError('Duplicate replay capture')
    edits = {e['target']['version_id']: e for e in overlay.active}
    if not edits or len(edits) != len(overlay.active): raise ValueError('Distinct exact-row edits required')
    changed, changes, used = [], [], set()
    for index, row in enumerate(rows):
        edit = edits.get(lineage.sha(row))
        if edit is None:
            changed.append(row)
            continue
        value = lineage.corrected_row(row, edit, overlay.manifest['corrections_as_of'])
        captures = evidence[row['audit_id']]
        expected = {(type(c).__name__, c) for c in row.get('capture_ids', [])}
        if not expected or {(type(c['capture_id']).__name__, c['capture_id']) for c in captures} != expected or len(captures) != len(expected):
            raise ValueError('Every exact source capture must support the correction')
        for c in captures:
            key = (row['audit_id'], type(c['capture_id']).__name__, c['capture_id'])
            if key not in by_capture: raise ValueError('Missing replay evidence')
            verify_capture(row, c, by_capture[key], edit)
        changes.append({'source_index': index, 'observation': row, 'edit': edit})
        changed.append(value); used.add(edit['id'])
    if used != {e['id'] for e in overlay.active}: raise ValueError('Unmatched or repeated correction')
    return changed, changes


def run(dataset, descriptions, audit, ledger, as_of, output):
    dataset, descriptions, audit, ledger = map(Path, (dataset, descriptions, audit, ledger))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'quarantined.jsonl', 'current-source-evidence.jsonl'})
    am, af = _verified_bundle(audit, retain={'captures.jsonl'})
    if (dm.get('version') != lineage.PARENT or am.get('version') != AUDIT_VERSION
            or am.get('dataset_manifest_sha256') != digest(dataset/'complete.json')
            or am.get('descriptions_manifest_sha256') != digest(descriptions/'complete.json')):
        raise ValueError('Elevator audit/source binding differs')
    literal = bayesian_evidence.load_evidence(dataset, descriptions)
    overlay = corrections.Overlay(ledger, as_of=as_of)
    original = records(df['observations.jsonl'])
    revised, changes = project(original, literal, records(af['captures.jsonl']), overlay)
    metadata = {'version': lineage.VERSION, 'source_manifest': dm,
        'source_manifest_sha256': digest(dataset/'complete.json'), 'source_rows': len(original),
        'overlay': overlay.manifest, 'audit_manifest_sha256': digest(audit/'complete.json'),
        'descriptions_manifest_sha256': digest(descriptions/'complete.json')}
    probe = {**metadata, 'files': {lineage.SIDECAR: lineage.records_hash(changes)}}
    if lineage.parent_rows(probe, revised, changes) != (dm, original):
        raise ValueError('Correction inverse changed source')
    summary = {'rows': len(revised), 'changed_rows': len(changes),
        'negative_claim_rows': sum(c['edit']['patch'][-1]['value'] is False for c in changes),
        'conflict_mask_rows': sum(c['edit']['patch'][-1]['value'] is None for c in changes),
        'current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in revised),
        'changed_current_rows': sum(a != b for a, b in zip(original, revised) if a['analysis_price_basis'] == 'current_capture_gross_ask'),
        'policy': 'Exact-row source-report corrections only. Preserve source clocks; correction knowledge is dated in attribute_review_history. No physical change date or cross-ad propagation.'}
    files = {'observations.jsonl': ''.join(canonical(r)+'\n' for r in revised),
        lineage.SIDECAR: ''.join(canonical(r)+'\n' for r in changes),
        'corrections.jsonl': ''.join(canonical(r)+'\n' for r in overlay.records),
        'summary.json': canonical(summary)+'\n'}
    for name in ('quarantined.jsonl', 'current-source-evidence.jsonl'):
        if name in df: files[name] = df[name].decode()
    for p in (Path(__file__), Path(lineage.__file__), Path(corrections.__file__)):
        files[p.name] = p.read_text()
    publish_bundle(output, files, {**metadata, 'summary': summary})
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'descriptions', 'audit', 'ledger', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--as-of', required=True)
    print(canonical(run(**vars(p.parse_args()))), flush=True)
