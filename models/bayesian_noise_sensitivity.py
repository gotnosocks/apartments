"""Compare same-cohort shared/bedroom-noise fits without pairing posterior draws."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from . import bayesian_feature_report as verified
from . import bayesian_feature_sensitivity as comparison

VERSION = 'verified-bayesian-noise-sensitivity-v1'
V2 = 'observable-bayesian-bathroom-experiment-v2'
V3 = 'observable-bayesian-bathroom-experiment-v3'
VARIABLE = {'version','chains','draws','tune','seed','graph','graph_verification',
            'implementation_sha256','likelihood','residual_scale','graph_configuration',
            'building_prior_scale','unit_prior_scale','residual_parameterization'}
V3_CODE = {'bayesian_feature_experiment_v3.py','bayesian_feature_graph_v3.py'}


def check_protocols(reference, candidate):
    if reference.get('version') not in (V2,V3) or candidate.get('version') != V3:
        raise ValueError('A v2/v3 shared reference and v3 bedroom candidate are required')
    if reference.get('residual_scale','shared') != 'shared' or candidate.get('residual_scale') != 'bedroom':
        raise ValueError('Compare shared reference against bedroom residual scale only')
    for protocol in (reference,candidate):
        if protocol.get('residual_parameterization','noncentered') not in ('centered','noncentered'):
            raise ValueError('Unknown residual hierarchy parameterization')
        for key,minimum in [('chains',2),('draws',1),('tune',1),('seed',0)]:
            if type(protocol.get(key)) is not int or protocol[key] < minimum:
                raise ValueError('Invalid sampling protocol')
    if {k:v for k,v in reference.items() if k not in VARIABLE} != {k:v for k,v in candidate.items() if k not in VARIABLE}:
        raise ValueError('Fixed source, mean, feature prior, sampler or environment protocol differs')
    for name,default in [('building_prior_scale',.35),('unit_prior_scale',.25)]:
        if reference.get(name,default) != candidate.get(name):
            raise ValueError('Group priors differ in noise-only comparison')
    before,after = (p['implementation_sha256'] for p in (reference,candidate))
    if reference['version'] == V2:
        if not before or set(after)-set(before) != V3_CODE or any(after.get(k) != v for k,v in before.items()):
            raise ValueError('V3 must preserve every archived v2 implementation dependency')
    elif before != after:
        raise ValueError('Same-version implementations differ')


def build_comparison(reference, candidate, dataset):
    fits = []
    for root in map(Path,(reference,candidate)):
        report,provenance = verified.build_report(root,dataset,top=5)
        protocol = json.loads(comparison.bound_bytes(root/'protocol','protocol.json',provenance['protocol_manifest']))
        residuals = verified.jsonl(comparison.bound_bytes(root/'fit','residuals.jsonl',provenance['fit_manifest']))
        fits.append({'report':report,'protocol':protocol,'residuals':residuals,'provenance':provenance})
    a,b = fits
    check_protocols(a['protocol'],b['protocol'])
    hashes = [{name:f['provenance']['fit_manifest']['files'][name] for name in comparison.DESIGNS} for f in fits]
    if hashes[0] != hashes[1]:
        raise ValueError('Exact saved mean-design hashes differ')
    before,after = a['report'],b['report']
    result = {'version':VERSION,'cohort':before['cohort'],'design_sha256':hashes[0],
        'source_observations_sha256':before['source_observations_sha256'],
        'fits':[{'experiment':f['report']['experiment'],'protocol':f['protocol'],
                 'diagnostics':f['report']['diagnostics'],
                 'median_absolute_log_residual':f['report']['median_absolute_log_residual'],
                 'residual_scales':f['report'].get('residual_scales')} for f in fits],
        'bathrooms':{name:comparison.compare_tables(before['bathrooms'][name],after['bathrooms'][name],fields)
            for name,fields in [('full_bath_increments',('log_effect','percent_effect')),
                ('half_bath_increments',('log_effect','percent_effect')),('net_balance',('difference',))]},
        'coefficients':{name:comparison.coefficient_changes(before['coefficients'][name],after['coefficients'][name])
            for name in ('encoded_value_coefficients','reporting_coefficients')},
        'residuals':comparison.residual_changes(a['residuals'],b['residuals'],before,after),
        'limitations':[comparison.LIMITATION,
            'Only residual-scale structure changes; source rows, targets, encoded mean design and mean priors match. Both fits pass parameter and derived diagnostics. This comparison does not establish predictive calibration.',
            *before['limitations']]}
    return result,[f['provenance'] for f in fits]


def markdown_report(report):
    lines = ['# Residual-scale sensitivity','',f"{report['cohort']['rows']:,} identical observations; shared versus bedroom-dependent Student-t scales.",
        '',comparison.LIMITATION,'','| Bedrooms | Full baths | Shared median [95%] | Bedroom-scale median [95%] | Median change (percentage points) |',
        '| --- | --- | ---: | ---: | ---: |']
    def interval(x):
        return f"{x['median']:+.2f}% [{x['lower_95']:+.2f}, {x['upper_95']:+.2f}]"
    for row in report['bathrooms']['full_bath_increments']:
        c=row['changes']['percent_effect']
        lines.append(f"| {row['bedrooms']} | {row['before_full_half'][0]} → {row['after_full_half'][0]} | {interval(c['reference'])} | {interval(c['candidate'])} | {c['median_change']:+.2f} |")
    lines += ['',f"Signed residual rank correlation: {report['residuals']['signed_log_residual']['spearman_rho']}. Absolute residual rank correlation: {report['residuals']['absolute_log_residual']['spearman_rho']}.",
        '', 'Full source support, separate posterior intervals, coefficient changes, current-apartment residual changes, protocols and diagnostic evidence are retained in comparison.json.',
        '',*['- '+s for s in report['limitations']]]
    return '\n'.join(lines)+'\n'


def run(reference,candidate,dataset,output):
    report,provenance = build_comparison(reference,candidate,dataset)
    paths = [Path(__file__),Path(verified.__file__),Path(comparison.__file__)]
    return publish_bundle(output,{'comparison.json':canonical(report)+'\n','comparison.md':markdown_report(report),
        **{p.name:p.read_text() for p in paths}},
        {'version':VERSION,'experiments':provenance,'implementation_sha256':{p.name:digest(p) for p in paths}})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','dataset','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=run(args.reference,args.candidate,args.dataset,args.output)
    print(canonical({'version':result['version'],'output':str(args.output)}))
