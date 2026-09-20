"""Strict protocol and archived-code checks for a matched direct-floor refit.

Only the reviewed source revision and its loader plumbing may differ. This
module does not certify posterior convergence or replace the fit comparison.
"""
import ast
from pathlib import Path

import numpy as np

from apartments import direct_floor_projection as projection
from . import expanded_floor_fit_comparison as expanded

spline = expanded.spline
experiment = expanded.experiment
execution = expanded.execution
VARIABLE = expanded.SOURCE_FIELDS | {'implementation_sha256'}
LOADER_CODE = expanded.LOADER_CODE
ADDED_CODE = {'direct_floor_projection.py'}


def check_protocols(a, b):
    if (a.get('version') != experiment.VERSION or b.get('version') != experiment.VERSION
            or a.get('source_version') != projection.residual_scope_projection.VERSION or b.get('source_version') != projection.VERSION
            or a.get('feature_design_version') != spline.VERSION or b.get('feature_design_version') != spline.VERSION
            or a.get('residual_scale') != 'shared' or not execution.verify_protocol(a)
            or not execution.verify_protocol(b)):
        raise ValueError('Expected durable matched spline fits and the direct-floor source revision')
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


class _RemoveDirectFloorPlumbing(ast.NodeTransformer):
    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'direct_floor_sidecar'
                and expanded._same_ast(node.value, 'reviewed_source_lineage.direct_floor_projection.SIDECAR')):
            return None
        return self.generic_visit(node)

    def visit_Set(self, node):
        node.elts = [e for e in node.elts if not (isinstance(e, ast.Name) and e.id == 'direct_floor_sidecar')
                     and not expanded._same_ast(e, 'direct_floor_projection.VERSION')]
        return self.generic_visit(node)

    def visit_Tuple(self, node):
        node.elts = [e for e in node.elts if not expanded._same_ast(e, 'reviewed_source_lineage.direct_floor_projection')]
        return self.generic_visit(node)

    def visit_Call(self, node):
        if expanded._same_ast(node.func, 'reviewed_source_lineage.source_lineage'):
            expression = "[json.loads(s) for s in files[direct_floor_sidecar].decode().split('\\n') if s.strip()] if direct_floor_sidecar in files else None"
            node.keywords = [kw for kw in node.keywords if not
                (kw.arg == 'direct_floor_changes' and expanded._same_ast(kw.value, expression))]
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level == 1 and node.module is None:
            node.names = [n for n in node.names if not (n.name == 'direct_floor_projection' and n.asname is None)]
        return node if node.names else None

    def visit_FunctionDef(self, node):
        if node.name == 'source_lineage':
            kept = [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
                    if not (a.arg == 'direct_floor_changes' and a.annotation is None
                            and isinstance(d, ast.Constant) and d.value is None)]
            node.args.kwonlyargs = [a for a, _ in kept]
            node.args.kw_defaults = [d for _, d in kept]
        return self.generic_visit(node)

    def visit_If(self, node):
        expected = ast.parse("""if manifest['version'] == direct_floor_projection.VERSION:
    manifest, current = direct_floor_projection.parent_rows(manifest, current, direct_floor_changes)
elif direct_floor_changes is not None:
    raise ValueError('Unexpected direct floor sidecar for this source version')""").body[0]
        if ast.dump(node, include_attributes=False) == ast.dump(expected, include_attributes=False):
            return None
        return self.generic_visit(node)


def check_loader_change(before, after):
    old = ast.dump(ast.parse(before), include_attributes=False)
    new = ast.dump(_RemoveDirectFloorPlumbing().visit(ast.parse(after)), include_attributes=False)
    if old != new:
        raise ValueError('Archived changes exceed exact direct-floor loading and inventory plumbing')
    return True



def check_implementation_sources(a, b, changed):
    for name in changed:
        sources = [expanded.shared.common.bound_bytes(
            fit['root']/'protocol', name, fit['provenance']['protocol_manifest']) for fit in (a, b)]
        check_loader_change(*sources)
    name = Path(projection.__file__).name
    code = expanded.shared.common.bound_bytes(b['root']/'protocol', name, b['provenance']['protocol_manifest'])
    if (code.encode() if isinstance(code, str) else code) != Path(projection.__file__).read_bytes():
        raise ValueError('Direct-floor contract differs from archived fit implementation')
    return {'exact_loader_plumbing_verified': True, 'direct_floor_contract_matches_archive': True}
