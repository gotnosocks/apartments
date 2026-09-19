import json
from pathlib import Path
import xarray as xr
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest
from models import bayesian_disk_experiment as m
from tests.test_bayesian_feature_experiment_v3 import setup, posterior


def configure(setup,monkeypatch,floor=False):
    args,design,events=setup
    args.floor_increments=floor;args.floor_increment_prior_scale=.15
    monkeypatch.setattr(m.increments.floor,'FeatureDesign',lambda *a,**k:design)
    monkeypatch.setattr(m.increments,'floor_contrasts',lambda *a:{'version':m.increments.FLOOR_CONTRAST_VERSION,
        'diagnostics':{'acceptable':True},'contrasts':[]})
    def sample(model,**kwargs):
        events['sample']+=1
        p=posterior(args,design,model.graph_configuration)['posterior']
        tree=xr.DataTree.from_dict({'posterior':p})
        tree.to_netcdf(kwargs['output'],engine='h5netcdf')
        raw=kwargs['trace_root'];raw.mkdir(exist_ok=True)
        identity={'version':m.storage.VERSION,'protocol_sha256':kwargs['protocol_hash'],
            **{k:kwargs[k] for k in ('chains','draws','tune','seed','adaptation','target_accept')},
            'contract':{'chains':args.chains,'draws':args.draws,'variables':{name:list(v.dims[2:]) for name,v in p.data_vars.items()}}}
        marker={'identity':identity,'files':{'zarr.json':'a'*64}}
        m.storage.atomic_json(raw/'complete.json',marker)
        result={'version':m.storage.VERSION,'chains':args.chains,'draws':args.draws,
            'posterior_sha256':digest(kwargs['output']),'trace_manifest_sha256':digest(raw/'complete.json'),
            'warmup_exported':False,'raw_event_statistics_preserved':True,
            'block_budget_bytes':m.storage.MAX_BLOCK_BYTES,'maximum_array_block_bytes':64,
            'posterior_variables':list(p.data_vars)}
        m.storage.atomic_json(kwargs['output'].with_name('storage.json'),result)
        return tree
    monkeypatch.setattr(m.storage,'sample_to_netcdf',sample)
    return args,design,events


@pytest.mark.parametrize('floor',[False,True])
def test_disk_runner_preserves_specification_and_replays_completed_fit(setup,monkeypatch,floor):
    args,_,events=configure(setup,monkeypatch,floor)
    result=m.run(args)
    protocol=json.loads((args.output/'protocol/protocol.json').read_text())
    assert protocol['version']==(m.increments.VERSION if floor else m.linear.VERSION)
    assert protocol['execution_version']==m.VERSION
    assert m.disk_protocol.CODE<=protocol['implementation_sha256'].keys()
    assert protocol['graph_configuration']==events['configuration']
    assert m.run(args)==result
    assert events['sample']==events['reports']==1
    assert {'storage.json','trace-manifest.json','reporting-cache.json','bayesian_report_cache.py'}<=json.loads((args.output/'fit/complete.json').read_text())['files'].keys()
    cache = json.loads((args.output/'fit/reporting-cache.json').read_text())
    assert cache['all_retained_draws'] is True and cache['draws'] == args.draws
    assert cache['implementation_sha256'] == digest(args.output/'fit/bayesian_report_cache.py')


def test_reports_resume_from_exported_checkpoint_without_sampling(setup,monkeypatch):
    args,_,events=configure(setup,monkeypatch)
    original=m.linear.v2.write_reports
    monkeypatch.setattr(m.linear.v2,'write_reports',lambda *a:(_ for _ in ()).throw(RuntimeError('Interrupted report')))
    with pytest.raises(RuntimeError):m.run(args)
    assert (args.output/'fit/posterior-checkpoint.json').exists()
    monkeypatch.setattr(m.linear.v2,'write_reports',original)
    m.run(args)
    assert events['sample']==1


@pytest.mark.parametrize('field,value',[('execution_version','invented'),('storage_policy',{}),('storage_versions',{})])
def test_disk_protocol_rejects_unrecognized_execution(setup,monkeypatch,field,value):
    args,_,_=configure(setup,monkeypatch);m.run(args)
    protocol=json.loads((args.output/'protocol/protocol.json').read_text())
    protocol[field]=value
    with pytest.raises(ValueError,match='disk execution'):m.disk_protocol.verify_protocol(protocol)


@pytest.mark.parametrize('damage',['warmup','posterior_hash','block_size','trace_binding','retained_draws'])
def test_storage_product_gate_rejects_inconsistent_evidence(setup,monkeypatch,damage):
    args,_,_=configure(setup,monkeypatch);m.run(args)
    protocol=json.loads((args.output/'protocol/protocol.json').read_text())
    storage=json.loads((args.output/'fit/storage.json').read_text())
    manifest=json.loads((args.output/'fit/trace-manifest.json').read_text())
    if damage=='warmup':storage['warmup_exported']=True
    if damage=='posterior_hash':storage['posterior_sha256']='0'*64
    if damage=='block_size':storage['maximum_array_block_bytes']=m.storage.MAX_BLOCK_BYTES+1
    if damage=='trace_binding':storage['trace_manifest_sha256']='0'*64
    if damage=='retained_draws':manifest['identity']['draws']-=1
    with pytest.raises(ValueError,match='storage products differ'):
        m.disk_protocol.verify_products(protocol,storage,manifest,digest(args.output/'fit/posterior.nc'))
