"""Conditional spatial diagnostics of a saved joint building-effect posterior.

This is not a spatial price fit or a test of causal location premiums. Coordinates
are an evidence overlay; the posterior still belongs to its original source.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import cdist

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from . import cohort_spatial_features as locations
from .bayesian_feature_sensitivity import bound_bytes

VERSION = 'joint-building-spatial-diagnostics-v1'
NEIGHBORS = (5, 10)


def neighbor_graph(labels, coordinates, k):
    """Symmetric binary union of spherical kNN edges; ties use building IDs."""
    coordinates = np.asarray(coordinates, dtype=float)
    n = len(labels)
    if (n < 3 or len(set(labels)) != n or coordinates.shape != (n, 2)
            or not np.isfinite(coordinates).all() or (abs(coordinates[:, 0]) > 90).any()
            or (abs(coordinates[:, 1]) > 180).any() or type(k) is not int or not 0 < k < n):
        raise ValueError('Unique buildings, finite geographic coordinates and valid k required')
    lat, lon = np.deg2rad(coordinates).T
    xyz = np.column_stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    distances = cdist(xyz, xyz, 'sqeuclidean')
    coincident = int(np.count_nonzero(np.triu(distances == 0, 1)))
    np.fill_diagonal(distances, np.inf)
    targets = np.concatenate([np.lexsort((np.asarray(labels), row))[:k] for row in distances])
    weights = csr_matrix((np.ones(n*k), (np.repeat(np.arange(n), k), targets)), shape=(n, n))
    weights = weights.maximum(weights.T)
    degree = np.asarray(weights.sum(axis=1)).ravel()
    return weights, {'k': k, 'buildings': n, 'undirected_edges': weights.nnz//2,
        'minimum_degree': int(degree.min()), 'maximum_degree': int(degree.max()),
        'connected_components': int(connected_components(weights, directed=False, return_labels=False)),
        'coincident_coordinate_pairs': coincident,
        'weights': 'Symmetric binary union; no self edges or row normalization.',
        'distance': 'Squared unit-sphere chord distance; same neighbor order as angular distance.',
        'tie_break': 'Lexicographic building ID for exact distance ties.'}


def moran_draws(values, weights, block_size=256):
    """Compute n/S0 * z'Wz/z'z, centering separately within each joint draw."""
    values = np.asarray(values, dtype=float)
    weights = csr_matrix(weights, dtype=float)
    n = weights.shape[0]
    if (values.ndim < 2 or n < 3 or weights.shape != (n, n) or values.shape[-1] != n
            or not np.isfinite(values).all() or not np.isfinite(weights.data).all()
            or (weights.data < 0).any() or np.any(weights.diagonal()) or weights.sum() <= 0
            or type(block_size) is not int or block_size < 1):
        raise ValueError('Finite joint draws and nonnegative zero-diagonal spatial weights required')
    flat = values.reshape(-1, n)
    result = np.empty(len(flat))
    scale = n/float(weights.sum())
    for start in range(0, len(flat), block_size):
        z = flat[start:start+block_size]
        z = z-z.mean(axis=1, keepdims=True)
        denominator = np.einsum('ij,ij->i', z, z)
        if (denominator <= 0).any(): raise ValueError('Moran I is undefined for constant building draws')
        result[start:start+len(z)] = scale*np.einsum('ij,ij->i', z, weights.dot(z.T).T)/denominator
    if not np.isfinite(result).all(): raise ValueError('Nonfinite Moran I')
    return result.reshape(values.shape[:-1])


def interval(values):
    values = np.asarray(values)
    lower, median, upper = np.quantile(values, [.025, .5, .975])
    return {'median': float(median), 'lower_95': float(lower), 'upper_95': float(upper),
            'probability_positive': float(np.mean(values > 0))}


def distinct_locations(buildings):
    """Sensitivity subset: remove every member of an exactly coincident group."""
    from collections import Counter
    counts = Counter((b['latitude'], b['longitude']) for b in buildings)
    return [b for b in buildings if counts[(b['latitude'], b['longitude'])] == 1]


def check_lineage(selected_manifest, candidate_manifest, spatial_manifest, rows, buildings):
    if (candidate_manifest.get('source_manifest') != selected_manifest
            or candidate_manifest.get('source_manifest_sha256') != hashlib.sha256(
                (canonical(selected_manifest)+'\n').encode()).hexdigest()):
        raise ValueError('Location cohort is not a direct revision of the selected source')
    if spatial_manifest.get('version') != locations.VERSION:
        raise ValueError('Unsupported location evidence')
    labels = [r['building'] for r in buildings]
    if (len(set(labels)) != len(labels) or set(labels) != {r['building'] for r in rows}
            or any(r['status'] != 'source_bound' for r in buildings)):
        raise ValueError('Location evidence does not cover the exact candidate building cohort')


def posterior_statistics(path, protocol, source_labels, labels, graphs):
    import xarray as xr
    from . import bayesian_rent_model as base
    with xr.open_dataset(path, group='posterior', engine='h5netcdf', cache=False) as p, \
         xr.open_dataset(path, group='sample_stats', engine='h5netcdf', cache=False) as s:
        actual = p.building.values.tolist()
        if (p.building_effect.dims != ('chain', 'draw', 'building')
                or len(set(actual)) != len(actual) or set(actual) != set(source_labels)
                or len(set(labels)) != len(labels) or not set(labels) <= set(actual)
                or any(p.sizes[d] != protocol[k] for d, k in [('chain', 'chains'), ('draw', 'draws')])
                or any(not p[d].equals(s[d]) for d in ('chain', 'draw'))):
            raise ValueError('Posterior dimensions, labels or sample-stat coordinates differ')
        # Select the building variable only, never the multi-GB unit posterior.
        values = p.building_effect.sel(building=labels).values
        statistics = np.stack([moran_draws(values, w) for w in graphs], axis=-1)
        ds = xr.Dataset({'moran_i': (('chain', 'draw', 'graph'), statistics)},
                        coords={'chain': p.chain, 'draw': p.draw, 'graph': list(NEIGHBORS)})
        diag, table = base.diagnostics(xr.DataTree.from_dict({'posterior': ds, 'sample_stats': s.load()}))
        if not diag['acceptable'] or diag['maxdepth_reached'] != 0:
            raise ValueError('Joint spatial statistics fail convergence diagnostics')
        # Preserve draw-wise centering for maps as well as the Moran statistic.
        values -= values.mean(axis=-1, keepdims=True)
        building_summaries = [{'building': name, 'centered_log_effect': interval(values[:, :, i])}
                              for i, name in enumerate(labels)]
    return statistics, diag, table, building_summaries


def run(selection, spatial, dataset, output, exclude_coincident=False):
    from .bayesian_feature_report import check_diagnostics
    selection, spatial, dataset = map(Path, (selection, spatial, dataset))
    selection_hash = digest(selection)
    chosen = json.loads(selection.read_text())
    root, source = Path(chosen['experiment']), Path(chosen['dataset'])
    bindings = [(root/'fit', chosen['fit_manifest_sha256']),
                (root/'protocol', chosen['protocol_manifest_sha256']),
                (source, chosen['source_manifest_sha256']),
                (spatial, digest(spatial/'complete.json')), (dataset, digest(dataset/'complete.json'))]
    manifests = []
    for path, expected in bindings:
        if digest(path/'complete.json') != expected: raise ValueError('Selected artifact changed')
        manifests.append(locations.verified_manifest(path))
    fm, pm, sm, lm, dm = manifests
    if lm['dataset_manifest_sha256'] != bindings[-1][1]: raise ValueError('Spatial source binding differs')
    protocol = json.loads(bound_bytes(root/'protocol', 'protocol.json', pm))
    if (hashlib.sha256(canonical(protocol).encode()).hexdigest() != chosen['protocol_sha256']
            or fm['protocol_sha256'] != chosen['protocol_sha256']
            or pm['protocol_sha256'] != chosen['protocol_sha256']
            or protocol['source_manifest_sha256'] != chosen['source_manifest_sha256']
            or protocol['source_observations_sha256'] != sm['files']['observations.jsonl']
            or sm['files']['observations.jsonl'] != chosen['source_observations_sha256']):
        raise ValueError('Selected posterior/protocol/source binding differs')
    saved = {n: json.loads(bound_bytes(root/'fit', n+'.json', fm)) for n in
             ('summary', 'diagnostics', 'derived-diagnostics', 'floor-contrasts')}
    check_diagnostics(saved['summary'], saved['diagnostics'], saved['derived-diagnostics'])
    fd = saved['floor-contrasts']['diagnostics']
    check_diagnostics({'status': saved['summary']['status'], 'diagnostics': fd, 'derived_diagnostics': fd}, fd, fd)
    if saved['summary']['floor_diagnostics'] != fd: raise ValueError('Floor diagnostic binding differs')
    # Only cohort membership is needed here; avoid retaining raw evidence blobs.
    rows = [{'building': r['building']} for r in locations.records(dataset/'observations.jsonl')]
    buildings = sorted(locations.records(spatial/'buildings.jsonl'), key=lambda b: b['building'])
    check_lineage(sm, dm, lm, rows, buildings)
    all_location_labels = {r['building'] for r in buildings}
    if exclude_coincident: buildings = distinct_locations(buildings)
    labels = [r['building'] for r in buildings]
    source_labels = sorted({r['building'] for r in locations.records(source/'observations.jsonl')})
    coordinates = [[r['latitude'], r['longitude']] for r in buildings]
    graphs, metadata = zip(*(neighbor_graph(labels, coordinates, k) for k in NEIGHBORS))
    statistics, diag, table, effects = posterior_statistics(root/'fit/posterior.nc', protocol, source_labels, labels, graphs)
    expectation = -1/(len(labels)-1)
    results = [{**m, 'moran_i': interval(statistics[:, :, i]),
        'probability_above_randomization_expectation': float(np.mean(statistics[:, :, i] > expectation))}
        for i, m in enumerate(metadata)]
    result = {'version': VERSION, 'graphs': results, 'diagnostics': diag,
        'chains': protocol['chains'], 'draws_per_chain': protocol['draws'], 'all_retained_draws': True,
        'posterior_source_rows': protocol['rows'], 'location_cohort_rows': len(rows),
        'omitted_posterior_buildings': sorted(set(source_labels)-set(labels)),
        'exclude_coincident_locations': exclude_coincident,
        'coincident_buildings_excluded': sorted(all_location_labels-set(labels)),
        'randomization_expectation': expectation,
        'main_model_changed': False, 'posterior_refitted': False,
        'limitations': ['Conditional posterior descriptive statistic, not a null-test p-value or a causal location premium.',
            'The posterior retains the original source, including rows quarantined in the location cohort. Repeat after source refitting.',
            'Spatial clustering may reflect omitted building characteristics, source errors, uneven support or shrinkage.',
            'Neighbor definitions are fixed before observing results; binary union weights are not row standardized.',
            'Moran I is not Pearson correlation and is not generally restricted to [-1, 1].',
            'This result alone does not select a spatial model or establish better feature attribution.']}
    files = {'summary.json': canonical(result)+'\n', 'diagnostics.csv': table.to_csv(),
        'joint-statistics.json': canonical({'dimensions': ['chain', 'draw', 'graph'],
            'graph': list(NEIGHBORS), 'values': statistics.tolist()})+'\n',
        'buildings.jsonl': ''.join(canonical({**b, **e})+'\n' for b, e in zip(buildings, effects)),
        'edges.jsonl': ''.join(canonical({'k': k, 'a': labels[i], 'b': labels[j]})+'\n'
            for k, w in zip(NEIGHBORS, graphs) for i, j in zip(*w.nonzero()) if i < j)}
    from . import bayesian_rent_model as base, bayesian_feature_report as report, bayesian_feature_sensitivity as common
    from apartments import research_pipeline, corrections
    implementations = [Path(__file__), Path(locations.__file__), Path(base.__file__), Path(report.__file__),
                       Path(research_pipeline.__file__), Path(corrections.__file__), Path(common.__file__)]
    for path in implementations: files[path.name] = path.read_text()
    # Recheck consumed artifacts before publishing. Hash streams avoid loading
    # the full posterior; frozen model files used by a live fit are never edited.
    for (path, expected), manifest in zip(bindings, manifests):
        if digest(path/'complete.json') != expected or locations.verified_manifest(path) != manifest:
            raise ValueError('Input changed during spatial diagnostics')
    if digest(selection) != selection_hash: raise ValueError('Selection changed during spatial diagnostics')
    publish_bundle(output, files, {'version': VERSION, 'selection_sha256': selection_hash,
        'fit_manifest_sha256': chosen['fit_manifest_sha256'], 'posterior_sha256': fm['files']['posterior.nc'],
        'source_manifest_sha256': chosen['source_manifest_sha256'], 'spatial_manifest_sha256': bindings[-2][1],
        'location_cohort_manifest_sha256': bindings[-1][1]})
    print(canonical(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, default=Path('config/main-analysis.json'))
    parser.add_argument('--exclude-coincident', action='store_true',
                        help='Sensitivity only: omit every building sharing identical coordinates, then rebuild graphs.')
    for name in ('spatial', 'dataset', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
