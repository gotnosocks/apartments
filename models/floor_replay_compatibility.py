"""Recognize only the reviewed read-only floor-replay copying refactor.

Compare bound archived implementations, not just their filenames. This is not
a general equivalence checker and does not waive source-contract validation.
"""
import ast
from copy import deepcopy

FILES = {'floor_label_projection.py', 'expanded_floor_projection.py'}


def same(a, expression):
    return ast.dump(a, include_attributes=False) == ast.dump(ast.parse(expression, mode='eval').body, include_attributes=False)


class _ExpectedRefactor(ast.NodeTransformer):
    def __init__(self, name):
        self.name = name
        self.function = None
        self.counts = {'result_copy': 0, 'parent_replay': 0, 'original_copy': 0, 'original_replay': 0}

    def visit_FunctionDef(self, node):
        previous, self.function = self.function, node.name
        node = self.generic_visit(node)
        self.function = previous
        if node.name != 'project_row':
            return node
        wrapper = deepcopy(node)
        wrapper.body = [ast.Return(value=ast.Call(func=ast.Name(id='deepcopy', ctx=ast.Load()),
            args=[ast.Call(func=ast.Name(id='_project_row_view', ctx=ast.Load()),
                args=[ast.Name(id=a.arg, ctx=ast.Load()) for a in node.args.args], keywords=[])], keywords=[]))]
        node.name = '_project_row_view'
        return [wrapper, node]

    def visit_Assign(self, node):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and same(node.value, 'deepcopy(row)'):
            if self.function == 'project_row' and node.targets[0].id == 'result':
                self.counts['result_copy'] += 1
                node.value = ast.parse('dict(row)', mode='eval').body
            elif self.name == 'expanded_floor_projection.py' and self.function == '_verified_original' and node.targets[0].id == 'before':
                self.counts['original_copy'] += 1
                node.value = ast.parse('dict(row)', mode='eval').body
        return self.generic_visit(node)

    def visit_Call(self, node):
        if self.function == 'parent_rows' and same(node.func, 'project_row'):
            self.counts['parent_replay'] += 1
            node.func = ast.Name(id='_project_row_view', ctx=ast.Load())
        if self.name == 'expanded_floor_projection.py' and self.function == '_verified_original' and same(node.func, 'original.project_row'):
            self.counts['original_replay'] += 1
            node.func = ast.parse('original._project_row_view', mode='eval').body
        return self.generic_visit(node)


def check_refactor(name, before, after):
    if name not in FILES:
        raise ValueError('Not an approved floor replay contract')
    old, new = ast.parse(before), ast.parse(after)
    if any(isinstance(n, ast.FunctionDef) and n.name == '_project_row_view' for n in old.body):
        raise ValueError('Reference already contains private replay; expected the original contract')
    transform = _ExpectedRefactor(name)
    expected = transform.visit(old)
    counts = {'result_copy': 1, 'parent_replay': 1,
              'original_copy': int(name == 'expanded_floor_projection.py'),
              'original_replay': int(name == 'expanded_floor_projection.py')}
    if transform.counts != counts:
        raise ValueError('Reference does not match the reviewed refactor sites')
    # The new helper's explanatory docstring is the sole non-code addition.
    helpers = [n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == '_project_row_view']
    if len(helpers) != 1:
        raise ValueError('Expected exactly one internal replay helper')
    body = helpers[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body.pop(0)
    if ast.dump(expected, include_attributes=False) != ast.dump(new, include_attributes=False):
        raise ValueError('Archived floor changes exceed the reviewed copying-only refactor')
    return True
