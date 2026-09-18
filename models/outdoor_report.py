"""Compare outdoor source policies on the same apartments and fitted targets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle


def load_experiment(root):
    root=Path(root)
    sm,sf=_verified_bundle(root/'summary',retain={'results.json'})
    pm,pf=_verified_bundle(root/'protocol',retain={'protocol.json'})
    if sm['protocol_sha256']!=pm['protocol_sha256']:raise ValueError('Experiment protocol mismatch')
    protocol=json.loads(pf['protocol.json']);results=json.loads(sf['results.json'])
    cm,cf=_verified_bundle(root/'standard/comparison',retain={'fitted-values.jsonl'})
    if cm['protocol_sha256']!=sm['protocol_sha256']:raise ValueError('Comparison protocol mismatch')
    rows=[json.loads(s) for s in cf['fitted-values.jsonl'].decode().split('\n') if s]
    return sm,protocol,results,rows


def run(structured,corroborated,interior,output):
    sm,sp,sr,srows=load_experiment(structured)
    cm,cp,cr,crows=load_experiment(corroborated)
    if sp['dataset_manifest']['interior_manifest']!=cp['dataset_manifest']['interior_manifest']:
        raise ValueError('Source policies do not share interior inputs')
    if cp['dataset_manifest'].get('structured_projection_manifest')!=sp['dataset_manifest']:
        raise ValueError('Corroboration policy must derive from this structured dataset')
    sby={r['audit_id']:r for r in srows};cby={r['audit_id']:r for r in crows}
    if set(sby)!=set(cby) or len(sby)!=len(srows) or len(cby)!=len(crows):raise ValueError('Membership mismatch')
    for key in sby:
        if any(sby[key][f]!=cby[key][f] for f in ('asking_rent','unit_id','building','period','shared_outdoor_category','advertised_ceiling_feet','advertised_levels')):
            raise ValueError('Source-policy comparison changed targets or nonprivate inputs')
    reference,_=_verified_bundle(Path(interior)/'summary')
    ipm,ipf=_verified_bundle(Path(interior)/'protocol',retain={'protocol.json'})
    if (ipm['protocol_sha256']!=reference['protocol_sha256'] or
        json.loads(ipf['protocol.json'])['dataset_manifest']!=sp['dataset_manifest']['interior_manifest']):
        raise ValueError('Reference interior source dataset differs')
    parity={}
    for name in ('standard','weaker_groups','stronger_groups'):
        im,inf=_verified_bundle(Path(interior)/name/'values',retain={'log-fitted.json'})
        if im['protocol_sha256']!=reference['protocol_sha256']:raise ValueError('Prior interior protocol mismatch')
        old=np.exp(np.array(json.loads(inf['log-fitted.json'])))
        for label,root in [('structured',structured),('corroborated',corroborated)]:
            _,f=_verified_bundle(Path(root)/name/'interior',retain={'log-fitted.json'})
            new=np.exp(np.array(json.loads(f['log-fitted.json'])))
            if len(new)!=len(old):raise ValueError('Reference row count differs')
            error=float(max(abs(new-old)))
            if error>.02:raise ValueError('Reference model differs beyond numerical tolerance')
            parity[label+'/'+name]=error
    comparison=[]
    for label,results in [('structured',sr),('corroborated',cr)]:
        for item in results:
            values=item['results']['types']
            comparison.append({'policy':label,'settings':item['settings'],
                'metrics':{v:d['metrics'] for v,d in item['results'].items()},
                'triplex_contrast_by_variant':{v:next(c['rent_percent_change'] for c in d['interior_contrasts'] if c['field']=='advertised_levels') for v,d in item['results'].items()},
                'outdoor_contrasts':values['outdoor_contrasts'],'comparisons':item['comparisons']})
    diagnostics=[]
    for key,r in sby.items():
        other=cby[key]
        diagnostics.append({k:r[k] for k in ('audit_id','source_listing_id','unit_id','period','asking_rent','analysis_price_basis','advertised_levels','shared_outdoor_category')} |
            {'structured_private_category':r['private_outdoor_category'],'corroborated_private_category':other['private_outdoor_category'],
             'interior_fitted_rent':r['interior_fitted_rent'],'structured_fitted_rent':r['types_fitted_rent'],
             'corroborated_fitted_rent':other['types_fitted_rent'],
             'corroborated_minus_structured_dollars':other['types_fitted_rent']-r['types_fitted_rent'],
             'structured_residual_dollars':r['asking_rent']-r['types_fitted_rent'],
             'corroborated_residual_dollars':r['asking_rent']-other['types_fitted_rent']})
    current=[r for r in diagnostics if r['analysis_price_basis']=='current_capture_gross_ask']
    selected=[];units=set()
    for r in sorted(diagnostics,key=lambda r:(-abs(r['corroborated_minus_structured_dollars']),r['audit_id'])):
        if r['unit_id'] in units:continue
        units.add(r['unit_id']);selected.append(r)
        if len(selected)==20:break
    changes=[abs(r['corroborated_minus_structured_dollars']) for r in diagnostics]
    cross_policy={'rows':len(diagnostics),'median_absolute_fitted_change_dollars':float(np.median(changes)),
                  'maximum_absolute_fitted_change_dollars':float(max(changes))}
    lines=['# Outdoor source-policy sensitivity','',f'Both policies retain the same {len(diagnostics):,} observations and price targets. Eighteen fits compare interior-only, outdoor reporting, and outdoor-type contrasts under three group penalties.','',
        '| Policy | Group penalties | Interior log RMSE | Reporting log RMSE | Types log RMSE | Triplex contrast after types | Terrace vs balcony | Garden vs balcony |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in comparison:
        outdoor=r['outdoor_contrasts']
        numbers=' | '.join(f"{r['metrics'][v]['log_rmse']:.6f}" for v in ('interior','reporting','types'))
        effects=[r['triplex_contrast_by_variant']['types'],outdoor[0]['rent_percent_change'],outdoor[1]['rent_percent_change']]
        effect_text=' | '.join('unsupported' if v is None else f'{v:+.3f}%' for v in effects)
        lines.append(f"| {r['policy']} | {r['settings']} | {numbers} | {effect_text} |")
    lines+=['',f"At standard penalties, switching source policy changes fitted rent by a median absolute ${cross_policy['median_absolute_fitted_change_dollars']:.2f}; the maximum is ${cross_policy['maximum_absolute_fitted_change_dollars']:,.2f}.",
        'Comparisons are conditional associations among reported type subsets. They are not physical private-space presence premiums, causal amenity values or comparisons of exhaustive outdoor inventories.',
        'Structured private fields can accompany shared-space or garden-view descriptions. Text corroboration reduces that ambiguity but creates substantial nonrandom missingness and can reject genuine coexisting private/shared amenities. Policy differences combine source quality and selection effects.',
        'Outdoor square footage remains excluded: reviewed examples mix shared facilities, unit-private areas, aggregate terraces, lower bounds and approximate quantities. Historical effective times remain unverified.', '',
        '## Current captures','',
        '| Advertisement | Ask | Interior fit | Structured types fit | Corroborated types fit | Corroborated ask minus fit |',
        '|---|---:|---:|---:|---:|---:|']
    for r in current:
        lines.append(f"| {r['source_listing_id']} | ${r['asking_rent']:,.0f} | ${r['interior_fitted_rent']:,.0f} | ${r['structured_fitted_rent']:,.0f} | ${r['corroborated_fitted_rent']:,.0f} | {r['corroborated_residual_dollars']:+,.0f} |")
    lines+=['','These are in-sample residual diagnostics. Review the largest policy-driven changes against source evidence before promoting an encoding. The main reviewed analysis model remains unchanged.']
    return publish_bundle(output,{'report.md':'\n'.join(lines)+'\n','comparisons.json':canonical(comparison)+'\n',
        'cross-policy.json':canonical(cross_policy)+'\n','reference-parity.json':canonical(parity)+'\n',
        'current-comparison.jsonl':''.join(canonical(r)+'\n' for r in current),
        'policy-review-queue.jsonl':''.join(canonical(r)+'\n' for r in selected),'report.py':Path(__file__).read_text()},
        {'version':'outdoor-policy-comparison-v1','structured_summary':sm,'corroborated_summary':cm,
         'interior_summary':reference,'implementation_sha256':digest(__file__)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('structured','corroborated','interior','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();run(**vars(args))
