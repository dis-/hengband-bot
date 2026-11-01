"""Mechanical review of town-work census sites that provably cannot emit work.

A census site needs no hand review entry, and is recorded as observational
data, only when the AST proves all of the following. Anything unproved keeps
needing a hand review, so the proof can only remove entries that never decide
anything at run time:

* its only origin is the producer census (no @claims, ladder, registry,
  decision, design-table or emit/driver tag);
* it emits no key: no return, yield or lambda body can be a str. Proved are
  non-str constants, comparisons, `not`/unary operators, containers, numeric
  and bitwise operators, the safe builtins below, local names whose every
  write is proved, and calls of a module function or a self/cls method whose
  every same-named definition is proved (builtin operator semantics assumed);
* it calls no send seam, directly or through any same-named callee;
* it mutates no object it did not create: no assignment, deletion or
  mutating method call rooted at anything but a fresh local container, no
  setattr/global/nonlocal, and every module function and self/cls method it
  calls is proved the same way;
* it does not call a parameter, a subscript or a call result (a callback may
  be a producer), and has no decorator other than the read-only ones.

The proof reads neither line numbers nor AST digests: an edit that keeps these
properties needs no review and changes no generated file.
"""
from __future__ import annotations

import ast

import town_structure_lint as lint

# The runtime index row of a proved site (town_work.py reads these fields).
DATA_REVIEW = {'classification': 'data', 'rows': ['data/no-independent-credit'],
               'delegation': 'selected child; no independent success'}
SAFE_BUILTINS = frozenset({
    'bool', 'int', 'float', 'len', 'any', 'all', 'isinstance', 'issubclass', 'hasattr', 'callable',
    'sum', 'abs', 'round', 'frozenset', 'set', 'list', 'tuple', 'dict', 'sorted', 'range',
    'enumerate', 'zip', 'reversed', 'divmod', 'id', 'hash', 'ord'})
MUTATORS = frozenset({
    'append', 'extend', 'add', 'update', 'setdefault', 'pop', 'popitem', 'remove', 'discard',
    'clear', 'insert', 'sort', 'reverse', 'appendleft', 'popleft', 'extendleft', 'rotate',
    'write', 'put', 'difference_update', 'intersection_update', 'symmetric_difference_update'})
DYNAMIC = frozenset({'setattr', 'delattr', 'exec', 'eval', 'globals', '__setattr__', '__delattr__'})
FRESH_CONSTRUCTORS = frozenset({'dict', 'list', 'set', 'defaultdict', 'Counter', 'OrderedDict', 'deque'})
FRESH_DISPLAYS = (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp)
READ_ONLY_DECORATORS = frozenset({'property', 'staticmethod', 'classmethod', 'cached_property',
                                  'lru_cache', 'cache'})
NON_STR_NODES = (ast.Compare, ast.UnaryOp, ast.GeneratorExp, ast.Lambda) + FRESH_DISPLAYS
# Operators that never produce a str whatever their (builtin) operands are.
NON_STR_OPERATORS = (ast.Sub, ast.Div, ast.FloorDiv, ast.Pow, ast.BitAnd, ast.BitXor, ast.BitOr,
                     ast.LShift, ast.RShift, ast.MatMult)
SEAM_PREFIXES = ('_send_', '_consume_response_')


def _root(node):
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _leaves(target):
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _leaves(element)
    elif isinstance(target, ast.Starred):
        yield from _leaves(target.value)
    else:
        yield target


def _targets(node):
    if isinstance(node, (ast.Assign, ast.Delete)):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor,
                         ast.comprehension)):
        return [node.target]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [node.optional_vars]
    return []


def _fresh(value):
    return isinstance(value, FRESH_DISPLAYS) or (
        isinstance(value, ast.Call) and lint.name(value.func) in FRESH_CONSTRUCTORS)


class _Site:
    """What one function body shows; the fixpoints combine these per callee."""

    def __init__(self, function):
        arguments = function.args
        self.params = {a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                                       arguments.vararg, arguments.kwarg) if a}
        nodes = list(lint.local_nodes(function))
        # Every value a local name is bound to; None marks an unpacked or loop binding.
        self.writes = {}
        for node in nodes:
            for target in _targets(node):
                exact = isinstance(target, ast.Name) and isinstance(node, (ast.Assign, ast.AnnAssign,
                                                                           ast.NamedExpr))
                for leaf in _leaves(target):
                    if isinstance(leaf, ast.Name):
                        self.writes.setdefault(leaf.id, []).append(node.value if exact else None)
        self.fresh = {name for name, values in self.writes.items()
                      if name not in self.params and all(_fresh(v) for v in values)}
        self.values = [n.value for n in nodes if isinstance(n, (ast.Return, ast.Yield))]
        # A lambda's code is attributed to this site by town_work.code_site.
        self.values += [n.body for n in nodes if isinstance(n, ast.Lambda)]
        self.problems = []
        self.called = set()
        self.calls = []
        for node in nodes:
            self._inspect(node)
        for decorator in function.decorator_list:
            if lint.name(decorator.func if isinstance(decorator, ast.Call) else decorator) \
                    not in READ_ONLY_DECORATORS:
                self.problems.append('decorator')

    def _foreign(self, node):
        """Whether node may be rooted at an object this function did not create."""
        return _root(node) not in self.fresh

    def _inspect(self, node):
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.Await, ast.YieldFrom, ast.Delete)):
            self.problems.append(type(node).__name__)
        for target in _targets(node):
            for leaf in _leaves(target):
                if isinstance(leaf, (ast.Attribute, ast.Subscript)) and self._foreign(leaf):
                    self.problems.append('mutation')
        if not isinstance(node, ast.Call):
            return
        name = lint.name(node.func)
        if name in DYNAMIC:
            self.problems.append('dynamic')
        if not isinstance(node.func, (ast.Name, ast.Attribute)) or (
                isinstance(node.func, ast.Name) and name in self.params | self.writes.keys()):
            self.problems.append('indirect call')
            return
        self.called.add(name)
        self.calls.append(node.func)
        if isinstance(node.func, ast.Attribute) and name in MUTATORS and self._foreign(node.func.value):
            self.problems.append('mutation')

    def call_targets(self, func, names):
        """The definitions a call may run: SAFE_BUILTINS, a set of sites, or None.

        Only a plain name (a module function or a safe builtin) and a method of
        self/cls are resolved; any other receiver may be a foreign object.
        """
        name = lint.name(func)
        if isinstance(func, ast.Name) and name not in self.writes and name not in self.params:
            if name in SAFE_BUILTINS:
                return SAFE_BUILTINS
            return {site for site in names.get(name, ()) if '.' not in site.split(':', 1)[1]} or None
        if isinstance(func, ast.Attribute) and _root(func) in {'self', 'cls'} and \
                isinstance(func.value, ast.Name):
            return {site for site in names.get(name, ()) if '.' in site.split(':', 1)[1]} or None
        return None

    def non_str(self, expr, names, proved, seen=frozenset()):
        """Whether expr cannot be a str, given the sites proved so far (None: optimistic start)."""
        if expr is None or isinstance(expr, NON_STR_NODES):
            return True
        if isinstance(expr, ast.Constant):
            return not isinstance(expr.value, str)
        if isinstance(expr, ast.BoolOp):
            return all(self.non_str(v, names, proved, seen) for v in expr.values)
        if isinstance(expr, ast.IfExp):
            return all(self.non_str(v, names, proved, seen) for v in (expr.body, expr.orelse))
        if isinstance(expr, ast.BinOp):
            return isinstance(expr.op, NON_STR_OPERATORS) or all(
                self.non_str(v, names, proved, seen) for v in (expr.left, expr.right))
        if isinstance(expr, ast.Name):
            values = self.writes.get(expr.id)
            return (bool(values) and expr.id not in seen and expr.id not in self.params
                    and all(v is not None and self.non_str(v, names, proved, seen | {expr.id})
                            for v in values))
        if isinstance(expr, ast.Call):
            targets = self.call_targets(expr.func, names)
            if targets is SAFE_BUILTINS:
                return True
            return bool(targets) and (proved is None or targets <= proved)
        return False


def _greatest(sites, keep):
    """The greatest fixpoint: start from every site, drop those whose callees fell."""
    proved = {site for site in sites if keep(site, None)}
    changed = True
    while changed:
        changed = False
        for site in sorted(proved):
            if not keep(site, proved):
                proved.discard(site)
                changed = True
    return proved


def proved_data(functions, names, origins, selected, seams):
    """The selected sites proved to be observational data by the rules above."""
    facts = {site: _Site(fn) for site, fn in functions.items()}

    def callees(site, called):
        return {target for name in called for target in names.get(name, ()) if target != site}

    def no_seam(site, proved):
        called = facts[site].called
        if called & seams or any(name.startswith(SEAM_PREFIXES) for name in called):
            return False
        return proved is None or callees(site, called) <= proved

    def own_callees(site):
        found = (facts[site].call_targets(func, names) for func in facts[site].calls)
        return {target for targets in found if targets and targets is not SAFE_BUILTINS
                for target in targets} - {site}

    def no_mutation(site, proved):
        return not facts[site].problems and (proved is None or own_callees(site) <= proved)

    def no_key(site, proved):
        return all(facts[site].non_str(v, names, proved) for v in facts[site].values)

    candidates = {site for site in selected if set(origins[site]) == {'census'}}
    return candidates & _greatest(functions, no_seam) & _greatest(functions, no_mutation) \
        & _greatest(functions, no_key)
