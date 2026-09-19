"""Source-bound unresolved issues, independent of a particular fitted posterior.

Annotations never mutate observations or assert a physical attribute's effective
date. A new dataset needs a new verified review, even if audit IDs survive.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .bayesian_evidence import load_evidence
from .corrections import canonical, instant
from .research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'reviewed-source-issues-v1'


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _records(data):
    return [json.loads(line) for line in data.decode().split('\n') if line.strip()]


def _source(dataset, evidence):
    manifest, files = _verified_bundle(dataset, retain={'observations.jsonl'})
    rows = _records(files['observations.jsonl'])
    indexed = {row['audit_id']: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate source observation identity')
    return manifest, indexed, load_evidence(dataset, evidence)


def _validate(issue, row, captures):
    if row is None or not captures:
        raise ValueError('Issue requires a source row and attached capture evidence')
    for key in ('audit_id', 'unit_id', 'source_listing_id'):
        if (type(issue.get(key)) is not type(row.get(key))
                or issue.get(key) != row.get(key)):
            raise ValueError('Issue source identity differs')
    if (issue.get('source_row_sha256') != _hash(row)
            or issue.get('issue_id') != _hash({k: v for k, v in issue.items() if k != 'issue_id'})
            or issue.get('disposition') != 'unresolved'
            or issue.get('interpretation_limited') is not True):
        raise ValueError('Issue source binding, identifier or disposition differs')
    for field in ('kind', 'message', 'reviewer', 'temporal_scope'):
        if not isinstance(issue.get(field), str) or not issue[field].strip():
            raise ValueError('Issue requires named findings, reviewer and temporal scope')
    reviewed = instant(issue['reviewed_at'])
    if reviewed < instant(row['known_at']):
        raise ValueError('Issue review predates source knowledge')
    fields = issue.get('observed_fields')
    if (not isinstance(fields, dict) or not fields
            or any(key not in row or canonical(value) != canonical(row[key])
                   for key, value in fields.items())):
        raise ValueError('Issue observed fields differ from the bound source')
    reviewed_captures = issue.get('captures', [])
    # Python equality aliases True/1 and 1/1.0. Captures are exact typed
    # archive records, so compare their canonical JSON while retaining order.
    if (not isinstance(reviewed_captures, list)
            or any(not isinstance(item, dict) for item in reviewed_captures)
            or canonical([item.get('capture') for item in reviewed_captures]) != canonical(captures)):
        raise ValueError('Issue must retain every exact attached capture in order')
    count = 0
    for item in reviewed_captures:
        capture = item['capture']
        if reviewed < instant(capture['known_at']):
            raise ValueError('Issue review predates capture knowledge')
        spans = item.get('spans')
        if not isinstance(spans, list):
            raise ValueError('Issue requires explicit literal evidence spans')
        text = capture.get('description')
        seen = set()
        for span in spans:
            start, end = span.get('start'), span.get('end')
            if (not isinstance(text, str) or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text) or (start, end) in seen
                    or text[start:end] != span.get('literal')):
                raise ValueError('Issue literal span differs')
            seen.add((start, end)); count += 1
    if not count:
        raise ValueError('Issue needs at least one supporting literal claim')


def _notes(issues):
    notes = {}
    for issue in issues:
        identity = issue['audit_id']
        if identity not in notes:
            notes[identity] = {'kind': issue['kind'], 'message': issue['message'],
                'interpretation_limited': True, 'issues': [deepcopy(issue)]}
        else:
            notes[identity]['kind'] += '; ' + issue['kind']
            notes[identity]['message'] += '\n\n' + issue['message']
            notes[identity]['issues'].append(deepcopy(issue))
    return notes


def load_source_issues(dataset, issues, *, evidence):
    """Verify all source/evidence bindings before returning historical or current notes."""
    dataset, issues, evidence = map(Path, (dataset, issues, evidence))
    manifest, files = _verified_bundle(issues, retain={'issues.jsonl'})
    if (manifest.get('version') != VERSION
            or manifest.get('dataset_manifest_sha256') != digest(dataset/'complete.json')
            or manifest.get('evidence_manifest_sha256') != digest(evidence/'complete.json')):
        raise ValueError('Source issues differ from selected dataset or description archive')
    source_manifest, rows, captures = _source(dataset, evidence)
    values = _records(files['issues.jsonl'])
    if (not values or manifest.get('issues') != len(values)
            or manifest.get('observations') != len({v['audit_id'] for v in values})
            or len({v['issue_id'] for v in values}) != len(values)
            or manifest.get('source_observations_sha256') != source_manifest['files']['observations.jsonl']):
        raise ValueError('Source issue coverage or source hash differs')
    for value in values:
        _validate(value, rows.get(value['audit_id']), captures.get(value['audit_id']))
    return _notes(values)


def publish_source_issues(dataset, evidence, specifications, output, *, reviewed_at, reviewer):
    """Publish manually reviewed literal claims; no extraction or correction inference.

    Each specification names one exact audit ID, the observed fields, message,
    temporal scope and literal phrases. Every phrase must occur in at least one
    attached capture; all captures remain available, including ones without it.
    """
    dataset, evidence, output = map(Path, (dataset, evidence, output))
    manifest, rows, captures = _source(dataset, evidence)
    values = []
    for spec in specifications:
        row = rows[spec['audit_id']]
        phrases = spec['literals']
        if (not isinstance(phrases, list) or not phrases
                or any(not isinstance(p, str) or not p for p in phrases)
                or len(set(phrases)) != len(phrases)):
            raise ValueError('Distinct nonempty literal phrases are required')
        found, reviewed = set(), []
        for capture in captures[row['audit_id']]:
            text = capture.get('description') or ''
            spans = []
            for phrase in phrases:
                start = text.find(phrase)
                while start >= 0:
                    spans.append({'start': start, 'end': start+len(phrase), 'literal': phrase})
                    found.add(phrase)
                    start = text.find(phrase, start+len(phrase))
            reviewed.append({'capture': deepcopy(capture),
                             'spans': sorted(spans, key=lambda s: (s['start'], s['end']))})
        if found != set(phrases):
            raise ValueError('A reviewed literal phrase is absent from attached evidence')
        value = {**{key: row[key] for key in ('audit_id', 'unit_id', 'source_listing_id')},
            **{key: deepcopy(spec[key]) for key in ('kind', 'message', 'temporal_scope', 'observed_fields')},
            'reviewed_at': reviewed_at, 'reviewer': reviewer, 'source_row_sha256': _hash(row),
            'disposition': 'unresolved', 'interpretation_limited': True, 'captures': reviewed}
        value['issue_id'] = _hash(value)
        _validate(value, row, captures[row['audit_id']])
        values.append(value)
    if not values or len({v['issue_id'] for v in values}) != len(values):
        raise ValueError('Nonempty distinct source issues are required')
    values.sort(key=lambda v: (v['audit_id'], v['issue_id']))
    publish_bundle(output, {'issues.jsonl': ''.join(canonical(v)+'\n' for v in values),
        'specifications.json': canonical(specifications)+'\n',
        Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'issues': len(values), 'observations': len({v['audit_id'] for v in values}),
         'dataset_manifest_sha256': digest(dataset/'complete.json'),
         'evidence_manifest_sha256': digest(evidence/'complete.json'),
         'source_observations_sha256': manifest['files']['observations.jsonl']})
    return _notes(values)


def merge_notes(review_notes, issue_notes):
    """Keep both review channels; never replace or mutate an existing warning."""
    merged = deepcopy(review_notes)
    for identity, note in issue_notes.items():
        if identity not in merged:
            merged[identity] = deepcopy(note)
        else:
            previous = merged[identity]
            merged[identity] = {**previous,
                'kind': previous['kind']+'; '+note['kind'],
                'message': previous['message']+'\n\n'+note['message'],
                'interpretation_limited': previous['interpretation_limited'] or note['interpretation_limited'],
                'issues': deepcopy(previous.get('issues', []))+deepcopy(note['issues'])}
    return merged
