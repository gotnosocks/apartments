"""Matched spline fits before/after a reversible own-label floor data revision."""
import argparse
import ast
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from apartments import expanded_floor_projection as projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from apartments.reviewed_cohort_quarantine import sha
from . import floor_spline_fit_comparison as smooth
from . import quarantine_fit_comparison as shared
from . import bayesian_floor_spline_design as spline
from . import bayesian_floor_spline_experiment as experiment
from . import bayesian_floor_execution as execution

VERSION = 'matched-expanded-floor-spline-fit-comparison-v1'
SOURCE_FIELDS = shared.source.SOURCE_FIELDS - {'rows', 'units', 'buildings', 'current_rows'}
VARIABLE = SOURCE_FIELDS | {'implementation_sha256', 'floor_levels', 'floor_knots'}
LOADER_CODE = {'reviewed_source_lineage.py', 'bayesian_feature_experiment_v3.py'}
ADDED_CODE = {'expanded_floor_projection.py'}


def check_protocols(a, b):
    if (a.get('version') != experiment.VERSION or b.get('version') != experiment.VERSION
            or a.get('source_version') != projection.PARENT or b.get('source_version') != projection.VERSION
            or a.get('feature_design_version') != spline.VERSION or b.get('feature_design_version') != spline.VERSION
            or a.get('residual_scale') != 'shared' or not execution.verify_protocol(a)
            or not execution.verify_protocol(b)):
        raise ValueError('Expected durable matched spline fits and the expanded source revision')
    if {k: v for k, v in a.items() if k not in VARIABLE} != {k: v for k, v in b.items() if k not in VARIABLE}:
        raise ValueError('Spline specification, prior, sampler, population or environment changed')
    for protocol in (a, b):
        levels = protocol.get('floor_levels', [])
        if (len(levels) < 2 or levels != sorted(set(levels))
                or not np.isfinite(levels).all() or 2. not in levels):
            raise ValueError('Invalid observed floor support')
        knots, anchor = spline.knot_specification(levels)
        if (protocol.get('floor_knots') != knots or protocol.get('floor_reference') != anchor
                or protocol.get('floor_policy') != spline.policy()):
            raise ValueError('Invalid spline specification')
        expected = {'chains': 4, 'tune': 4000, 'draws': 6000, 'target_accept': .93,
                    'adaptation': 'diag', 'seed': 20260924, 'maxdepth': 10}
        if any(protocol.get(k) != value for k, value in expected.items()):
            raise ValueError('Matched production sampling protocol required')
    old, new = a['implementation_sha256'], b['implementation_sha256']
    if set(new)-set(old) != ADDED_CODE or not old.keys() <= new.keys():
        raise ValueError('Unexpected implementation inventory change')
    changed = {key for key in old if old[key] != new[key]}
    if changed-LOADER_CODE:
        raise ValueError('Mathematical or sampling implementation changed')
    return sorted(changed)


def _same_ast(node, expression):
    return ast.dump(node, include_attributes=False) == ast.dump(ast.parse(expression, mode='eval').body, include_attributes=False)


class _RemoveExpandedPlumbing(ast.NodeTransformer):
    """Undo only the exact new sidecar plumbing, then compare the whole v3 AST."""
    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'expanded_floor_sidecar'
                and _same_ast(node.value, 'reviewed_source_lineage.expanded_floor_projection.SIDECAR')):
            return None
        return self.generic_visit(node)

    def visit_Set(self, node):
        node.elts = [e for e in node.elts if not (isinstance(e, ast.Name) and e.id == 'expanded_floor_sidecar')]
        return self.generic_visit(node)

    def visit_Tuple(self, node):
        node.elts = [e for e in node.elts if not _same_ast(e, 'reviewed_source_lineage.expanded_floor_projection')]
        return self.generic_visit(node)

    def visit_Call(self, node):
        if _same_ast(node.func, 'reviewed_source_lineage.source_lineage'):
            expression = "[json.loads(s) for s in files[expanded_floor_sidecar].decode().split('\\n') if s.strip()] if expanded_floor_sidecar in files else None"
            node.keywords = [kw for kw in node.keywords if not
                (kw.arg == 'expanded_floor_changes' and _same_ast(kw.value, expression))]
        return self.generic_visit(node)


def check_v3_loader_change(before, after):
    original = ast.parse(before)
    normalized = _RemoveExpandedPlumbing().visit(ast.parse(after))
    if ast.dump(original, include_attributes=False) != ast.dump(normalized, include_attributes=False):
        raise ValueError('Archived v3 changes exceed exact expanded-sidecar loading and inventory plumbing')
    return True


def check_implementation_sources(a, b, changed):
    name = 'bayesian_feature_experiment_v3.py'
    if name in changed:
        sources = [shared.common.bound_bytes(f['root']/'protocol', name, f['provenance']['protocol_manifest']) for f in (a, b)]
        check_v3_loader_change(*sources)
    # The new contract is itself archived in the candidate protocol, not merely
    # accepted by filename. Source replay below checks it against the local code.
    name = 'expanded_floor_projection.py'
    source = shared.common.bound_bytes(b['root']/'protocol', name, b['provenance']['protocol_manifest'])
    expected = Path(projection.__file__).read_bytes()
    if (source.encode() if isinstance(source, str) else source) != expected:
        raise ValueError('Expanded source contract differs from archived fit implementation')
    return {'v3_exact_sidecar_plumbing_only': True, 'expanded_contract_matches_archive': True}


def verify_revision(reference, candidate):
    bundles = [_verified_bundle(path, retain={'observations.jsonl', projection.SIDECAR}) for path in (reference, candidate)]
    before, after = [shared.report.jsonl(files['observations.jsonl']) for _, files in bundles]
    if projection.SIDECAR not in bundles[1][1]:
        raise ValueError('Missing expanded floor projection sidecar')
    changes = shared.report.jsonl(bundles[1][1][projection.SIDECAR])
    restored = projection.parent_rows(bundles[1][0], after, changes)
    if sha(restored) != sha((bundles[0][0], before)):
        raise ValueError('Expanded floor revision does not restore exact reference source')
    if [r['audit_id'] for r in before] != [r['audit_id'] for r in after]:
        raise ValueError('Expanded floor revision changed membership or order')
    allowed = {'listed_floor', 'advertised_floor', projection.FIELD}
    if any(sha({k: v for k, v in a.items() if k not in allowed}) !=
           sha({k: v for k, v in b.items() if k not in allowed}) for a, b in zip(before, after, strict=True)):
        raise ValueError('Expanded source changed a nonfloor field')
    return before, after


def check_design_arrays(a, b, adata, bdata):
    names = [n for n in a.features if not smooth.is_floor(n)]
    if names != [n for n in b.features if not smooth.is_floor(n)]:
        raise ValueError('Nonfloor columns or ordering changed')
    ai, bi = [[d.features.index(n) for n in names] for d in (a, b)]
    for x, y in [(a.means[ai], b.means[bi]), (a.prior_scales[ai], b.prior_scales[bi]),
                 (a.matrix(adata)[:, ai], b.matrix(bdata)[:, bi])]:
        if not np.array_equal(x, y):
            raise ValueError('Nonfloor encoding, centering or priors changed')
    for design in (a, b):
        knots, anchor = spline.knot_specification(design.floor_levels)
        if design.floor_knots != knots or design.floor_reference != anchor:
            raise ValueError('Spline basis does not follow the fixed support rule')
    if a.floor_reference != b.floor_reference or a.floor_prior_scale != b.floor_prior_scale:
        raise ValueError('Spline reference or coefficient prior changed')
    # Missingness values/centering may change, but its prior and interpretation may not.
    for name in set(a.features) & set(b.features):
        if smooth.is_floor(name) and a.prior_scales[a.features.index(name)] != b.prior_scales[b.features.index(name)]:
            raise ValueError('Floor coefficient prior changed')
    return names


def check_designs(a, b):
    names = check_design_arrays(a['design'], b['design'], a['data'], b['data'])
    times = [json.loads(shared.common.bound_bytes(f['root']/'fit', 'time-design.json', f['provenance']['fit_manifest'])) for f in (a, b)]
    if times[0] != times[1] or a['reconstruction']['time_arrays'] != b['reconstruction']['time_arrays']:
        raise ValueError('Time design or group structure changed')
    return names


def residual_slices(before, after, movements):
    import pandas as pd
    if [r['audit_id'] for r in before] != [r['audit_id'] for r in after]:
        raise ValueError('Residual source membership or order differs')
    old, new = [smooth.increment.listed_floor_values(pd.DataFrame(rows)) for rows in (before, after)]
    corrected = np.array([r.get(projection.FIELD, {}).get('correction_id') is not None for r in after])
    masks = {'all': np.ones(len(after), dtype=bool),
        'current_capture': np.array([r['analysis_price_basis'] == 'current_capture_gross_ask' for r in after]),
        'newly_inferred_floor': ~np.isfinite(old) & np.isfinite(new),
        'corrected_photo_floor': corrected,
        'previously_known_floor': np.isfinite(old) & ~corrected,
        'remaining_unknown_floor': ~np.isfinite(new)}
    indexed = {r['audit_id']: r for r in movements}
    if len(indexed) != len(movements) or set(indexed) != {r['audit_id'] for r in after}:
        raise ValueError('Residual movement membership differs')
    return {name: {**shared.laundry.summarize_slice([indexed[r['audit_id']] for r, keep in zip(after, mask, strict=True) if keep]),
        'buildings': len({r['building'] for r, keep in zip(after, mask, strict=True) if keep})}
        for name, mask in masks.items()}


def prior_comparison(a, b, prior_multiplier):
    """Expose support-driven changes to the joint function prior analytically."""
    levels = sorted(set(a.floor_levels) & set(b.floor_levels))
    weighted = [np.asarray([smooth.curve_vector(design, level) for level in levels]) *
                design.prior_scales * prior_multiplier for design in (a, b)]
    covariances = [vectors @ vectors.T for vectors in weighted]
    sd = [np.sqrt(np.maximum(np.diag(covariance), 0)) for covariance in covariances]
    changes = [{'floor': level, 'reference_log_sd': float(x), 'candidate_log_sd': float(y),
                'log_sd_change': float(y-x)} for level, x, y in zip(levels, *sd, strict=True)]
    return {'reference_floor': 2., 'common_floors': levels,
        'reference_knots': a.floor_knots, 'candidate_knots': b.floor_knots,
        'coefficient_prior_scale': a.floor_prior_scale, 'prior_multiplier': prior_multiplier,
        'endpoint_standard_deviations': changes,
        'reference_log_curve_covariance': covariances[0].tolist(),
        'candidate_log_curve_covariance': covariances[1].tolist(),
        'maximum_absolute_log_sd_change': float(np.max(np.abs(sd[1]-sd[0]))),
        'maximum_absolute_log_covariance_change': float(np.max(np.abs(covariances[1]-covariances[0]))),
        'interpretation': 'Analytical joint prior covariance for common observed floor contrasts relative to floor 2. Matching coefficient scales and the knot rule does not imply a matching function prior when observed endpoints change.'}


def build_comparison(reference, candidate, reference_dataset, dataset):
    before, after = verify_revision(reference_dataset, dataset)
    a, b = shared.load_fits(reference, candidate, reference_dataset, dataset, before, after)
    changed = check_protocols(a['protocol'], b['protocol'])
    implementation_check = check_implementation_sources(a, b, changed)
    names = check_designs(a, b)
    movements, residuals = shared.compare_residuals(a['residuals'], b['residuals'], before, after)
    groups, removed = shared.compare_groups(a['groups'], b['groups'], before, after)
    if removed or residuals['excluded_reference_rows']:
        raise ValueError('Matched population lost observations or groups')
    buildings = sorted({r['building'] for r in after})
    common = [shared.building_contrasts(f, buildings) for f in (a, b)]
    building_changes = [{'id': x['id'], 'log_effect': shared.common.interval_change(x['log_effect'], y['log_effect'])}
        for x, y in zip(common[0]['contrasts'], common[1]['contrasts'], strict=True)]
    building_changes.sort(key=lambda r: (-abs(r['log_effect']['median_change']), r['id']))
    curves = [smooth.curve_from_draws(f['design'], smooth.elevator.beta_draws(f), f['protocol']['prior_multiplier']) for f in (a, b)]
    distinct, seen = [], set()
    for row in movements:
        if row['unit_id'] not in seen:
            distinct.append(row); seen.add(row['unit_id'])
        if len(distinct) == 25:
            break
    result = {'version': VERSION, 'main_selection_changed': False, 'rows': len(after),
        'changed_loader_implementations': changed, 'implementation_scope_verification': implementation_check,
        'unchanged_nonfloor_features': names, 'curves': curves,
        'floor_prior_comparison': prior_comparison(a['design'], b['design'], a['protocol']['prior_multiplier']),
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
            'design_reconstruction': f['reconstruction'], 'floor_parameter_diagnostics': smooth.floor_parameter_diagnostics(f),
            'retained_sampler_work': smooth.sampler_work(f), 'bindings': {k: digest(path/'complete.json') for k, path in
                [('fit', f['root']/'fit'), ('protocol', f['root']/'protocol'), ('source', f['dataset'])]}} for f in (a, b)],
        'floor_support': [f['design'].floor_support for f in (a, b)], 'residuals': residuals,
        'residual_slices': residual_slices(before, after, movements), 'largest_distinct_unit_movements': distinct,
        'largest_unit_offset_movements': [r for r in groups if r['kind'] == 'unit'][:25],
        'largest_common_reference_building_movements': building_changes[:25],
        'building_reference': {'definition': 'Unweighted mean of the identical building population subtracted within each joint posterior draw.',
            'buildings': buildings, 'diagnostics': [value['diagnostics'] for value in common]},
        'limitations': [shared.common.LIMITATION,
            'Own-capture floor data and five reviewed photo-scope corrections change; the spline construction rule, coefficient-prior scales, sampler and nonfloor design are matched.',
            'Floor coverage, centering and observed support change. The fixed rule moves the upper boundary knot with observed support; this changes the induced joint floor-curve prior, which is quantified explicitly. Labels remain proxies for advertised numbering, not physical height.',
            'Residuals are in sample and include unit effects. Current is a dated capture cohort, not a representative test panel.',
            'Joint curve intervals are pointwise conditional associations. Between-fit shifts are descriptive; independent fits are never paired.',
            'Residual and group movements identify units for source review; improvement alone cannot establish identification or justify feature adoption.']}
    for fit in (a, b):
        if digest(fit['root']/'fit/posterior.nc') != fit['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result, movements, groups, building_changes


def render(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'svg.hashsalt': VERSION}):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout='constrained')
        for curve, label, color in zip(result['curves'], ['Original floor coverage', 'Expanded floor coverage'], ['#4564a3', '#b14e38'], strict=True):
            x = [r['floor'] for r in curve['points']]
            for ax, kind in zip(axes, ['log_effect', 'prior_log_effect'], strict=True):
                values = [[r[kind][key] if r.get(kind) is not None else np.nan for r in curve['points']] for key in ('lower_95', 'median', 'upper_95')]
                ax.plot(x, values[1], color=color, label=label)
                ax.fill_between(x, values[0], values[2], color=color, alpha=.18)
        for ax, title in zip(axes, ['Posterior pointwise 95% intervals', 'Induced marginal prior intervals'], strict=True):
            ax.axhline(0, color='gray', lw=.7)
            ax.set(title=title, xlabel='Advertised floor label', ylabel='Log-price component relative to floor 2')
            ax.legend(); ax.grid(alpha=.15)
        fig.suptitle('Expanded floor data: same spline rule; support changes the boundary and curve prior')
        files = {}
        for extension in ('png', 'svg'):
            stream = BytesIO()
            fig.savefig(stream, format=extension, dpi=160, metadata={'Date': None} if extension == 'svg' else None)
            files['floor-curves.'+extension] = stream.getvalue()
        plt.close(fig)
    return files


def run(output, **kwargs):
    modules = (projection, projection.original, shared, shared.report, shared.source, shared.common,
        shared.laundry, shared.floors, smooth, smooth.increment, smooth.contrasts, smooth.elevator,
        spline, experiment, execution, smooth.publisher)
    paths = [Path(__file__), *[Path(module.__file__) for module in modules]]
    hashes = {path.name: digest(path) for path in paths}
    result, movements, groups, buildings = build_comparison(**kwargs)
    files = render(result)
    files.update({'comparison.json': (canonical(result)+'\n').encode(),
        'movements.jsonl': ''.join(canonical(row)+'\n' for row in movements).encode(),
        'residual-movements.jsonl': ''.join(canonical(row)+'\n' for row in movements).encode(),
        'raw-group-movements.jsonl': ''.join(canonical(row)+'\n' for row in groups).encode(),
        'common-reference-building-movements.jsonl': ''.join(canonical(row)+'\n' for row in buildings).encode(),
        **{path.name: path.read_bytes() for path in paths}})
    if any(digest(path) != hashes[path.name] for path in paths):
        raise ValueError('Comparison implementation changed')
    smooth.publisher._publish(output, files, {'version': VERSION,
        'fits': [fit['bindings'] for fit in result['fits']], 'implementation_sha256': hashes})
    print(canonical({'rows': result['rows'], 'output': str(output), 'main_selection_changed': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'reference-dataset', 'candidate', 'dataset', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    with threadpool_limits(limits=1, user_api='blas'):
        run(**vars(parser.parse_args()))
