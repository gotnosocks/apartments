"""Compare accepted shared-noise fits across a verified scope/composition overlay."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import statistics
import tempfile

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as verified
from . import bayesian_feature_sensitivity as comparison
from . import bayesian_noise_sensitivity as noise
from . import research_scope_overlay as overlay

VERSION = 'verified-bayesian-source-sensitivity-v1'
SOURCE_FIELDS = {'source_manifest_sha256','source_observations_sha256','source_version',
                 'source_directory','rows','units','buildings','current_rows'}
VARIABLE = noise.VARIABLE | SOURCE_FIELDS


def reconstruction_dependencies(protocol=None):
    # Import lazily: verifying source revisions alone needs no numerical runtime.
    from . import bayesian_feature_model as feature
    paths = [Path(module.__file__) for module in
        (feature, feature.base, feature.amenity, feature.amenity.baseline, feature.pricing)]
    if protocol and protocol.get('version') == 'observable-bayesian-floor-experiment-v4':
        from . import bayesian_floor_increment_design as floor
        if protocol.get('feature_design_version') != floor.VERSION:
            raise ValueError('Unsupported floor reconstruction version')
        return floor, [*paths,Path(floor.__file__)]
    return feature, paths


def verify_design(experiment, dataset, protocol, provenance):
    """Rebuild the archived construction from exact source; never load a fitted design."""
    import numpy as np
    import pandas as pd

    experiment, dataset = Path(experiment), Path(dataset)
    feature, paths = reconstruction_dependencies(protocol)
    pm, fm = provenance['protocol_manifest'], provenance['fit_manifest']
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    if (pm.get('protocol_sha256') != ph or fm.get('protocol_sha256') != ph
            or json.loads(comparison.bound_bytes(experiment/'protocol','protocol.json',pm)) != protocol):
        raise ValueError('Design reconstruction protocol binding differs')
    code = protocol['implementation_sha256']
    for path in paths:
        if code.get(path.name) != digest(path) or pm['files'].get(path.name) != code.get(path.name):
            raise ValueError('Local design reconstruction dependency differs from archive: '+path.name)
        comparison.bound_bytes(experiment/'protocol',path.name,pm)
    versions = {name:importlib.metadata.version(name) for name in ('numpy','pandas','scipy')}
    if any(protocol.get('versions',{}).get(name) != value for name,value in versions.items()):
        raise ValueError('Design reconstruction numerical environment differs from archive')
    sm, sf = _verified_bundle(dataset,retain={'observations.jsonl'})
    if (digest(dataset/'complete.json') != protocol['source_manifest_sha256']
            or sm['files']['observations.jsonl'] != protocol['source_observations_sha256']
            or sm.get('version') != protocol.get('source_version')):
        raise ValueError('Design reconstruction source differs from protocol')
    # Keep conversions and row order identical to the frozen v2/v3 runners.
    data = pd.DataFrame(overlay.rows(sf['observations.jsonl']))
    data.period = pd.to_datetime(data.period)
    data.square_feet = pd.to_numeric(data.square_feet,errors='coerce')
    if (len(data) != protocol['rows'] or data.audit_id.duplicated().any()
            or data.duplicated(['unit_id','period']).any()
            or not np.isfinite(data.asking_rent).all() or not data.asking_rent.gt(0).all()):
        raise ValueError('Invalid design reconstruction source cohort')
    saved = {name:comparison.bound_bytes(experiment/'fit',name,fm) for name in comparison.DESIGNS}
    arrays = {}
    with tempfile.TemporaryDirectory(prefix='apartments-design-verification-') as temporary:
        fresh = Path(temporary)
        kwargs = ({'floor_increment_prior_scale':protocol['floor_increment_prior_scale']}
                  if protocol.get('version') == 'observable-bayesian-floor-experiment-v4' else {})
        feature.FeatureDesign(data,protocol['specification'],**kwargs).save(fresh)
        for name in ('feature-design.json','time-design.json'):
            if canonical(json.loads(saved[name])) != canonical(json.loads((fresh/name).read_bytes())):
                raise ValueError('Saved design differs from exact source reconstruction: '+name)
        with np.load(io.BytesIO(saved['time-design.npz']),allow_pickle=False) as actual, \
                np.load(fresh/'time-design.npz',allow_pickle=False) as expected:
            if (len(set(actual.files)) != len(actual.files)
                    or set(actual.files) != set(expected.files)):
                raise ValueError('Saved time design array membership differs from reconstruction')
            for name in expected.files:
                a, b = actual[name], expected[name]
                if a.dtype != b.dtype or a.shape != b.shape or not np.array_equal(a,b):
                    raise ValueError('Saved time design array differs from exact reconstruction: '+name)
                arrays[name] = {'dtype':str(a.dtype),'shape':list(a.shape),
                    'contents_sha256':hashlib.sha256(a.tobytes(order='C')).hexdigest()}
    if any(digest(path) != code[path.name] for path in paths):
        raise ValueError('Design reconstruction implementation changed during verification')
    return {'verified':True,'source_manifest_sha256':protocol['source_manifest_sha256'],
        'source_observations_sha256':protocol['source_observations_sha256'],'rows':len(data),
        'implementation_sha256':{path.name:code[path.name] for path in paths},'versions':versions,
        'design_sha256':{name:fm['files'][name] for name in comparison.DESIGNS},
        'time_arrays':arrays,'comparison':'All JSON semantics equal; exact named NPZ array contents, dtypes and shapes.'}


def check_protocols(reference, candidate):
    if reference.get('version') not in (noise.V2,noise.V3) or candidate.get('version') != noise.V3:
        raise ValueError('Expected v2/v3 reference and v3 reviewed-source fit')
    for p in (reference,candidate):
        if p.get('residual_parameterization','noncentered') not in ('centered','noncentered'):
            raise ValueError('Unknown residual hierarchy parameterization')
        if p.get('residual_scale','shared') != 'shared':
            raise ValueError('This source-only comparison requires shared residual scales')
        for key,minimum in [('chains',2),('draws',1),('tune',1),('seed',0)]:
            if type(p.get(key)) is not int or p[key] < minimum:
                raise ValueError('Invalid sampler protocol')
    if {k:v for k,v in reference.items() if k not in VARIABLE} != {k:v for k,v in candidate.items() if k not in VARIABLE}:
        raise ValueError('Fixed model, feature prior, sampler or environment changed')
    for key,default in [('building_prior_scale',.35),('unit_prior_scale',.25)]:
        if reference.get(key,default) != candidate.get(key):
            raise ValueError('Group priors changed')
    if reference['version'] == noise.V3 and reference['graph_configuration'] != candidate['graph_configuration']:
        raise ValueError('Shared graph configuration changed')
    a,b = (p['implementation_sha256'] for p in (reference,candidate))
    if reference['version'] == noise.V2:
        if not a or set(b)-set(a) != noise.V3_CODE or any(b.get(k) != v for k,v in a.items()):
            raise ValueError('Shared archived implementation changed')
    elif a != b:
        raise ValueError('Shared archived implementation changed')


def verify_revision(reference, candidate, audit):
    """Recheck exact retained rows and original quarantines against reviewed evidence."""
    reference,candidate,audit = map(Path,(reference,candidate,audit))
    rm,rf = _verified_bundle(reference,retain={'observations.jsonl'})
    cm,cf = _verified_bundle(candidate,retain={'observations.jsonl','decisions.jsonl','quarantined.jsonl','summary.json'})
    am,_ = _verified_bundle(audit,retain=set())
    decisions_manifest = cm.get('decisions_manifest',{})
    if (rm.get('version') != overlay.SOURCE_VERSION or cm.get('version') != overlay.VERSION
            or cm.get('source_manifest_sha256') != digest(reference/'complete.json')
            or cm.get('source_manifest') != rm
            or cm.get('audit_manifest_sha256') != digest(audit/'complete.json')
            or decisions_manifest.get('version') != overlay.DECISION_VERSION
            or decisions_manifest.get('source_manifest_sha256') != digest(reference/'complete.json')
            or decisions_manifest.get('source_observations_sha256') != rm['files']['observations.jsonl']
            or decisions_manifest.get('audit_manifest_sha256') != digest(audit/'complete.json')
            or decisions_manifest.get('files',{}).get('decisions.jsonl') != cm['files']['decisions.jsonl']):
        raise ValueError('Source revision lineage differs')
    before,after,decisions,quarantines = (overlay.rows(blob) for blob in
        (rf['observations.jsonl'],cf['observations.jsonl'],cf['decisions.jsonl'],cf['quarantined.jsonl']))
    by_id = {d['audit_id']:d for d in decisions}
    if len(by_id) != len(decisions) or len({r['audit_id'] for r in before}) != len(before) or not set(by_id) <= {r['audit_id'] for r in before}:
        raise ValueError('Duplicate or unknown revision identity')
    captures = {}
    with (audit/'captures.jsonl').open() as stream:
        for line in stream:
            if not line.strip():continue
            capture=json.loads(line)
            if capture['audit_id'] in by_id:
                key=(capture['audit_id'],str(capture['capture_id']))
                if key in captures:raise ValueError('Duplicate source capture')
                captures[key]=capture
    if digest(audit/'captures.jsonl') != am['files']['captures.jsonl']:
        raise ValueError('Source audit changed')
    expected,excluded = [],[]
    for row in before:
        d=by_id.get(row['audit_id'])
        result=row if d is None else overlay.apply_decision(row,d,captures)
        if result is not None:expected.append(result)
        else:excluded.append({'observation':row,**{k:d[k] for k in ('decision_id','action','reason','interpreted_at')}})
    if expected != after or excluded != quarantines:
        raise ValueError('Retained rows or quarantined originals differ from reviewed decisions')
    current=lambda rows:{r['audit_id'] for r in rows if r.get('analysis_price_basis')=='current_capture_gross_ask'}
    if current(before) != current(after):
        raise ValueError('Current capture membership changed')
    summary=json.loads(cf['summary.json'])
    if (summary.get('source_rows') != len(before) or summary.get('rows') != len(after)
            or summary.get('quarantined_rows') != len(excluded)
            or summary.get('masked_rows') != sum(d['action']=='mask_bathroom_composition' for d in decisions)
            or summary.get('action_counts') != dict(Counter(d['action'] for d in decisions))
            or summary.get('current_rows') != len(current(after))):
        raise ValueError('Revision summary disagrees with exact rows')
    return before,after,{'summary':summary,'decisions':decisions,
        'source_manifest_sha256':digest(reference/'complete.json'),
        'revision_manifest_sha256':digest(candidate/'complete.json'),
        'audit_manifest_sha256':digest(audit/'complete.json')}


def compare_contrasts(before,after,fields):
    """Support may change; compare identical physical scenarios with separate support."""
    support={'support','support_before','support_after','supported_endpoints'}
    def indexed(items):
        result={}
        for item in items:
            fixed={k:v for k,v in item.items() if k not in support|set(fields)|{'probability_first_increment_larger'}}
            key=canonical(fixed)
            if key in result:raise ValueError('Duplicate physical contrast')
            result[key]=(fixed,item)
        return result
    a,b=indexed(before),indexed(after)
    matched=[]
    for key in sorted(a.keys() & b.keys()):
        left,right=a[key][1],b[key][1]
        matched.append({**a[key][0],'reference_support':{k:v for k,v in left.items() if k in support},
            'candidate_support':{k:v for k,v in right.items() if k in support},
            'changes':{f:comparison.interval_change(left[f],right[f]) for f in fields}})
    return {'matched':matched,'reference_only':[a[k][1] for k in sorted(a.keys()-b.keys())],
            'candidate_only':[b[k][1] for k in sorted(b.keys()-a.keys())]}


def matched_residuals(a,b,before_report,after_report,rows,decisions):
    ai={r['audit_id']:r for r in a};bi={r['audit_id']:r for r in b}
    ids={r['audit_id'] for r in rows}
    if len(ai)!=len(a) or len(bi)!=len(b) or set(bi)!=ids or not ids <= ai.keys():
        raise ValueError('Residual membership differs from reviewed retained cohort')
    ref=[ai[k] for k in sorted(ids)];candidate=[bi[k] for k in sorted(ids)]
    result=comparison.residual_changes(ref,candidate,before_report,after_report)
    changes={k:bi[k]['fitted_rent']-ai[k]['fitted_rent'] for k in ids}
    row_by_id={r['audit_id']:r for r in rows};decision_by_id={r['audit_id']:r for r in decisions}
    selected=[];units=set()
    for key in sorted(ids,key=lambda k:(-abs(changes[k]),k)):
        row=row_by_id[key]
        if row['unit_id'] in units:continue
        units.add(row['unit_id'])
        selected.append({**{k:row[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent')},
            'reference_fitted_rent':ai[key]['fitted_rent'],'candidate_fitted_rent':bi[key]['fitted_rent'],
            'fitted_rent_change':changes[key],'reference_log_residual':ai[key]['residual_log'],
            'candidate_log_residual':bi[key]['residual_log'],'decision':decision_by_id.get(key)})
        if len(selected)==20:break
    result.update(reference_matched_median_absolute_log_residual=statistics.median(abs(r['residual_log']) for r in ref),
        candidate_matched_median_absolute_log_residual=statistics.median(abs(r['residual_log']) for r in candidate),
        median_absolute_fitted_rent_change=statistics.median(abs(v) for v in changes.values()),
        max_absolute_fitted_rent_change=max(abs(v) for v in changes.values()),largest_distinct_unit_movements=selected,
        excluded_reference_rows=[ai[k] for k in sorted(ai.keys()-ids)])
    return result


def build_comparison(reference,candidate,reference_dataset,candidate_dataset,audit):
    before,after,lineage=verify_revision(reference_dataset,candidate_dataset,audit)
    fits=[]
    for root,source in [(Path(reference),reference_dataset),(Path(candidate),candidate_dataset)]:
        report,provenance=verified.build_report(root,source,top=5)
        protocol=json.loads(comparison.bound_bytes(root/'protocol','protocol.json',provenance['protocol_manifest']))
        residuals=verified.jsonl(comparison.bound_bytes(root/'fit','residuals.jsonl',provenance['fit_manifest']))
        design_verification=verify_design(root,source,protocol,provenance)
        fits.append({'report':report,'protocol':protocol,'provenance':provenance,'residuals':residuals,
                     'design_verification':design_verification})
    a,b=fits;check_protocols(a['protocol'],b['protocol'])
    return {'version':VERSION,'revision':lineage,
        'fits':[{'experiment':f['report']['experiment'],'protocol':f['protocol'],'cohort':f['report']['cohort'],
            'diagnostics':f['report']['diagnostics'],
            'design_verification':f['design_verification'],
            'design_sha256':{name:f['provenance']['fit_manifest']['files'][name] for name in comparison.DESIGNS}} for f in fits],
        'bathrooms':{name:compare_contrasts(a['report']['bathrooms'][name],b['report']['bathrooms'][name],fields)
            for name,fields in [('full_bath_increments',('log_effect','percent_effect')),
                ('half_bath_increments',('log_effect','percent_effect')),('net_balance',('difference',))]},
        'residuals':matched_residuals(a['residuals'],b['residuals'],a['report'],b['report'],after,lineage['decisions']),
        'limitations':[comparison.LIMITATION,
            'Residual changes are evaluated on identical retained observations and unchanged asking-price targets; removed observations are listed separately.',
            'The source revision changes cohort membership and bathroom knownness. Source-derived centering, numeric scaling and group support are refitted and may change; raw standardized coefficients are deliberately not compared.',
            'Physical bathroom scenarios use each fitted design with separately reported endpoint support. A source correction is not an apartment renovation.',
            *a['report']['limitations']]},[f['provenance'] for f in fits]


def markdown_report(report):
    s=report['revision']['summary'];r=report['residuals']
    lines=['# Reviewed-source sensitivity','',f"{s['source_rows']:,} → {s['rows']:,} observations; {s['quarantined_rows']} quarantined and {s['masked_rows']} bathroom compositions masked. All {s['current_rows']} current captures retained.",
        '',comparison.LIMITATION,'',f"Matched-row median absolute log residual: {r['reference_matched_median_absolute_log_residual']:.6f} → {r['candidate_matched_median_absolute_log_residual']:.6f}.",
        f"Median absolute fitted-rent movement: ${r['median_absolute_fitted_rent_change']:.2f}; maximum: ${r['max_absolute_fitted_rent_change']:.2f}.",
        '', '| Bedrooms | Full baths | Reference % [95%] | Reviewed source % [95%] |', '| --- | --- | ---: | ---: |']
    def interval(v):return f"{v['median']:+.2f} [{v['lower_95']:+.2f}, {v['upper_95']:+.2f}]"
    for x in report['bathrooms']['full_bath_increments']['matched']:
        c=x['changes']['percent_effect']
        lines.append(f"| {x['bedrooms']} | {x['before_full_half'][0]} → {x['after_full_half'][0]} | {interval(c['reference'])} | {interval(c['candidate'])} |")
    lines+=['','All contrast support changes, separately supported/omitted scenarios, current residuals, largest distinct-unit movements, quarantined rows and verified source decisions are in comparison.json.',
            '',*['- '+s for s in report['limitations']]]
    return '\n'.join(lines)+'\n'


def run(reference,candidate,reference_dataset,candidate_dataset,audit,output):
    report,provenance=build_comparison(reference,candidate,reference_dataset,candidate_dataset,audit)
    paths=[Path(m.__file__) for m in (verified,comparison,noise,overlay)]+[Path(__file__)]
    return publish_bundle(output,{'comparison.json':canonical(report)+'\n','comparison.md':markdown_report(report),
        **{p.name:p.read_text() for p in paths}},
        {'version':VERSION,'experiments':provenance,'implementation_sha256':{p.name:digest(p) for p in paths}})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','reference_dataset','candidate_dataset','audit','output'):
        p.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    args=p.parse_args();result=run(**vars(args))
    print(canonical({'version':result['version'],'output':str(args.output)}))
