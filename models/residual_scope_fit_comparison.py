"""Compare full PyMC spline fits across the reviewed residual-driven scope revision.

Physical scenarios are evaluated within each joint posterior. Independent fit
samples are never paired; normalization is allowed to follow the retained data.
"""
import argparse
import ast
import json
from collections import Counter
from io import BytesIO
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from apartments import residual_scope_projection as projection
from apartments import reviewed_source_lineage as lineage
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from apartments.reviewed_cohort_quarantine import sha
from . import expanded_floor_fit_comparison as expanded
from . import floor_replay_compatibility as replay_compatibility

shared = expanded.shared
smooth = expanded.smooth
spline = expanded.spline
VERSION = 'matched-residual-scope-spline-fit-comparison-v1'
EXCLUDED_ADS = {'1260588', '937046', '2993341', '609730'}
VARIABLE = shared.source.SOURCE_FIELDS - {'current_rows'} | {'implementation_sha256', 'floor_levels', 'floor_knots'}
LOADER_CODE = expanded.LOADER_CODE
ADDED_CODE = {'residual_scope_projection.py'}


def check_protocols(a, b):
    if (a.get('version') != expanded.experiment.VERSION or b.get('version') != expanded.experiment.VERSION
            or a.get('source_version') != projection.PARENT or b.get('source_version') != projection.VERSION
            or any(p.get('feature_design_version') != spline.VERSION or p.get('residual_scale') != 'shared'
                   or not expanded.execution.verify_protocol(p) for p in (a, b))):
        raise ValueError('Expected durable shared-noise spline fits across residual scope revision')
    if {k: v for k, v in a.items() if k not in VARIABLE} != {k: v for k, v in b.items() if k not in VARIABLE}:
        raise ValueError('Spline specification, prior, sampler, current population or environment changed')
    for p in (a, b):
        levels = p.get('floor_levels', [])
        if len(levels) < 2 or levels != sorted(set(levels)) or not np.isfinite(levels).all() or 2. not in levels:
            raise ValueError('Invalid floor support')
        knots, anchor = spline.knot_specification(levels)
        if p.get('floor_knots') != knots or p.get('floor_reference') != anchor or p.get('floor_policy') != spline.policy():
            raise ValueError('Invalid spline construction rule')
        expected = {'chains': 4, 'tune': 4000, 'draws': 6000, 'target_accept': .93,
                    'adaptation': 'diag', 'seed': 20260924, 'maxdepth': 10}
        if any(p.get(k) != v for k, v in expected.items()):
            raise ValueError('Matched full production sampling required')
    old, new = a['implementation_sha256'], b['implementation_sha256']
    if not old.keys() <= new.keys() or new.keys()-old.keys() != ADDED_CODE:
        raise ValueError('Unexpected implementation inventory change')
    changed = {k for k in old if old[k] != new[k]}
    if changed-LOADER_CODE-replay_compatibility.FILES:
        raise ValueError('Mathematical or sampling implementation changed')
    return sorted(changed)


class _RemoveScopePlumbing(ast.NodeTransformer):
    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'residual_scope_sidecar'
                and expanded._same_ast(node.value, 'reviewed_source_lineage.residual_scope_projection.SIDECAR')):
            return None
        return self.generic_visit(node)

    def visit_Set(self, node):
        node.elts = [e for e in node.elts if not (isinstance(e, ast.Name) and e.id == 'residual_scope_sidecar')
                     and not expanded._same_ast(e, 'residual_scope_projection.VERSION')]
        return self.generic_visit(node)

    def visit_Tuple(self, node):
        node.elts = [e for e in node.elts if not expanded._same_ast(e, 'reviewed_source_lineage.residual_scope_projection')]
        return self.generic_visit(node)

    def visit_Call(self, node):
        if expanded._same_ast(node.func, 'reviewed_source_lineage.source_lineage'):
            expression = "[json.loads(s) for s in files[residual_scope_sidecar].decode().split('\\n') if s.strip()] if residual_scope_sidecar in files else None"
            node.keywords = [kw for kw in node.keywords if not
                (kw.arg == 'residual_scope_changes' and expanded._same_ast(kw.value, expression))]
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level == 1 and node.module is None:
            node.names = [n for n in node.names if not (n.name == 'residual_scope_projection' and n.asname is None)]
        return node if node.names else None

    def visit_FunctionDef(self, node):
        if node.name == 'source_lineage':
            kept = [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
                    if not (a.arg == 'residual_scope_changes' and a.annotation is None
                            and isinstance(d, ast.Constant) and d.value is None)]
            node.args.kwonlyargs = [a for a, _ in kept]
            node.args.kw_defaults = [d for _, d in kept]
        return self.generic_visit(node)

    def visit_If(self, node):
        expected = ast.parse("""if manifest['version'] == residual_scope_projection.VERSION:
    manifest, current = residual_scope_projection.parent_rows(manifest, current, residual_scope_changes)
elif residual_scope_changes is not None:
    raise ValueError('Unexpected residual scope sidecar for this source version')""").body[0]
        if ast.dump(node, include_attributes=False) == ast.dump(expected, include_attributes=False):
            return None
        return self.generic_visit(node)


def check_loader_change(before, after):
    old = ast.dump(ast.parse(before), include_attributes=False)
    new = ast.dump(_RemoveScopePlumbing().visit(ast.parse(after)), include_attributes=False)
    if old != new:
        raise ValueError('Archived changes exceed exact residual-scope loading and inventory plumbing')
    return True


def check_implementation_sources(a, b, changed):
    for name in changed:
        code = [shared.common.bound_bytes(f['root']/'protocol', name, f['provenance']['protocol_manifest']) for f in (a, b)]
        if name in replay_compatibility.FILES:
            replay_compatibility.check_refactor(name, *code)
        else:
            check_loader_change(*code)
    for module in (projection, lineage.expanded_floor_projection, lineage.floor_label_projection):
        name = Path(module.__file__).name
        code = shared.common.bound_bytes(b['root']/'protocol', name, b['provenance']['protocol_manifest'])
        if (code.encode() if isinstance(code, str) else code) != Path(module.__file__).read_bytes():
            raise ValueError('Source contract differs from archived fit implementation')
    return {'archived_loader_ast_verified': True, 'scope_and_both_floor_contracts_match_archive': True,
            'copying_only_floor_refactors_verified': sorted(set(changed) & replay_compatibility.FILES)}


def verify_revision(reference, candidate, *, policy=None):
    expected_ads = EXCLUDED_ADS
    policy_bytes = None
    if policy is not None:
        policy_bytes = Path(policy).read_bytes()
        specification = json.loads(policy_bytes)
        expected_ads = reviewed_ads(specification, digest(Path(reference)/'complete.json'))
    sidecars = {key: module.SIDECAR for key, module in (
        ('quarantined', lineage.reviewed_cohort_quarantine), ('elevator_changes', lineage.elevator_corrections),
        ('floor_label_changes', lineage.floor_label_projection), ('expanded_floor_changes', lineage.expanded_floor_projection))}
    bundles = [_verified_bundle(path, retain={'observations.jsonl', projection.SIDECAR,
                                             'residual-scope-policy.json', *sidecars.values()})
               for path in (reference, candidate)]
    before, after = [shared.report.jsonl(files['observations.jsonl']) for _, files in bundles]
    if projection.SIDECAR not in bundles[1][1]:
        raise ValueError('Missing residual scope quarantine sidecar')
    excluded = shared.report.jsonl(bundles[1][1][projection.SIDECAR])
    if policy_bytes is not None and bundles[1][1].get('residual-scope-policy.json') != policy_bytes:
        raise ValueError('Published scope policy differs from explicitly requested review')
    if sha(projection.parent_rows(bundles[1][0], after, excluded)) != sha((bundles[0][0], before)):
        raise ValueError('Residual scope inverse does not restore exact reference source')
    if after != [r for r in before if r['source_listing_id'] not in expected_ads]:
        raise ValueError('Retained observations or order changed beyond the explicitly reviewed ads')
    if {r['observation']['source_listing_id'] for r in excluded} != expected_ads:
        raise ValueError('Excluded ads differ from reviewed scope experiment')
    current = lambda rows: [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if current(before) != current(after):
        raise ValueError('Current captures changed')
    ancestors = []
    for i, (manifest, files) in enumerate(bundles):
        args = {key: shared.report.jsonl(files[name]) if name in files else None for key, name in sidecars.items()}
        if any(name not in files for name in sidecars.values()):
            raise ValueError('Missing inherited source lineage sidecar')
        ancestors.append(lineage.source_lineage(manifest, (before, after)[i],
            residual_scope_changes=excluded if i else None, **args))
    if sha(ancestors[0]) != sha(ancestors[1]) or any(bundles[0][1][name] != bundles[1][1][name] for name in sidecars.values()):
        raise ValueError('Inherited source or floor layers changed')
    return before, after, excluded


def reviewed_ads(specification, reference_hash):
    if (specification.get('version') != 'chelsea-residual-scope-policy-v1'
            or specification.get('source_manifest_sha256') != reference_hash):
        raise ValueError('Reviewed policy binds a different source')
    cases = specification.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Reviewed policy must name exact advertisements')
    ads = [case.get('source_listing_id') for case in cases]
    if (any(type(ad) is not str or not ad for ad in ads) or len(set(ads)) != len(ads)
            or any(case.get('action') not in projection.ACTIONS for case in cases)):
        raise ValueError('Invalid or duplicate reviewed advertisement decisions')
    return set(ads)


def check_designs(a, b):
    # Each saved design has already been reconstructed from its exact training
    # rows by load_fits. Empirical centers, category frequencies and group counts
    # are intentionally not required to match across a membership revision.
    x, y = a['design'], b['design']
    for design in (x, y):
        knots, anchor = spline.knot_specification(design.floor_levels)
        if design.floor_knots != knots or design.floor_reference != anchor:
            raise ValueError('Saved spline violates fixed support rule')
    common = sorted(set(x.features) & set(y.features))
    if any(x.prior_scales[x.features.index(k)] != y.prior_scales[y.features.index(k)] for k in common):
        raise ValueError('Common coefficient prior scales changed')
    if x.floor_reference != y.floor_reference or x.floor_prior_scale != y.floor_prior_scale or x.spec != y.spec:
        raise ValueError('Floor reference, prior or bathroom specification changed')
    return {'common_features': common, 'reference_only': sorted(set(x.features)-set(y.features)),
            'candidate_only': sorted(set(y.features)-set(x.features))}


def matched_physical_contrasts(a, b):
    """Match scenario identity, never empirical support, coordinates or basis."""
    def indexed(rows):
        result = {r['id']: r for r in rows}
        if len(result) != len(rows):
            raise ValueError('Duplicate physical scenario')
        return result
    x, y = indexed(a), indexed(b)
    matched = []
    for key in sorted(x.keys() & y.keys()):
        left, right = x[key], y[key]
        fields = ('field', 'before', 'after', 'held_fixed')
        if any(left.get(k) != right.get(k) for k in fields):
            raise ValueError('Physical scenario semantics differ')
        accepted = all(row['status'] == 'supported_converged' for row in (left, right))
        matched.append({'id': key, 'reference': left, 'candidate': right,
            'percent_effect': shared.common.interval_change(left['percent_effect'], right['percent_effect']) if accepted else None,
            'status': 'matched_converged' if accepted else 'withheld_derived_diagnostics'})
    return {'matched': matched, 'reference_only': [x[k] for k in sorted(x.keys()-y.keys())],
            'candidate_only': [y[k] for k in sorted(y.keys()-x.keys())]}


def matched_floor_curves(a, b):
    """Compare only identical physical endpoints, retaining endpoint diagnostics."""
    if a['reference_floor'] != b['reference_floor']:
        raise ValueError('Floor reference changed')
    points = []
    for curve in (a, b):
        values = []
        for row in curve['points']:
            if row['floor'] == curve['reference_floor']:
                continue
            values.append({**row, 'field': 'listed_floor', 'before': curve['reference_floor'],
                           'after': row['floor']})
        points.append(values)
    return matched_physical_contrasts(*points)


def bedroom_definitions(fits):
    """Fixed observed area and bath composition distinguish total bedroom effects
    from a lone bedroom coefficient (which omits size normalization/shortfall).
    """
    frame = fits[1]['data']
    full, half, known = smooth.contrasts.feature.bathroom_values(frame)
    cells = sorted({(int(row.bedrooms), int(f), int(h)) for (_, row), f, h, ok
                    in zip(frame.iterrows(), full, half, known, strict=True) if ok})
    definitions = []
    for bed, f, h in cells:
        if (bed+1, f, h) not in cells:
            continue
        mask = known & (full == f) & (half == h) & frame.bedrooms.isin([bed, bed+1]).to_numpy()
        area = frame.loc[mask, 'square_feet'].to_numpy(float)
        area = area[np.isfinite(area) & (area > 0)]
        if not len(area):
            continue
        definitions.append({'id': f'bedrooms:{bed}->{bed+1}:full={f}:half={h}', 'field': 'bedrooms',
            'before': bed, 'after': bed+1,
            'held_fixed': {'full_bathrooms': f, 'half_bathrooms': h, 'square_feet': float(np.median(area))}})
    return definitions


def bedroom_contrasts(fit, beta, definitions):
    design, frame = fit['design'], fit['data']
    full, half, known = smooth.contrasts.feature.bathroom_values(frame)
    items = []
    for definition in definitions:
        held = definition['held_fixed']; f, h = held['full_bathrooms'], held['half_bathrooms']
        frames = [frame.loc[known & (full == f) & (half == h) & frame.bedrooms.eq(definition[key]).to_numpy()]
                  for key in ('before', 'after')]
        if any(value.empty for value in frames):
            continue
        a = frame.iloc[[0]].copy()
        # Use a known shared floor inside either source's range for this scenario.
        a['listed_floor'] = 2.; a['advertised_floor'] = 2.
        a['reported_full_bathrooms'] = f; a['reported_half_bathrooms'] = h
        a['bathrooms'] = f+.5*h; a['bathroom_count_evidence'] = [{}]
        a['square_feet'] = held['square_feet']; a['bedrooms'] = definition['before']
        b = a.copy(); b['bedrooms'] = definition['after']
        vector = (design.matrix(b)-design.matrix(a))[0]
        if not np.any(abs(vector) > 1e-14):
            continue
        items.append({**definition, 'design_vector': vector.tolist(),
            'support_before': smooth.contrasts.support(frames[0]), 'support_after': smooth.contrasts.support(frames[1])})
    return smooth.contrasts.calculate(beta, items)[0] if items else []


def build_comparison(reference, candidate, reference_dataset, dataset, policy=None):
    policy_hash = digest(policy) if policy is not None else None
    before, after, excluded = verify_revision(reference_dataset, dataset, policy=policy)
    fits = shared.load_fits(reference, candidate, reference_dataset, dataset, before, after)
    a, b = fits
    changed = check_protocols(a['protocol'], b['protocol'])
    implementation = check_implementation_sources(a, b, changed)
    features = check_designs(a, b)
    movements, residuals = shared.compare_residuals(a['residuals'], b['residuals'], before, after)
    groups, removed = shared.compare_groups(a['groups'], b['groups'], before, after)
    buildings = sorted({r['building'] for r in after})
    common = [shared.building_contrasts(f, buildings) for f in fits]
    building_changes = [{'id': x['id'], 'log_effect': shared.common.interval_change(x['log_effect'], y['log_effect'])}
        for x, y in zip(common[0]['contrasts'], common[1]['contrasts'], strict=True)]
    building_changes.sort(key=lambda r: (-abs(r['log_effect']['median_change']), r['id']))
    definitions = bedroom_definitions(fits)
    curves, bedrooms, categories = [], [], []
    for f in fits:
        beta = smooth.elevator.beta_draws(f)
        curves.append(smooth.curve_from_draws(f['design'], beta, f['protocol']['prior_multiplier']))
        bedrooms.append(bedroom_contrasts(f, beta, definitions))
        _, definitions_categories, _ = smooth.contrasts.construct_contrasts(f['design'], f['data'])
        categories.append(smooth.contrasts.calculate(beta, definitions_categories)[0] if definitions_categories else [])
    affected = Counter(row['observation']['building'] for row in excluded)
    result = {'version': VERSION, 'main_selection_changed': False,
        'review_policy_sha256': policy_hash,
        'source_rows': len(before), 'retained_rows': len(after), 'excluded_rows': len(excluded),
        'affected_buildings': dict(affected), 'changed_loader_implementations': changed,
        'implementation_scope_verification': implementation, 'feature_support': features,
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
            'design_reconstruction': f['reconstruction'], 'floor_parameter_diagnostics': smooth.floor_parameter_diagnostics(f),
            'retained_sampler_work': smooth.sampler_work(f), 'bindings': {k: digest(path/'complete.json') for k, path in
                [('fit', f['root']/'fit'), ('protocol', f['root']/'protocol'), ('source', f['dataset'])]}} for f in fits],
        'normalization': [{'numeric': f['design'].numeric, 'centering': f['design'].means.tolist(),
            'categories': f['design'].categories, 'size_medians': f['design'].time.size_medians,
            'size_default': f['design'].time.size_default} for f in fits],
        'residuals': residuals, 'removed_groups': removed,
        'largest_distinct_unit_movements': distinct_units(movements),
        'largest_unit_offset_movements': [r for r in groups if r['kind'] == 'unit'][:25],
        'largest_common_reference_building_movements': building_changes[:25],
        'affected_common_reference_building_movements': [r for r in building_changes if r['id'] in affected],
        'building_reference': {'definition': 'Unweighted mean of identical retained buildings, subtracted within each joint posterior draw.',
            'buildings': buildings, 'diagnostics': [value['diagnostics'] for value in common]},
        'curves': curves, 'floor_contrasts': matched_floor_curves(*curves),
        'floor_support': [f['design'].floor_support for f in fits],
        'floor_prior_comparison': expanded.prior_comparison(a['design'], b['design'], a['protocol']['prior_multiplier']),
        'bedroom_contrasts': matched_physical_contrasts(*bedrooms),
        'category_contrasts': matched_physical_contrasts(*categories),
        'bathrooms': {name: shared.source.compare_contrasts(a['report']['bathrooms'][name], b['report']['bathrooms'][name], fields)
            for name, fields in [('full_bath_increments', ('log_effect', 'percent_effect')),
                ('half_bath_increments', ('log_effect', 'percent_effect')), ('net_balance', ('difference',))]},
        'limitations': [shared.common.LIMITATION,
            f'Exactly {len(excluded)} reviewed ads are excluded for commercial scope or unresolved location conflict; residual magnitude alone is not an exclusion rule.',
            'Residual improvement is measured only on identical retained observations. Excluded tail observations have reference-only residuals.',
            'Data-derived normalization, support and group counts are refitted. Equal coefficient scales need not give identical induced function priors.',
            'Physical bedroom contrasts hold observed area and bath composition fixed and include size normalization and bathroom shortfall contributions.',
            'Building contrasts use a common within-posterior reference; raw category basis coefficients are never interpreted as premiums.',
            'Conditional in-sample associations are not causal effects or willingness to pay. Current denotes a dated capture cohort.',
            'Pointwise convergence failures withhold the affected contrast; between-fit shifts are descriptive and draws are never paired.']}
    for f in fits:
        if digest(f['root']/'fit/posterior.nc') != f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    if policy is not None and digest(policy) != policy_hash:
        raise ValueError('Review policy changed during comparison')
    return result, movements, groups, building_changes


def distinct_units(movements):
    selected, seen = [], set()
    for row in movements:
        if row['unit_id'] not in seen:
            selected.append(row); seen.add(row['unit_id'])
        if len(selected) == 25:
            break
    return selected


def render(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size': 10, 'svg.hashsalt': VERSION}):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout='constrained')
        for curve, label, color in zip(result['curves'], ['Before scope review', 'Reviewed retained cohort'], ['#4564a3', '#b14e38'], strict=True):
            x = [r['floor'] for r in curve['points']]
            for ax, kind in zip(axes, ['log_effect', 'prior_log_effect'], strict=True):
                values = [[r[kind][k] if r.get(kind) is not None else np.nan for r in curve['points']]
                          for k in ('lower_95', 'median', 'upper_95')]
                ax.plot(x, values[1], color=color, label=label)
                ax.fill_between(x, values[0], values[2], color=color, alpha=.18)
        for ax, title in zip(axes, ['Posterior pointwise 95% intervals', 'Induced marginal prior intervals'], strict=True):
            ax.axhline(0, color='gray', lw=.7)
            ax.set(title=title, xlabel='Advertised floor label', ylabel='Log-price component relative to floor 2')
            ax.legend(); ax.grid(alpha=.15)
        fig.suptitle('Residual-driven scope review: matched spline construction and full PyMC fits')
        files = {}
        for extension in ('png', 'svg'):
            stream = BytesIO()
            fig.savefig(stream, format=extension, dpi=160, metadata={'Date': None} if extension == 'svg' else None)
            files['floor-curves.'+extension] = stream.getvalue()
        plt.close(fig)
    return files


def run(output, **kwargs):
    modules = (projection, lineage, lineage.expanded_floor_projection, lineage.floor_label_projection, replay_compatibility,
        expanded, shared, shared.report, shared.source, shared.common, shared.laundry, smooth, smooth.increment,
        smooth.contrasts, smooth.elevator, spline, expanded.experiment, expanded.execution, smooth.publisher)
    paths = [Path(__file__), *[Path(m.__file__) for m in modules]]
    hashes = {p.name: digest(p) for p in paths}
    result, movements, groups, buildings = build_comparison(**kwargs)
    files = render(result)
    files.update({'comparison.json': (canonical(result)+'\n').encode(),
        'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements).encode(),
        'raw-group-movements.jsonl': ''.join(canonical(r)+'\n' for r in groups).encode(),
        'common-reference-building-movements.jsonl': ''.join(canonical(r)+'\n' for r in buildings).encode(),
        **{p.name: p.read_bytes() for p in paths}})
    if any(digest(p) != hashes[p.name] for p in paths):
        raise ValueError('Comparison implementation changed')
    smooth.publisher._publish(output, files, {'version': VERSION,
        'fits': [f['bindings'] for f in result['fits']], 'implementation_sha256': hashes})
    print(canonical({'retained_rows': result['retained_rows'], 'excluded_rows': result['excluded_rows'], 'output': str(output)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'reference-dataset', 'candidate', 'dataset', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--policy', type=Path, help='Explicit cumulative policy; omitted enforces the original four exclusions')
    with threadpool_limits(limits=1, user_api='blas'):
        run(**vars(parser.parse_args()))
