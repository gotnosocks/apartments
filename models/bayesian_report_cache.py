"""Bound unit-draw reporting memory without changing retained samples or formulas."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path

import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import digest

VERSION = 'bayesian-unit-report-cache-v1'


class UnitSamples:
    """Narrow lazy interface used by fitted_summary and the unit-effect table.

    Indexing materializes only the requested units. Multiplication by one scale
    per retained draw stays lazy until units are indexed. Other operations fail
    explicitly rather than coercing the full matrix into memory.
    """
    __array_priority__ = 10000

    def __init__(self, values, scale=None):
        self.values = values
        self.scale = scale
        self.shape = values.shape

    def __getitem__(self, key):
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError('Unit samples require explicit sample and unit indexing')
        result = self.values[key]
        if self.scale is not None:
            scale = self.scale[key[0]]
            if result.ndim == 2: scale = scale[:, None]
            result = result * scale
        return result

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        if ufunc is not np.multiply or method != '__call__' or kwargs or len(inputs) != 2:
            raise TypeError('Only draw-wise unit scaling is supported')
        other = inputs[1] if inputs[0] is self else inputs[0]
        scale = np.asarray(other)
        if scale.shape != (self.shape[0], 1):
            raise ValueError('Unit scaling must have one value per retained draw')
        scale = scale[:, 0]
        return UnitSamples(self.values, scale if self.scale is None else self.scale * scale)


def build_cache(posterior, directory, posterior_sha256):
    """Copy bounded source slabs into sample-major coordinates with unit-local storage."""
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    path = directory/'unit-samples.npy'; marker = directory/'complete.json'
    variable = posterior['unit_z'].transpose('chain', 'draw', 'unit')
    chains, draws, units = variable.shape
    if units*variable.dtype.itemsize > 8*1024*1024:
        raise ValueError('One unit slab exceeds the report cache block budget')
    identity = {'version': VERSION, 'posterior_sha256': posterior_sha256,
        'chains': chains, 'draws': draws, 'units': units, 'sample_order': 'chain_major_then_draw',
        'unit_ids': variable.coords['unit'].values.tolist(), 'dtype': str(variable.dtype),
        'storage_order': 'Fortran; each unit contiguous across all retained samples'}
    if marker.exists():
        saved = json.loads(marker.read_text())
        if saved['identity'] != identity or digest(path) != saved['cache_sha256']:
            raise ValueError('Report cache identity or contents changed')
        return np.load(path, mmap_mode='r', allow_pickle=False), saved
    if path.exists():
        raise ValueError('Incomplete report cache; use a new cache directory')
    mapped = np.lib.format.open_memmap(path, mode='w+', dtype=variable.dtype,
        shape=(chains*draws, units), fortran_order=True)
    maximum = 0
    try:
        step = max(1, min(32, 8*1024*1024//(units*variable.dtype.itemsize)))
        for chain in range(chains):
            for start in range(0, draws, step):
                stop = min(draws, start+step)
                block = variable.isel(chain=chain, draw=slice(start, stop)).values
                if not np.isfinite(block).all(): raise ValueError('Nonfinite unit draws')
                maximum = max(maximum, block.nbytes)
                target = slice(chain*draws+start, chain*draws+stop)
                mapped[target, :] = block
                if not np.array_equal(mapped[target, :], block):
                    raise ValueError('Unit cache copy differs from posterior')
        mapped.flush()
    finally:
        mapped._mmap.close()
    saved = {'identity': identity, 'cache_sha256': digest(path), 'maximum_source_block_bytes': maximum}
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(canonical(saved)+'\n'); temporary.replace(marker)
    return np.load(path, mmap_mode='r', allow_pickle=False), saved


@contextmanager
def bounded_unit_samples(base, inference, directory, posterior_sha256):
    """Substitute only sample access; all scientific reporting formulas are unchanged.

    The enclosing experiment/recovery owns its exclusive process lock. This
    temporary module substitution must not be used by concurrent report threads.
    """
    original = base.sample_values
    values, manifest = build_cache(base.posterior_dataset(inference), directory, posterior_sha256)
    accessor = UnitSamples(values)
    def load(posterior, name):
        return accessor if name == 'unit_z' else original(posterior, name)
    base.sample_values = load
    try:
        yield manifest
    finally:
        base.sample_values = original
        values._mmap.close()
