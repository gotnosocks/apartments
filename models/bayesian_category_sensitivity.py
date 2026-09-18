"""Descriptive comparison of independently fitted category contrast posteriors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report
from . import bayesian_category_contrasts as contrasts

VERSION='bayesian-category-prior-sensitivity-v1'
SAMPLING_SETTINGS={'chains','draws','tune','seed','target_accept','adaptation'}
LIMITATIONS=[
    'Independent fits are compared descriptively. Draws are not paired, and no posterior interval or probability is assigned to the difference between fit medians.',
    'The median shift is measured in percentage points between two conditional percentage-effect summaries; it is not an apartment-price change or a causal estimate.',
    'Matching intervals or signs under this one prior change does not establish general prior robustness, causal identification, adequate observation noise, or data correctness.',
    'Only feature-coefficient prior scales change; building/unit shrinkage and likelihood remain fixed. Category effects and group offsets may still depend on those other assumptions.',
    *contrasts.LIMITATIONS,
]


def sign_interval(effect):
    return 'positive' if effect['lower_95']>0 else 'negative' if effect['upper_95']<0 else 'includes_zero'


def compare(before,after,before_protocol,after_protocol):
    for result in (before,after):
        if result.get('version')!=contrasts.VERSION or result.get('status')!='all_supported_contrasts_converged':
            raise ValueError('Accepted complete category contrasts required')
        if any(item['status']!='supported_converged' or item['diagnostics'].get('acceptable') is not True
               or item['log_effect'] is None or item['percent_effect'] is None for item in result['contrasts']):
            raise ValueError('Every category interval must pass derived diagnostics')
    for key in ('source_observations_sha256','design_features','categories','omitted','highlight_ids','implementation_sha256'):
        if before[key]!=after[key]:raise ValueError('Category analysis source/design/support/code mismatch: '+key)
    changed={key:{'before':before_protocol.get(key),'after':after_protocol.get(key)}
             for key in before_protocol.keys()|after_protocol.keys() if before_protocol.get(key)!=after_protocol.get(key)}
    if not changed.keys() <= SAMPLING_SETTINGS|{'prior_multiplier'} or 'prior_multiplier' not in changed:
        raise ValueError('Only feature prior and sampling settings may differ')
    old={r['id']:r for r in before['contrasts']};new={r['id']:r for r in after['contrasts']}
    if len(old)!=len(before['contrasts']) or len(new)!=len(after['contrasts']) or old.keys()!=new.keys():
        raise ValueError('Category pair membership differs')
    rows=[]
    inferential={'diagnostics','log_effect','percent_effect','status'}
    for identity,a in old.items():
        b=new[identity]
        if {k:v for k,v in a.items() if k not in inferential}!={k:v for k,v in b.items() if k not in inferential}:
            raise ValueError('Category pair vector or endpoint/overlap support differs: '+identity)
        for item in (a,b):
            diag=item['diagnostics']
            if (any(not report.finite(diag.get(k)) for k in ('max_rhat','ess_bulk','ess_tail'))
                    or diag['max_rhat']>=1.01 or diag['ess_bulk']<400 or diag['ess_tail']<400):
                raise ValueError('Category derived diagnostics do not meet thresholds')
            report.check_interval(item['log_effect']);report.check_interval(item['percent_effect'])
        rows.append({k:v for k,v in a.items() if k not in inferential}|{
            'before':{k:a[k] for k in inferential},'after':{k:b[k] for k in inferential},
            'median_shift_percentage_points':b['percent_effect']['median']-a['percent_effect']['median'],
            'before_interval_sign':sign_interval(a['percent_effect']),
            'after_interval_sign':sign_interval(b['percent_effect'])})
    return {'changed_protocol_settings':changed,'contrasts':rows,
            'maximum_absolute_median_shift_percentage_points':max(abs(r['median_shift_percentage_points']) for r in rows),
            'interval_sign_changes':[r['id'] for r in rows if r['before_interval_sign']!=r['after_interval_sign']]}


def verified_case(directory,experiment,dataset):
    manifest,files=_verified_bundle(directory,retain={'contrasts.json'})
    result=json.loads(files['contrasts.json'])
    if manifest.get('version')!=contrasts.VERSION:raise ValueError('Unknown category report version')
    verified,fit_manifests=report.build_report(experiment,dataset,top=1)
    for kind,path in [('fit',experiment/'fit'),('protocol',experiment/'protocol'),('source',dataset)]:
        if result['bindings'][kind]!=digest(path/'complete.json'):
            raise ValueError('Category report does not match verified '+kind)
    if (result['protocol_sha256']!=verified['protocol_sha256']
            or result['source_observations_sha256']!=verified['source_observations_sha256']
            or result['posterior_sha256']!=fit_manifests['fit_manifest']['files']['posterior.nc']):
        raise ValueError('Category posterior/source identity differs from accepted fit')
    protocol=json.loads((experiment/'protocol/protocol.json').read_text())
    return result,protocol


def markdown(result):
    lines=['# Category coefficient prior sensitivity','',*[p+'\n' for p in LIMITATIONS],
           '| Category contrast | Baseline % [95% CrI] | Half prior scale % [95% CrI] | Median shift (percentage points) |',
           '|---|---:|---:|---:|']
    def effect(v):return f"{v['median']:+.3f} [{v['lower_95']:+.3f}, {v['upper_95']:+.3f}]"
    for row in result['contrasts']:
        lines.append(f"| {row['id']} | {effect(row['before']['percent_effect'])} | {effect(row['after']['percent_effect'])} | {row['median_shift_percentage_points']:+.4f} |")
    return '\n'.join(lines)+'\n'


def run(before,after,before_experiment,after_experiment,dataset,output):
    before,after,before_experiment,after_experiment,dataset,output=map(Path,
        (before,after,before_experiment,after_experiment,dataset,output))
    a,ap=verified_case(before,before_experiment,dataset);b,bp=verified_case(after,after_experiment,dataset)
    result={'version':VERSION,**compare(a,b,ap,bp),'limitations':LIMITATIONS,'main_model_changed':False,
            'bindings':{name:digest(path/'complete.json') for name,path in
                [('before_report',before),('after_report',after),('before_fit',before_experiment/'fit'),
                 ('after_fit',after_experiment/'fit'),('before_protocol',before_experiment/'protocol'),
                 ('after_protocol',after_experiment/'protocol'),('source',dataset)]},
            'before_source_observations_sha256':a['source_observations_sha256'],
            'after_source_observations_sha256':b['source_observations_sha256']}
    publish_bundle(output,{'comparison.json':canonical(result)+'\n','comparison.md':markdown(result),
                          Path(__file__).name:Path(__file__).read_text()}, {'version':VERSION})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','before-experiment','after-experiment','dataset','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    result=run(args.before,args.after,args.before_experiment,args.after_experiment,args.dataset,args.output)
    print(canonical({'pairs':len(result['contrasts']),'maximum_absolute_median_shift_percentage_points':result['maximum_absolute_median_shift_percentage_points']}))
