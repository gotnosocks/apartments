from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from models import bayesian_disk_sampling as m


@pytest.fixture
def trace():
    shape=(2,17)
    p=xr.Dataset({'beta':(('chain','draw','feature'),np.arange(2*17*3,dtype=float).reshape(2,17,3)),
                  'sigma':(('chain','draw'),np.ones(shape)),
                  'sigma_log__':(('chain','draw'),np.zeros(shape))},coords={'feature':['a','b','c']})
    stats={name:(('chain','draw'),np.ones(shape)) for name in m.STATISTICS}
    stats['tuning']=(('chain','draw'),np.zeros(shape,dtype=bool))
    stats['diverging']=(('chain','draw'),np.zeros(shape,dtype=bool))
    stats['depth']=(('chain','draw'),np.full(shape,3,dtype=np.uint64))
    stats['divergence_draw']=(('chain','event'),np.empty((2,0)))
    tree=xr.DataTree.from_dict({'/':xr.Dataset(attrs={'sampler_settings':{'draws':17}}),
        'posterior':p,'sample_stats':xr.Dataset(stats),'warmup_posterior':p.isel(draw=slice(0,4))})
    expected={'chains':2,'draws':17,'variables':{'beta':['feature'],'sigma':[]},'coordinates':{'feature':['a','b','c']}}
    return tree,expected


def test_bounded_export_preserves_all_draws_coordinates_and_boolean_stats(trace,tmp_path):
    raw,expected=trace;path=tmp_path/'posterior.nc'
    result=m.export_trace(raw,expected,path,max_bytes=48)
    assert result['maximum_array_block_bytes']<=48
    assert result['warmup_exported'] is False
    with xr.open_datatree(path,engine='h5netcdf') as actual:
        assert set(actual.children)=={'posterior','sample_stats'}
        assert set(actual.posterior.data_vars)=={'beta','sigma'}
        assert actual.posterior.feature.values.tolist()==['a','b','c']
        assert actual.posterior.chain.values.tolist()==[0,1]
        assert actual.posterior.draw.values.tolist()==list(range(17))
        for name in expected['variables']:
            np.testing.assert_array_equal(actual.posterior[name].values,raw.posterior[name].values)
        assert actual.sample_stats.diverging.dtype==bool
        assert actual.sample_stats['depth'].dtype==np.uint64
        assert set(actual.sample_stats.data_vars)==set(m.STATISTICS)
        assert actual.attrs['raw_trace_attrs_json']=='{"sampler_settings":{"draws":17}}'


@pytest.mark.parametrize('damage',['coordinate','count','missing','dimensions','warmup','nonfinite'])
def test_corrupt_trace_cannot_publish(trace,tmp_path,damage):
    raw,expected=trace
    if damage=='coordinate': expected['coordinates']['feature']=['b','a','c']
    if damage=='count': expected['draws']=18
    if damage=='missing': del raw['posterior']['sigma']
    if damage=='dimensions': expected['variables']['beta']=[]
    if damage=='warmup': raw.sample_stats.tuning.values[0,0]=True
    if damage=='nonfinite': raw.posterior.beta.values[0,0,0]=np.nan
    path=tmp_path/'posterior.nc'
    with pytest.raises(ValueError):m.export_trace(raw,expected,path,max_bytes=48)
    assert not path.exists()


def test_trace_inventory_checks_chunks_and_rejects_symlinks(tmp_path):
    root=tmp_path/'raw';root.mkdir();(root/'zarr.json').write_text('{}')
    (root/'nested').mkdir();(root/'nested/chunk').write_bytes(b'123')
    first=m.trace_files(root)
    assert set(first)=={'zarr.json','nested/chunk'}
    (root/'nested/chunk').write_bytes(b'321')
    assert m.trace_files(root)!=first
    (root/'link').symlink_to(root/'zarr.json')
    with pytest.raises(ValueError,match='symlink'):m.trace_files(root)


def test_interrupted_sampling_refuses_automatic_restart(tmp_path,monkeypatch):
    model=SimpleNamespace(free_RVs=[SimpleNamespace(name='a')],deterministics=[],named_vars_to_dims={},coords={})
    root=tmp_path/'trace';root.mkdir();(root/'intent.json').write_text('{}')
    import nutpie
    monkeypatch.setattr(nutpie,'sample',lambda *a,**k:pytest.fail('Must not resample'))
    with pytest.raises(ValueError,match='cannot resume'):
        m.sample_to_netcdf(model,output=tmp_path/'p.nc',trace_root=root,protocol_hash='a',draws=4,tune=4,
            chains=2,seed=3,adaptation='diag',target_accept=.93,status_path=tmp_path/'status.json')


def test_block_budget_bounds_high_dimensional_arrays():
    assert np.prod(m.block_shape((4,6000,22158),8))*8 <= m.MAX_BLOCK_BYTES


def test_chain_coordinates_are_not_silently_relabelled(trace,tmp_path):
    raw,expected=trace
    raw['posterior']=xr.DataTree(raw.posterior.to_dataset().assign_coords(chain=[1,0]))
    with pytest.raises(ValueError,match='coordinate order'):
        m.export_trace(raw,expected,tmp_path/'posterior.nc')


@pytest.mark.parametrize('damage',['protocol','raw_chunk'])
def test_completed_trace_recovery_rejects_identity_or_chunk_changes(tmp_path,damage):
    model=SimpleNamespace(free_RVs=[SimpleNamespace(name='a')],deterministics=[],named_vars_to_dims={},coords={})
    root=tmp_path/'trace';raw=root/'raw.zarr';raw.mkdir(parents=True);(raw/'zarr.json').write_text('{}')
    settings=dict(draws=4,tune=4,chains=2,seed=3,adaptation='diag',target_accept=.93)
    identity={'version':m.VERSION,'protocol_sha256':'original','contract':m.contract(model,chains=2,draws=4),**settings}
    m.atomic_json(root/'complete.json',{'identity':identity,'files':m.trace_files(raw)})
    if damage=='raw_chunk':(raw/'zarr.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='completion or identity differs'):
        m.sample_to_netcdf(model,output=tmp_path/'p.nc',trace_root=root,
            protocol_hash='changed' if damage=='protocol' else 'original',status_path=tmp_path/'status.json',**settings)
