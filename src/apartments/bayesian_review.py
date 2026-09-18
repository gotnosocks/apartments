"""Read-only completed Bayesian research bundles; never open posterior arrays."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .corrections import canonical
from .research_pipeline import _verified_bundle, digest
from .analysis_review import bundle_signature

NAMES={
 'baseline':'chelsea-bayesian-long-report-20260918',
 'half':'chelsea-bayesian-prior-half-report-20260918',
 'categories':'chelsea-bayesian-category-contrasts-20260918',
 'half_categories':'chelsea-bayesian-category-prior-half-20260918',
 'sensitivity':'chelsea-bayesian-category-sensitivity-20260918',
 'bathroom_sensitivity':'chelsea-bayesian-prior-sensitivity-20260918',
}
REPORT_VERSION={'verified-bayesian-feature-report-v1','verified-bayesian-feature-report-v2'}
CATEGORY_VERSION='bayesian-category-contrasts-v1'
SENSITIVITY_VERSION='bayesian-category-prior-sensitivity-v1'


def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def interval(value):
    if (not isinstance(value,dict) or any(not finite(value.get(k)) for k in ('median','lower_95','upper_95','probability_positive'))
            or not value['lower_95']<=value['median']<=value['upper_95'] or not 0<=value['probability_positive']<=1):
        raise ValueError('Invalid posterior interval')


def diagnostics(diag,full=True):
    if diag.get('acceptable') is not True:raise ValueError('Unaccepted posterior diagnostics')
    keys=('max_rhat','min_ess_bulk','min_ess_tail') if full else ('max_rhat','ess_bulk','ess_tail')
    if any(not finite(diag.get(k)) for k in keys) or diag[keys[0]]>=1.01 or min(diag[keys[1]],diag[keys[2]])<400:
        raise ValueError('Posterior convergence thresholds failed')
    if full and (not finite(diag.get('min_bfmi')) or diag['min_bfmi']<.3
                 or any(diag.get(k)!=0 for k in ('divergences','maxdepth_reached','nonfinite_diagnostics'))):
        raise ValueError('Posterior sampler diagnostics failed')


def support(value):
    if (not isinstance(value,dict) or any(type(value.get(k)) is not int or value[k]<0 for k in ('rows','units','buildings'))
            or not value['buildings']<=value['units']<=value['rows']):
        raise ValueError('Invalid observation support')


def read_bound(root,manifest,name):
    if name not in manifest['files']:raise ValueError('Required saved fit product missing: '+name)
    path=Path(root)/name
    if path.is_symlink() or not path.is_file() or digest(path)!=manifest['files'][name]:
        raise ValueError('Saved fit product integrity mismatch: '+name)
    return path.read_bytes()


def load_bundle(path,name,version):
    manifest,files=_verified_bundle(path,retain={name})
    value=json.loads(files[name])
    versions={version} if isinstance(version,str) else version
    if manifest.get('version') not in versions or value.get('version')!=manifest.get('version'):
        raise ValueError('Unsupported research bundle schema')
    return value,manifest


def load_report(path):
    value,manifest=load_bundle(path,'report.json',REPORT_VERSION)
    if value.get('status')!='exploratory_converged':raise ValueError('Diagnostic-only reports cannot be displayed')
    for name in ('parameters','derived'):diagnostics(value['diagnostics'][name])
    experiment=Path(value['experiment'])
    fit=json.loads((experiment/'fit/complete.json').read_text())
    protocol_manifest=json.loads((experiment/'protocol/complete.json').read_text())
    if (fit.get('version') not in {'observable-bayesian-bathroom-experiment-v2','observable-bayesian-bathroom-experiment-v3'}
            or fit!=manifest['fit_manifest'] or protocol_manifest!=manifest['protocol_manifest']):
        raise ValueError('Report does not bind the completed experiment')
    protocol=json.loads(read_bound(experiment/'protocol',protocol_manifest,'protocol.json'))
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    if any(v!=ph for v in (value['protocol_sha256'],fit['protocol_sha256'],protocol_manifest['protocol_sha256'])):
        raise ValueError('Protocol identity mismatch')
    dataset=Path(protocol['source_directory'])
    source=json.loads((dataset/'complete.json').read_text())
    if (source!=manifest['source_manifest'] or digest(dataset/'complete.json')!=value['source_manifest_sha256']
            or protocol['source_manifest_sha256']!=value['source_manifest_sha256']
            or source['files']['observations.jsonl']!=value['source_observations_sha256']
            or protocol['source_observations_sha256']!=value['source_observations_sha256']):
        raise ValueError('Source dataset identity mismatch')
    summary=json.loads(read_bound(experiment/'fit',fit,'summary.json'))
    if (summary.get('status')!='exploratory_converged' or summary['protocol_sha256']!=ph
            or summary['diagnostics']!=value['diagnostics']['parameters']
            or summary['derived_diagnostics']!=value['diagnostics']['derived']):
        raise ValueError('Report differs from accepted fit summary')
    if any(protocol[k]!=v for k,v in value['method'].items() if k in protocol):
        raise ValueError('Report method differs from frozen protocol')
    if any(protocol[k]!=value['cohort'][k] for k in ('rows','units','buildings','current_rows')):
        raise ValueError('Report cohort differs from protocol')
    for key in ('full_bath_increments','half_bath_increments'):
        for item in value['bathrooms'][key]:
            interval(item['log_effect']);interval(item['percent_effect'])
            for side in ('support_before','support_after'):
                support(item[side])
                if item[side]['rows']==0:raise ValueError('Unsupported bathroom endpoint')
    for item in value['bathrooms']['net_balance']:
        interval(item['difference'])
        for s in item['support']:
            support(s)
            if s['rows']==0:raise ValueError('Unsupported bathroom balance')
    current=value['current_residuals']
    if len(current)!=protocol['current_rows'] or len({r['audit_id'] for r in current})!=len(current):
        raise ValueError('Current observation membership mismatch')
    current_ids={r['audit_id'] for r in current}
    saved={}
    # Read the saved residual text only; no posterior or inference library is used.
    for line in read_bound(experiment/'fit',fit,'residuals.jsonl').decode().split('\n'):
        if line.strip():
            row=json.loads(line)
            if row['audit_id'] in current_ids:saved[row['audit_id']]=row
    for row in current:
        if row['audit_id'] not in saved or any(row.get(k)!=v for k,v in saved[row['audit_id']].items()):
            raise ValueError('Current residual differs from fitted product')
        source_row=row['source_record']
        if (source_row.get('analysis_price_basis')!='current_capture_gross_ask'
                or any(str(source_row[k])!=str(row[k]) for k in ('audit_id','unit_id','building','source_listing_id','period'))
                or source_row['asking_rent']!=row['asking_rent']):
            raise ValueError('Current source identity mismatch')
        fields=('asking_rent','fitted_rent','residual_dollars','residual_log','latent_rent_lower_95','latent_rent_upper_95')
        if any(not finite(row.get(k)) for k in fields):raise ValueError('Invalid residual values')
        ask,fit_value=row['asking_rent'],row['fitted_rent']
        if (ask<=0 or not 0<row['latent_rent_lower_95']<=fit_value<=row['latent_rent_upper_95']
                or not math.isclose(row['residual_dollars'],ask-fit_value,abs_tol=1e-8)
                or not math.isclose(row['residual_log'],math.log(ask/fit_value),abs_tol=1e-10)):
            raise ValueError('Invalid residual arithmetic')
    return value,manifest,{'experiment':str(experiment),'dataset':str(dataset),'protocol_sha256':ph,
        'source_manifest_sha256':value['source_manifest_sha256'],
        'source_observations_sha256':value['source_observations_sha256'],
        'fit_manifest_sha256':digest(experiment/'fit/complete.json'),
        'protocol_manifest_sha256':digest(experiment/'protocol/complete.json'),
        'report_manifest_sha256':digest(Path(path)/'complete.json')}


def load_categories(path,research,identity,manifest):
    value,_=load_bundle(path,'contrasts.json',CATEGORY_VERSION)
    if value['status']!='all_supported_contrasts_converged':raise ValueError('Category report has withheld intervals')
    expected={'fit':identity['fit_manifest_sha256'],'protocol':identity['protocol_manifest_sha256'],
              'source':identity['source_manifest_sha256']}
    if (value['bindings']!=expected or value['protocol_sha256']!=identity['protocol_sha256']
            or value['source_observations_sha256']!=identity['source_observations_sha256']
            or value['posterior_sha256']!=manifest['fit_manifest']['files']['posterior.nc']):
        raise ValueError('Category report belongs to a different fit or dataset')
    fields={}
    for item in value['categories']:
        support(item['known']);support(item['unknown'])
        if item['known']['rows']+item['unknown']['rows']!=research['cohort']['rows']:
            raise ValueError('Category knownness totals differ from cohort')
        levels={}
        for level in item['levels']:
            support(level);levels[level['category']]={k:level[k] for k in ('rows','units','buildings')}
        if sum(v['rows'] for v in levels.values())!=item['known']['rows']:raise ValueError('Category level counts mismatch')
        fields[item['field']]=levels
    seen=set()
    for item in value['contrasts']:
        if item['id'] in seen or item['status']!='supported_converged':raise ValueError('Invalid category pair membership')
        seen.add(item['id']);diagnostics(item['diagnostics'],full=False)
        interval(item['log_effect']);interval(item['percent_effect'])
        for side in ('before','after'):
            if item['support_'+side]!=fields[item['field']].get(item[side]) or item['support_'+side]['rows']==0:
                raise ValueError('Category endpoint support mismatch')
        if item['before']==item['after']:raise ValueError('Identical category endpoints')
        for key in ('buildings','units'):
            overlap=item['overlap'][key]
            if type(overlap) is not int or not 0<=overlap<=min(item['support_before'][key],item['support_after'][key]):
                raise ValueError('Invalid within-building/unit overlap')
    return value


class BayesianWorkspace:
    @classmethod
    def load(cls,root):
        paths={key:Path(root)/name for key,name in NAMES.items()}
        baseline,bm,bi=load_report(paths['baseline']);half,hm,hi=load_report(paths['half'])
        if baseline['source_observations_sha256']!=half['source_observations_sha256'] or baseline['cohort']!=half['cohort']:
            raise ValueError('Research fits have different cohorts')
        categories=load_categories(paths['categories'],baseline,bi,bm)
        half_categories=load_categories(paths['half_categories'],half,hi,hm)
        sensitivity,_=load_bundle(paths['sensitivity'],'comparison.json',SENSITIVITY_VERSION)
        expected={'before_report':digest(paths['categories']/'complete.json'),'after_report':digest(paths['half_categories']/'complete.json'),
            'before_fit':bi['fit_manifest_sha256'],'after_fit':hi['fit_manifest_sha256'],
            'before_protocol':bi['protocol_manifest_sha256'],'after_protocol':hi['protocol_manifest_sha256'],'source':bi['source_manifest_sha256']}
        if sensitivity['bindings']!=expected:raise ValueError('Prior comparison does not bind these exact category reports')
        a={r['id']:r for r in categories['contrasts']};b={r['id']:r for r in half_categories['contrasts']}
        if a.keys()!=b.keys() or {r['id'] for r in sensitivity['contrasts']}!=a.keys():raise ValueError('Sensitivity pair membership mismatch')
        for row in sensitivity['contrasts']:
            old,new=a[row['id']],b[row['id']]
            for side,original in [('before',old),('after',new)]:
                if any(original[k]!=v for k,v in row[side].items()):raise ValueError('Sensitivity interval differs from bound category report')
            if any(old[k]!=new[k] for k in ('design_vector','support_before','support_after','overlap')):
                raise ValueError('Prior comparison changed category estimand')
            shift=new['percent_effect']['median']-old['percent_effect']['median']
            if not math.isclose(shift,row['median_shift_percentage_points'],abs_tol=1e-12):raise ValueError('Invalid prior median shift')
        maximum=max(abs(row['median_shift_percentage_points']) for row in sensitivity['contrasts'])
        if not finite(sensitivity.get('maximum_absolute_median_shift_percentage_points')) or not math.isclose(maximum,sensitivity['maximum_absolute_median_shift_percentage_points'],abs_tol=1e-12):
            raise ValueError('Invalid sensitivity maximum shift')
        if baseline['method']['prior_multiplier']!=1. or half['method']['prior_multiplier']!=.5:
            raise ValueError('This review requires baseline and half feature-prior fits')
        protocols=[json.loads((Path(identity['experiment'])/'protocol/protocol.json').read_text()) for identity in (bi,hi)]
        changed={key:{'before':protocols[0].get(key),'after':protocols[1].get(key)}
                 for key in protocols[0].keys()|protocols[1].keys() if protocols[0].get(key)!=protocols[1].get(key)}
        if sensitivity['changed_protocol_settings']!=changed or not changed.keys()<={'prior_multiplier','seed','tune','draws','chains','target_accept','adaptation'}:
            raise ValueError('Prior sensitivity changed model or source settings')
        result=cls();result.baseline=baseline;result.half=half;result.categories=categories
        result.half_categories=half_categories;result.sensitivity=sensitivity
        result.bathroom_sensitivity=load_bathroom_sensitivity(paths['bathroom_sensitivity'],baseline,half,bm,hm,bi,hi)
        result.identity={'baseline':bi,'half_prior':hi};return result


def workspace_signature(root):
    """Cache invalidation includes small fit products used above, never posterior.nc."""
    paths={key:Path(root)/name for key,name in NAMES.items()}
    signatures=[bundle_signature(*paths.values())]
    stamps=[]
    for key in ('baseline','half'):
        value=json.loads((paths[key]/'report.json').read_text());experiment=Path(value['experiment'])
        protocol=json.loads((experiment/'protocol/protocol.json').read_text())
        for path in (experiment/'fit/complete.json',experiment/'fit/summary.json',experiment/'fit/residuals.jsonl',
                     experiment/'protocol/complete.json',experiment/'protocol/protocol.json',Path(protocol['source_directory'])/'complete.json',Path(protocol['source_directory'])/'observations.jsonl'):
            stat=path.stat();stamps.append((str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
    return hashlib.sha256(canonical([signatures,stamps]).encode()).hexdigest()


def _bathroom_interval_change(before,after):
    return {'reference':before,'candidate':after,
            'median_change':after['median']-before['median'],
            'lower_endpoint_change':after['lower_95']-before['lower_95'],
            'upper_endpoint_change':after['upper_95']-before['upper_95'],
            'intervals_overlap_descriptively':max(before['lower_95'],after['lower_95'])<=min(before['upper_95'],after['upper_95'])}


def _bathroom_pair_tables(before,after,fields):
    def indexed(items):
        out={}
        for item in items:
            fixed={k:v for k,v in item.items() if k not in fields and k!='probability_first_increment_larger'}
            key=canonical(fixed)
            if key in out:raise ValueError('Duplicate bathroom comparison identity')
            out[key]=(fixed,item)
        return out
    a,b=indexed(before),indexed(after)
    if a.keys()!=b.keys():raise ValueError('Bathroom prior comparison changed endpoints or support')
    return [{**a[key][0],'changes':{field:_bathroom_interval_change(a[key][1][field],b[key][1][field]) for field in fields}}
            for key in sorted(a)]


def load_bathroom_sensitivity(path,baseline,half,bm,hm,bi,hi):
    value,manifest=load_bundle(path,'comparison.json','verified-bayesian-feature-prior-sensitivity-v1')
    expected={identity['experiment']:(research,meta,identity) for research,meta,identity in
              ((baseline,bm,bi),(half,hm,hi))}
    experiments=manifest['experiments']
    if len(experiments)!=2 or {item['experiment'] for item in experiments}!=expected.keys():
        raise ValueError('Bathroom comparison experiment membership mismatch')
    allowed={'chains','draws','tune','seed','prior_multiplier'}
    if set(value['allowed_protocol_changes'])!=allowed or value['reference_prior_multiplier']!=1.:
        raise ValueError('Unexpected bathroom prior reference or allowed settings')
    protocols={}
    for item in experiments:
        research,meta,identity=expected[item['experiment']]
        for key in ('fit_manifest','protocol_manifest','source_manifest'):
            if item[key]!=meta[key]:raise ValueError('Bathroom comparison manifest binding mismatch')
        hashes={'fit':identity['fit_manifest_sha256'],'protocol':identity['protocol_manifest_sha256'],'source':identity['source_manifest_sha256']}
        if item['manifest_sha256']!=hashes:raise ValueError('Bathroom comparison source/fit/protocol hash mismatch')
        protocol=json.loads((Path(identity['experiment'])/'protocol/protocol.json').read_text())
        protocols[identity['experiment']]=protocol
        if {k:v for k,v in protocol.items() if k not in allowed}!=value['fixed_protocol']:
            raise ValueError('Bathroom comparison fixed protocol differs from fitted source/model')
        designs={name:meta['fit_manifest']['files'][name] for name in ('feature-design.json','time-design.json','time-design.npz')}
        if value['design_sha256']!=designs:raise ValueError('Bathroom comparison design hashes differ')
    if value['cohort']!=baseline['cohort'] or len(value['fits'])!=2:raise ValueError('Bathroom comparison cohort mismatch')
    if {item['experiment'] for item in value['fits']}!=expected.keys():raise ValueError('Bathroom comparison fit membership mismatch')
    for item in value['fits']:
        research,_,identity=expected[item['experiment']];protocol=protocols[item['experiment']]
        if (item['protocol_sha256']!=identity['protocol_sha256'] or item['diagnostics']!=research['diagnostics']
                or item['sampling_and_prior']!={k:protocol[k] for k in allowed}):
            raise ValueError('Bathroom comparison fit diagnostics or settings mismatch')
    if len(value['comparisons'])!=1 or value['comparisons'][0]['candidate_prior_multiplier']!=.5:
        raise ValueError('Bathroom comparison candidate mismatch')
    comparison=value['comparisons'][0]
    tables={key:_bathroom_pair_tables(baseline['bathrooms'][key],half['bathrooms'][key],fields)
            for key,fields in [('full_bath_increments',('log_effect','percent_effect')),
                               ('half_bath_increments',('log_effect','percent_effect')),('net_balance',('difference',))]}
    if comparison['bathrooms']!=tables:raise ValueError('Bathroom sensitivity values or endpoint support differ from bound reports')
    a={r['audit_id']:r for r in baseline['current_residuals']};b={r['audit_id']:r for r in half['current_residuals']}
    current=comparison['residuals']['current_rows']
    if len(current)!=len(a) or {r['audit_id'] for r in current}!=a.keys() or a.keys()!=b.keys():
        raise ValueError('Bathroom sensitivity current residual membership mismatch')
    movements=[]
    for row in current:
        old,new=a[row['audit_id']],b[row['audit_id']]
        for key in ('unit_id','building','source_listing_id','period','asking_rent'):
            if row[key]!=old[key] or row[key]!=new[key]:raise ValueError('Prior residual identity mismatch')
        for side,original in [('reference',old),('candidate',new)]:
            if any(original[k]!=v for k,v in row[side].items()):raise ValueError('Prior residual values differ from bound reports')
        for key,delta in row['changes'].items():
            if not math.isclose(delta,new[key]-old[key],abs_tol=1e-10):raise ValueError('Prior residual change arithmetic mismatch')
        movements.append(abs(new['fitted_rent']-old['fitted_rent']))
    # Stream source text once to establish the number of distinct advertisements
    # informing the second-half coefficient. Never retain the full source dataset.
    source_path=Path(bi['dataset'])/'observations.jsonl';source_hash=hashlib.sha256();rare=[]
    if source_path.is_symlink():raise ValueError('Source observations must be a regular bound file')
    with source_path.open('rb') as handle:
        for line in handle:
            source_hash.update(line)
            if not line.strip():continue
            row=json.loads(line)
            full,halves,total=(row.get(k) for k in ('reported_full_bathrooms','reported_half_bathrooms','bathrooms'))
            if (all(finite(v) for v in (full,halves,total)) and full>=1 and int(full)==full
                    and halves>=2 and int(halves)==halves and not row['bathroom_count_evidence'].get('flags')
                    and math.isclose(total,full+.5*halves,rel_tol=0,abs_tol=1e-8)):
                rare.append({k:row[k] for k in ('audit_id','source_listing_id','unit_id','building','bedrooms','reported_full_bathrooms','reported_half_bathrooms')})
    if source_hash.hexdigest()!=bi['source_observations_sha256']:raise ValueError('Second-half support source integrity mismatch')
    return {'tables':tables,'maximum_current_fitted_rent_movement':max(movements),
            'current_rows':len(current),'second_half_support':{'rows':len(rare),
                'advertisements':len({str(r['source_listing_id']) for r in rare}),
                'units':len({r['unit_id'] for r in rare}),'records':rare},
            'comparison_manifest_sha256':digest(Path(path)/'complete.json')}
