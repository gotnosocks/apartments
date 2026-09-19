"""Durable nutpie Zarr traces and bounded-memory NetCDF export for PyMC models."""
from __future__ import annotations

import itertools
import json
import math
import os
from pathlib import Path

import h5netcdf
import numpy as np
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import digest
from .bayesian_sampling import SamplingProgress, write_status

VERSION = 'bayesian-disk-sampling-v1'
# Event-indexed diagnostics remain in the raw archive. Analysis requires these
# actual per-draw statistics, whose Arrow/Zarr values were checked for parity.
STATISTICS = ('depth','maxdepth_reached','step_size','step_size_bar','mean_tree_accept',
    'mean_tree_accept_sym','n_steps','max_energy_error','tuning','index_in_trajectory',
    'logp','energy','energy_error','fisher_distance','transformation_index','diverging')
MAX_BLOCK_BYTES = 8 * 1024 * 1024


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('w') as stream:
        stream.write(canonical(value)+'\n'); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def trace_files(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('Trace must be a real directory')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Trace contains a symlink')
        if path.is_file(): result[path.relative_to(root).as_posix()] = digest(path)
    if not result or 'zarr.json' not in result: raise ValueError('Incomplete trace archive')
    return result


def contract(model, *, chains, draws):
    names = [v.name for v in [*model.free_RVs, *model.deterministics]]
    if len(names) != len(set(names)): raise ValueError('Duplicate model variable names')
    dimensions = {name:list(model.named_vars_to_dims.get(name, ())) for name in names}
    if any(dim is None for dims in dimensions.values() for dim in dims):
        raise ValueError('Explicit posterior dimension names required')
    coordinates = {dim:list(model.coords[dim]) for dims in dimensions.values() for dim in dims}
    # Normalize numpy scalar coordinates for canonical JSON and exact comparisons.
    coordinates = {k:np.asarray(v).tolist() for k,v in coordinates.items()}
    return {'chains':chains,'draws':draws,'variables':dimensions,'coordinates':coordinates}


def retained_groups(trace, expected):
    chains, draws = expected['chains'], expected['draws']
    groups = {}
    for group, names in [('posterior',expected['variables']),('sample_stats',STATISTICS)]:
        source = trace[group].to_dataset()
        if source.sizes.get('chain') != chains or source.sizes.get('draw') != draws:
            raise ValueError('Trace chain/draw counts differ from contract')
        if not set(names) <= set(source.data_vars): raise ValueError('Missing required trace variables')
        for name in names:
            dims = ('chain','draw',*expected['variables'][name]) if group == 'posterior' else ('chain','draw')
            if source[name].dims != dims: raise ValueError('Trace dimensions differ: '+name)
        for dim, count in [('chain',chains),('draw',draws)]:
            if dim in source.coords and source[dim].values.tolist() != list(range(count)):
                raise ValueError('Unexpected chain/draw coordinate order')
        selected = source[list(names)].assign_coords(chain=np.arange(chains),draw=np.arange(draws))
        if group == 'posterior':
            for dim, values in expected['coordinates'].items():
                if dim not in selected.coords or selected[dim].values.tolist() != values:
                    raise ValueError('Trace coordinate order differs: '+dim)
        # All metadata survives as JSON text; no dictionary-valued HDF5 attrs.
        selected.attrs = {'disk_sampling_version':VERSION,'raw_group_attrs_json':canonical(source.attrs)}
        groups[group] = selected
    if np.any(groups['sample_stats']['tuning'].values):
        raise ValueError('Retained trace contains warmup draws')
    return groups


def block_shape(shape, itemsize, max_bytes=MAX_BLOCK_BYTES):
    if not shape or any(n <= 0 for n in shape): raise ValueError('Positive array shape required')
    chunks = list(shape)
    chunks[0] = 1
    if len(chunks)>1: chunks[1] = min(32,chunks[1])
    while math.prod(chunks)*itemsize > max_bytes:
        index = max(range(len(chunks)),key=chunks.__getitem__)
        if chunks[index] == 1: raise ValueError('Block budget smaller than one element')
        chunks[index] = max(1,chunks[index]//2)
    return tuple(chunks)


def export_trace(trace, expected, output, *, max_bytes=MAX_BLOCK_BYTES):
    """Read/write bounded slabs; never materialize a complete unit trace array."""
    output = Path(output)
    temporary = output.with_name(output.name+'.partial')
    groups = retained_groups(trace,expected)
    xr.Dataset(attrs={'disk_sampling_version':VERSION,
        'raw_trace_attrs_json':canonical(trace.attrs)}).to_netcdf(temporary,engine='h5netcdf')
    maximum = 0
    for group, dataset in groups.items():
        coords = {name:(coord.dims,np.asarray(coord.values,dtype=object)
                       if coord.dtype.kind in 'OUT' else coord.values)
                  for name,coord in dataset.coords.items()}
        xr.Dataset(coords=coords,attrs=dataset.attrs).to_netcdf(temporary,group=group,mode='a',engine='h5netcdf')
        with h5netcdf.File(temporary,'a') as target:
            node = target.groups[group]
            for name, variable in dataset.data_vars.items():
                if variable.dtype.kind not in 'biuf': raise ValueError('Non-numeric trace variable: '+name)
                chunks = block_shape(variable.shape,variable.dtype.itemsize,max_bytes)
                boolean = variable.dtype.kind == 'b'
                stored = node.create_variable(name,variable.dims,dtype='i1' if boolean else variable.dtype,
                    chunks=tuple(min(size,512) if dim not in ('chain','draw') else size for dim,size in zip(variable.dims,chunks)),compression='gzip',compression_opts=1)
                if boolean: stored.attrs['dtype'] = 'bool'
                stored.attrs['raw_variable_attrs_json'] = canonical(variable.attrs)
                for starts in itertools.product(*(range(0,n,c) for n,c in zip(variable.shape,chunks))):
                    slices = tuple(slice(start,min(start+chunk,n)) for start,chunk,n in zip(starts,chunks,variable.shape))
                    block = variable.isel(dict(zip(variable.dims,slices))).values
                    maximum = max(maximum,block.nbytes)
                    if (group == 'posterior' or name in ('energy','logp','step_size')) and not np.isfinite(block).all():
                        raise ValueError('Nonfinite required trace values: '+name)
                    stored[slices] = block.astype('i1') if boolean else block
    with temporary.open('rb') as stream: os.fsync(stream.fileno())
    temporary.replace(output)
    return {'version':VERSION,'maximum_array_block_bytes':maximum,'block_budget_bytes':max_bytes,
        'chains':expected['chains'],'draws':expected['draws'],'warmup_exported':False,
        'posterior_variables':list(expected['variables']),'sample_statistics':list(STATISTICS),
        'raw_event_statistics_preserved':True,'posterior_sha256':digest(output)}


def sample_to_netcdf(model, *, output, trace_root, protocol_hash, draws, tune, chains,
                     seed, adaptation, target_accept, status_path):
    import nutpie
    output, trace_root = Path(output), Path(trace_root)
    expected = contract(model,chains=chains,draws=draws)
    identity = {'version':VERSION,'protocol_sha256':protocol_hash,'contract':expected,
        'draws':draws,'tune':tune,'chains':chains,'seed':seed,'adaptation':adaptation,'target_accept':target_accept}
    complete = trace_root/'complete.json'; raw = trace_root/'raw.zarr'
    trace_root.mkdir(parents=True,exist_ok=True)
    if complete.exists():
        saved = json.loads(complete.read_text())
        if saved.get('identity') != identity or saved.get('files') != trace_files(raw):
            raise ValueError('Disk trace completion or identity differs')
        trace = xr.open_datatree(raw,engine='zarr',consolidated=False)
    else:
        if any(trace_root.iterdir()):
            raise ValueError('Incomplete disk sampling cannot resume; preserve it and choose a new run')
        atomic_json(trace_root/'intent.json',identity)
        raw.mkdir()
        write_status(status_path,'compiling_disk_sampler')
        compiled = nutpie.compile_pymc_model(model,backend='numba')
        trace = nutpie.sample(compiled,draws=draws,tune=tune,chains=chains,cores=min(chains,4),
            seed=seed,adaptation=adaptation,target_accept=target_accept,save_warmup=False,
            store_unconstrained=False,progress_bar=False,progress_callback=SamplingProgress(status_path),
            progress_rate=5000,zarr_store=nutpie.zarr_store.LocalStore(str(raw)))
        retained_groups(trace,expected)
        atomic_json(complete,{'identity':identity,'files':trace_files(raw)})
    try:
        write_status(status_path,'exporting_disk_trace')
        result = export_trace(trace,expected,output)
        result['trace_manifest_sha256'] = digest(complete)
        atomic_json(output.with_name('storage.json'),result)
    finally:
        trace.close()
    write_status(status_path,'sampled_disk_trace')
    return xr.open_datatree(output,engine='h5netcdf',cache=False)
