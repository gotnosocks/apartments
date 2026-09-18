from copy import deepcopy
import json
import math

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest
from models import bayesian_source_sensitivity as m
from .test_research_scope_overlay import bundles
from .test_bayesian_feature_report import interval


def reseal(folder,name,value):
    (folder/name).write_text(value)
    manifest=json.loads((folder/'complete.json').read_text())
    manifest['files'][name]=digest(folder/name)
    (folder/'complete.json').write_text(canonical(manifest)+'\n')


@pytest.fixture
def revision(tmp_path):
    source,decisions,audit=bundles(tmp_path)
    output=tmp_path/'revision'
    m.overlay.run(source,decisions,audit,output)
    return source,output,audit


def test_revision_rechecked_against_original_captures(revision):
    before,after,evidence=m.verify_revision(*revision)
    assert len(before)==3 and len(after)==2
    assert after[0]['asking_rent']==before[0]['asking_rent']==3500
    assert evidence['summary']['masked_rows']==1
    assert evidence['summary']['quarantined_rows']==1
    assert evidence['summary']['current_rows']==1
    assert len(evidence['decisions'])==2


@pytest.mark.parametrize('mutation',['target','unit','count','flag','membership','duplicate','quarantine','summary','evidence'])
def test_rehashed_revision_changes_still_rejected(revision,mutation):
    source,output,audit=revision
    name='observations.jsonl'
    rows=m.overlay.rows((output/name).read_bytes())
    if mutation=='target':rows[0]['asking_rent']+=1
    if mutation=='unit':rows[0]['unit_id']='other'
    if mutation=='count':rows[0]['reported_full_bathrooms']=2
    if mutation=='flag':rows[0]['bathroom_count_evidence']['flags']=[]
    if mutation=='membership':rows=rows[:1]
    if mutation=='duplicate':rows.append(rows[0])
    if mutation=='quarantine':
        name='quarantined.jsonl';rows=m.overlay.rows((output/name).read_bytes());rows[0]['observation']['asking_rent']+=1
    if mutation=='summary':
        value=json.loads((output/'summary.json').read_text());value['masked_rows']=999
        reseal(output,'summary.json',canonical(value)+'\n')
    elif mutation=='evidence':
        name='decisions.jsonl';rows=m.overlay.rows((output/name).read_bytes());rows[0]['evidence'][0]['description']='forged'
        reseal(output,name,''.join(canonical(r)+'\n' for r in rows))
    else:reseal(output,name,''.join(canonical(r)+'\n' for r in rows))
    with pytest.raises(ValueError):m.verify_revision(source,output,audit)


def protocols():
    a={'version':m.noise.V2,'chains':4,'draws':4000,'tune':1000,'seed':71,
       'specification':'full_half_balance','prior_multiplier':1.,'adaptation':'diag','target_accept':.93,
       'versions':{'synthetic':'1'},'implementation_sha256':{'original.py':'abc'},
       'source_manifest_sha256':'old','source_observations_sha256':'old-observations',
       'source_version':m.overlay.SOURCE_VERSION,'source_directory':'original','rows':100,'units':90,'buildings':10,'current_rows':13}
    b={**a,'version':m.noise.V3,'tune':2000,'seed':72,'rows':99,'units':89,'buildings':9,
       'source_manifest_sha256':'new','source_observations_sha256':'new-observations',
       'source_version':m.overlay.VERSION,'source_directory':'revision','residual_scale':'shared',
       'building_prior_scale':.35,'unit_prior_scale':.25,'graph_configuration':{'residual_scale':'shared'},
       'implementation_sha256':{**a['implementation_sha256'],**{n:'extra' for n in m.noise.V3_CODE}}}
    return a,b


def test_source_changes_allowed_but_all_model_settings_fixed():
    a,b=protocols();m.check_protocols(a,b)
    a={**b,**{k:a[k] for k in m.SOURCE_FIELDS}}
    m.check_protocols(a,b)


@pytest.mark.parametrize('parameterization',['centered','noncentered'])
def test_shared_source_comparison_allows_recorded_computational_parameterization(parameterization):
    a,b=protocols()
    b['residual_parameterization']=parameterization
    m.check_protocols(a,b)


def test_source_comparison_rejects_unknown_parameterization():
    a,b=protocols();b['residual_parameterization']='unknown'
    with pytest.raises(ValueError,match='parameterization'):
        m.check_protocols(a,b)


@pytest.mark.parametrize('change',[
    {'prior_multiplier':.5},{'specification':'full_half'}, {'residual_scale':'bedroom'},
    {'building_prior_scale':.7},{'unit_prior_scale':.5},{'adaptation':'low_rank'},
    {'target_accept':.99},{'versions':{'synthetic':'2'}},{'draws':0},{'chains':True},
    {'implementation_sha256':{'original.py':'changed',**{n:'extra' for n in m.noise.V3_CODE}}},
])
def test_conflated_model_or_environment_changes_rejected(change):
    a,b=protocols();b.update(change)
    with pytest.raises(ValueError):m.check_protocols(a,b)


def test_physical_contrast_identity_preserved_with_separate_support_and_omissions():
    before=[{'bedrooms':2,'before_full_half':[1,0],'after_full_half':[2,0],
        'support_before':{'rows':5},'support_after':{'rows':6},'log_effect':interval(.2)}]
    after=deepcopy(before);after[0]['support_after']['rows']=4;after[0]['log_effect']=interval(.19)
    before.append({'bedrooms':2,'before_full_half':[4,0],'after_full_half':[5,0],
                   'support_before':{'rows':2},'support_after':{'rows':1},'log_effect':interval(.3)})
    result=m.compare_contrasts(before,after,('log_effect',))
    assert len(result['matched'])==1 and len(result['reference_only'])==1
    row=result['matched'][0]
    assert row['reference_support']['support_after']['rows']==6
    assert row['candidate_support']['support_after']['rows']==4
    assert row['changes']['log_effect']['median_change']==pytest.approx(-.01)
    assert row['changes']['log_effect']['reference']==before[0]['log_effect']
    with pytest.raises(ValueError,match='Duplicate'):
        m.compare_contrasts(before+before,after,('log_effect',))


def test_matched_residuals_exclude_quarantines_from_both_metrics_and_pair_by_id():
    rows=[{'audit_id':str(i),'source_listing_id':str(100+i),'unit_id':'u'+str(i//2),
           'building':'b','period':'2026-09-01','asking_rent':3000.} for i in range(4)]
    def fitted(row,fit):
        return {**row,'fitted_rent':fit,'residual_log':math.log(3000/fit),'residual_dollars':3000-fit}
    before=[fitted(r,3000 if i<3 else 300) for i,r in enumerate(rows)]
    after=[fitted(r,2990+5*i) for i,r in enumerate(rows[:3])][::-1]
    reports={'current_residuals':[]}
    result=m.matched_residuals(before,after,reports,reports,rows[:3],[])
    assert result['rows']==3
    assert result['reference_matched_median_absolute_log_residual']==0
    assert result['max_absolute_fitted_rent_change']==10
    assert len(result['largest_distinct_unit_movements'])==2
    assert result['largest_distinct_unit_movements'][0]['audit_id']=='0'
    assert result['excluded_reference_rows']==[before[-1]]
    with pytest.raises(ValueError,match='membership'):
        m.matched_residuals(before,after[:-1],reports,reports,rows[:3],[])


# Actual construction and saved-product integration: no graph compilation or sampling.
import hashlib
import importlib.metadata
import io
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.research_pipeline import publish_bundle
from .test_bayesian_feature_model import train
from .test_bayesian_feature_report import diagnostics, publish_binary
from .test_research_scope_overlay import decision


def design_source(frame):
    rows=json.loads(frame.to_json(orient='records',date_format='iso'))
    for i,r in enumerate(rows):
        r.update(audit_id='a'+str(i),source_listing_id=str(1000+i),period=r['period'][:10],
                 listed_floor=float(i%13),canonical_unit_url='https://streeteasy.com/building/example/'+str(i),
                 known_at='2026-09-18T12:00:00+00:00',capture_ids=[i],
                 analysis_price_basis='current_capture_gross_ask' if i==0 else 'historical_initial_own_advertisement_ask')
        r['bathroom_count_evidence']['capture_ids']=[i]
    return rows


def converted(rows):
    data=pd.DataFrame(rows);data.period=pd.to_datetime(data.period)
    data.square_feet=pd.to_numeric(data.square_feet,errors='coerce')
    return data


def runtime_identity():
    feature,paths=m.reconstruction_dependencies()
    code={p.name:p.read_bytes() for p in paths}
    return feature,code,{name:importlib.metadata.version(name) for name in ('numpy','pandas','scipy')}


def design_archive(tmp_path,rows,version=m.noise.V2):
    feature,code,versions=runtime_identity()
    source=tmp_path/'source'
    manifest=publish_bundle(source,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
                            {'version':m.overlay.SOURCE_VERSION})
    protocol={'version':version,'specification':'full_half_balance','rows':len(rows),
              'source_manifest_sha256':digest(source/'complete.json'),
              'source_observations_sha256':manifest['files']['observations.jsonl'],
              'source_version':manifest['version'],'implementation_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in code.items()},
              'versions':versions}
    ph=m.overlay.sha(protocol)
    root=tmp_path/'experiment';target=root/'fit';target.mkdir(parents=True)
    feature.FeatureDesign(converted(rows),protocol['specification']).save(target)
    pm=publish_binary(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**code},
                      {'version':version,'protocol_sha256':ph})
    fm=publish_binary(target,{name:(target/name).read_bytes() for name in m.comparison.DESIGNS},
                      {'version':version,'protocol_sha256':ph})
    return root,source,protocol,{'protocol_manifest':pm,'fit_manifest':fm}


@pytest.fixture
def actual_design(tmp_path,train):
    return design_archive(tmp_path,design_source(train))


def test_design_reconstruction_matches_all_saved_semantics(actual_design):
    result=m.verify_design(*actual_design)
    assert result['verified'] and result['rows']==300
    assert set(result['time_arrays'])=={'time_matrix','season_matrix'}
    assert result['time_arrays']['season_matrix']['shape']==[12,11]
    assert result['time_arrays']['time_matrix']['dtype']=='float64'


@pytest.mark.parametrize('mutation',['center','numeric_scale','prior_scale','active','category_basis',
                                    'category_order','time_center','size_median','group_order'])
def test_independently_rehashed_design_changes_rejected(actual_design,mutation):
    root,source,protocol,provenance=actual_design
    name='time-design.json' if mutation in {'time_center','size_median','group_order'} else 'feature-design.json'
    path=root/'fit'/name;value=json.loads(path.read_text())
    if mutation=='center':value['means'][0]+=.1
    if mutation=='numeric_scale':value['numeric']['listed_floor']['scale']*=2
    if mutation=='prior_scale':value['prior_scales'][0]*=2
    if mutation=='active':value['active'][0]=not value['active'][0]
    if mutation=='category_basis':value['categories']['laundry_type']['basis'][0][0]+=.1
    if mutation=='category_order':value['categories']['laundry_type']['levels'].reverse()
    if mutation=='time_center':value['time_center'][0]+=.1
    if mutation=='size_median':value['size_default']+=10
    if mutation=='group_order':value['buildings'].reverse()
    path.write_text(canonical(value)+'\n');provenance['fit_manifest']['files'][name]=digest(path)
    with pytest.raises(ValueError,match='exact source reconstruction'):
        m.verify_design(root,source,protocol,provenance)


@pytest.mark.parametrize('mutation',['time_values','season_order','dtype','shape','missing','extra'])
def test_rehashed_npz_array_values_types_shapes_and_membership_rejected(actual_design,mutation):
    root,source,protocol,provenance=actual_design;path=root/'fit'/'time-design.npz'
    with np.load(path,allow_pickle=False) as saved:arrays={name:saved[name].copy() for name in saved.files}
    if mutation=='time_values':arrays['time_matrix'][0,0]+=.1
    if mutation=='season_order':arrays['season_matrix']=arrays['season_matrix'][:,::-1]
    if mutation=='dtype':arrays['time_matrix']=arrays['time_matrix'].astype('float32')
    if mutation=='shape':arrays['time_matrix']=arrays['time_matrix'].reshape(-1)
    if mutation=='missing':del arrays['season_matrix']
    if mutation=='extra':arrays['undeclared']=np.zeros(3)
    np.savez_compressed(path,**arrays);provenance['fit_manifest']['files'][path.name]=digest(path)
    with pytest.raises(ValueError,match='Saved time design array'):
        m.verify_design(root,source,protocol,provenance)


def test_json_format_and_npz_container_bytes_are_not_design_semantics(actual_design):
    root,source,protocol,provenance=actual_design
    for name in ('feature-design.json','time-design.json'):
        path=root/'fit'/name;value=json.loads(path.read_text())
        path.write_text(json.dumps(dict(reversed(list(value.items()))),indent=5)+'\n')
        provenance['fit_manifest']['files'][name]=digest(path)
    path=root/'fit'/'time-design.npz'
    with np.load(path,allow_pickle=False) as saved:arrays={name:saved[name].copy() for name in reversed(saved.files)}
    np.savez(path,**arrays);provenance['fit_manifest']['files'][path.name]=digest(path)
    assert m.verify_design(root,source,protocol,provenance)['verified']


@pytest.mark.parametrize('mutation',['missing_code','changed_code','changed_environment','changed_source'])
def test_reconstruction_fails_before_use_of_mismatched_dependencies(actual_design,mutation,monkeypatch):
    root,source,protocol,provenance=actual_design
    if mutation=='missing_code':del protocol['implementation_sha256']['bayesian_feature_model.py']
    if mutation=='changed_code':protocol['implementation_sha256']['bayesian_feature_model.py']='0'*64
    if mutation=='changed_environment':protocol['versions']['numpy']='different'
    if mutation=='changed_source':protocol['source_observations_sha256']='0'*64
    ph=m.overlay.sha(protocol)
    p=root/'protocol'/'protocol.json';p.write_text(canonical(protocol)+'\n')
    provenance['protocol_manifest']['files'][p.name]=digest(p)
    provenance['protocol_manifest']['protocol_sha256']=ph;provenance['fit_manifest']['protocol_sha256']=ph
    feature,_=m.reconstruction_dependencies()
    monkeypatch.setattr(feature,'FeatureDesign',lambda *a:pytest.fail('Must reject before reconstruction'))
    with pytest.raises(ValueError,match='dependency|environment|source'):
        m.verify_design(root,source,protocol,provenance)


def complete_synthetic_fit(root,source,rows,version):
    """Real saved source/design/report bundles, deliberately synthetic posterior summaries."""
    from models import bayesian_feature_experiment_v2 as reports
    from models import bayesian_feature_graph_v3 as graph
    feature,code,versions=runtime_identity();data=converted(rows)
    if version==m.noise.V3:
        from models import bayesian_feature_experiment_v3 as runner
        code.update({Path(x.__file__).name:Path(x.__file__).read_bytes() for x in (graph,runner)})
    protocol={'version':version,'source_manifest_sha256':digest(source/'complete.json'),
              'source_observations_sha256':digest(source/'observations.jsonl'),
              'source_version':json.loads((source/'complete.json').read_text())['version'],
              'rows':len(data),'units':data.unit_id.nunique(),'buildings':data.building.nunique(),'current_rows':1,
              'specification':'full_half_balance','prior_multiplier':1.,'chains':4,'draws':1000,'tune':1000,'seed':71,
              'adaptation':'diag','target_accept':.93,'versions':versions,'bathroom_policy':'Source counts',
              'likelihood':'Synthetic accepted summary, no sampling','uncertainty':'Conditional associations',
              'implementation_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in code.items()}}
    config=graph.graph_configuration(data)
    if version==m.noise.V3:
        protocol.update(residual_scale='shared',building_prior_scale=.35,unit_prior_scale=.25,graph_configuration=config)
    ph=m.overlay.sha(protocol);target=root/'fit';target.mkdir(parents=True)
    design=feature.FeatureDesign(data);design.save(target)
    beta=np.full((10,len(design.features)),.01)
    contrasts=reports.reports.bathroom_contrasts(design,data,beta)
    contrasts['half_bath_increments']=reports.half_bath_contrasts(design,data,beta)
    residuals=[{k:r[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent')}|
        {'fitted_rent':r['asking_rent']*.95,'latent_rent_lower_95':r['asking_rent']*.9,'latent_rent_upper_95':r['asking_rent'],
         'residual_dollars':r['asking_rent']*.05,'residual_log':math.log(1/.95)} for r in rows]
    groups=[{'kind':kind,'id':key,'log_effect':interval(.1),'percent_effect':interval(10)}
            for kind,keys in [('building',design.time.buildings),('unit',design.time.unit_ids)] for key in keys]
    diag=diagnostics();summary={'protocol_sha256':ph,'status':'exploratory_converged','diagnostics':diag,
        'derived_diagnostics':diag,'design_support':design.support,'bathroom_balance':contrasts['balance'],
        'median_absolute_log_residual':math.log(1/.95)}
    files={name:(target/name).read_bytes() for name in m.comparison.DESIGNS}
    files.update({'summary.json':canonical(summary)+'\n','diagnostics.json':canonical(diag)+'\n',
        'derived-diagnostics.json':canonical(diag)+'\n','bathroom-contrasts.json':canonical(contrasts)+'\n',
        'coefficients.json':canonical([{'feature':name,**interval(.01)} for name in design.features])+'\n',
        'residuals.jsonl':''.join(canonical(r)+'\n' for r in residuals),
        'group-effects.jsonl':''.join(canonical(r)+'\n' for r in groups),'posterior.nc':b'SYNTHETIC; no posterior samples'})
    if version==m.noise.V3:
        scales={'version':'bayesian-residual-scale-summary-v1','graph_configuration':config,'student_t_nu':5.,
            'scale_units':'Log advertised asking rent; Student-t scale, not its standard deviation.',
            'global_sigma':{**interval(.2),'probability_positive':1.},'global_sigma_role':'Shared observation scale','by_bedroom':[],
            'interpretation':'Separate conditional 95% posterior intervals. Residual variation is not latent conditional-median uncertainty. Student-t standard deviation equals scale * sqrt(5/3); no mean or feature contribution changed by this summary.'}
        files.update({'graph-configuration.json':canonical(config)+'\n','residual-scales.json':canonical(scales)+'\n'})
    publish_binary(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**code},{'version':version,'protocol_sha256':ph})
    publish_binary(target,files,{'version':version,'protocol_sha256':ph})


@pytest.fixture
def comparison_pair(tmp_path,train):
    rows=design_source(train)
    source=tmp_path/'original';audit=tmp_path/'audit';decisions=tmp_path/'decisions';revised=tmp_path/'revised'
    publish_bundle(source,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},{'version':m.overlay.SOURCE_VERSION})
    captures=[];edits=[]
    for index,action in [(1,'mask_bathroom_composition'),(2,'quarantine_nonresidential')]:
        row=rows[index];text='The apartment has 2 FULL BATHS.'
        capture={k:row[k] for k in m.overlay.IDENTITY}|{'capture_id':index,'body_sha256':'a'*64,
            'raw_listing_sha256':'b'*64,'description':text,'description_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_collected_at':'2026-09-17T12:00:00+00:00','known_at':row['known_at']}
        captures.append(capture);edits.append(decision(row,capture,action))
    publish_bundle(audit,{'captures.jsonl':''.join(canonical(c)+'\n' for c in captures)},{'version':'synthetic-audit'})
    publish_bundle(decisions,{'decisions.jsonl':''.join(canonical(d)+'\n' for d in edits)},
        {'version':m.overlay.DECISION_VERSION,'source_manifest_sha256':digest(source/'complete.json'),
         'source_observations_sha256':digest(source/'observations.jsonl'),'audit_manifest_sha256':digest(audit/'complete.json')})
    m.overlay.run(source,decisions,audit,revised)
    after=m.overlay.rows((revised/'observations.jsonl').read_bytes())
    reference=tmp_path/'reference-fit';candidate=tmp_path/'candidate-fit'
    complete_synthetic_fit(reference,source,rows,m.noise.V2)
    complete_synthetic_fit(candidate,revised,after,m.noise.V3)
    return reference,candidate,source,revised,audit


def test_full_comparison_reconstructs_both_source_designs_and_replays(comparison_pair,tmp_path):
    report,_=m.build_comparison(*comparison_pair)
    assert [fit['design_verification']['rows'] for fit in report['fits']]==[300,299]
    assert all(fit['design_verification']['verified'] for fit in report['fits'])
    assert report['residuals']['rows']==299
    assert report['residuals']['excluded_reference_rows'][0]['audit_id']=='a2'
    output=tmp_path/'comparison';first=m.run(*comparison_pair,output)
    assert m.run(*comparison_pair,output)==first


def test_full_comparison_rejects_independent_design_change_after_report_gate(comparison_pair):
    reference,candidate,source,revised,audit=comparison_pair
    design=json.loads((candidate/'fit'/'feature-design.json').read_text())
    design['numeric']['listed_floor']['scale']*=10
    reseal(candidate/'fit','feature-design.json',canonical(design)+'\n')
    # The general report gate accepts this plausible scalar metadata; the new
    # source-reconstruction gate must reject it before publishing a comparison.
    m.verified.build_report(candidate,revised)
    with pytest.raises(ValueError,match='exact source reconstruction'):
        m.build_comparison(reference,candidate,source,revised,audit)
