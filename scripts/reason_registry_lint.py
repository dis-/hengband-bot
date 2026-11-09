#!/usr/bin/env python3
"""The decision reasons the source can produce, against the registry hengbot.reasons.

The reasons are plain strings put into ``last_reason`` all over ``src/hengbot``; the
per-dive escape count (policy_observation) and the breeder window (breeder_stalemate) read
them through the registry's attributes.  Nothing else ties a new reason to the registry: a
new teleport whose reason is missing from it would silently not count (owner 2026-11-09
「全部の逃げを数える」).  This reads, from the AST, every reason the source sends:

* ``<anything>.last_reason = <expr>`` and ``last_reason = <expr>`` (tuple targets too);
* the arguments given to a parameter called ``reason`` / ``*_reason`` of a function of
  ``src/hengbot``, and ``reason=`` keywords anywhere (the reason a helper or a record
  carries to the assignment);

and resolves ``<expr>`` statically: string literals, module constants (also imported ones,
``module.CONST``), ``+`` and f-strings (an unresolvable part is ``*``), ``a if c else b``,
``a or b``, the function's own local assignments and, for a parameter, the values its
callers pass.  What cannot be resolved at all is not a finding (a reason read from a table
row, say); what resolves to a shape is checked:

* a shape of the escape vocabulary (``reasons.ESCAPE_WORDS``) that the registry does not
  know (``reasons.lookup``) is a finding.

``--print`` lists every resolved shape with its registry entry, for writing the registry's
diff.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
import sys
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hengbot import reasons  # noqa: E402

POLICY_ROOT = ROOT / 'src' / 'hengbot'
PACKAGE = 'hengbot'
WILD = '*'
# A string constant of this form anywhere in the package is taken as a reason as well: the
# reasons a helper returns in a tuple (``return "fire", ammo, "ranged:fire"``) reach
# ``last_reason`` through a subscript the resolution cannot follow.
REASON_LIKE = re.compile(r'^[a-z][a-z0-9-]*(:[a-z0-9_.*-]+)+$')
MAX_SHAPES = 96     # per expression: the product of the parts beyond this is cut to WILD


class Site(NamedTuple):
    """One place that sends a reason: the module, the line, the resolved shapes."""
    module: str
    line: int
    shapes: frozenset


def _normal(shape: str) -> str:
    """Runs of ``*`` are one ``*``."""
    while WILD + WILD in shape:
        shape = shape.replace(WILD + WILD, WILD)
    return shape


def _product(left: set, right: set) -> set:
    if len(left) * len(right) > MAX_SHAPES:
        return {WILD}
    return {_normal(a + b) for a in left for b in right}


class _Module:
    def __init__(self, name: str, tree: ast.Module, nodes: list):
        self.name = name
        self.tree = tree
        self.constants: dict[str, ast.expr] = {}
        self.imports: dict[str, tuple[str, str | None]] = {}   # alias -> (module, name or None)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.constants[target.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                self.constants[node.target.id] = node.value
        for node in nodes:
            if isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    base = f'{PACKAGE}.{base}' if base else PACKAGE
                for alias in node.names:
                    local = alias.asname or alias.name
                    if base == PACKAGE:
                        self.imports.setdefault(local, (alias.name, None))
                    elif base.startswith(PACKAGE + '.'):
                        self.imports.setdefault(local, (base[len(PACKAGE) + 1:], alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(PACKAGE + '.') and alias.asname:
                        self.imports.setdefault(alias.asname, (alias.name[len(PACKAGE) + 1:], None))


_PARSED: dict[str, tuple] = {}


def _parsed(source: str) -> tuple:
    """(tree, every node, node id -> the function around it, the functions defined) of a
    source, kept per source text: the trees are only read, and a test that edits one module
    re-parses that one."""
    cached = _PARSED.get(source)
    if cached is not None:
        return cached
    tree = ast.parse(source)
    nodes, enclosing, defined = [], {}, []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    stack = [(tree, None)]
    while stack:
        node, function = stack.pop()
        nodes.append(node)
        if function is not None:
            enclosing[id(node)] = function
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.append(node)
        inner = node if isinstance(node, functions) else function
        stack.extend((child, inner) for child in ast.iter_child_nodes(node))
    cached = _PARSED[source] = (tree, nodes, enclosing, defined)
    return cached


def _reason_param(name: str) -> bool:
    return name == 'reason' or name.endswith('_reason')


class Scanner:
    """Every reason site of the package, resolved."""

    def __init__(self, sources: dict[str, str]):
        self.modules: dict[str, _Module] = {}
        self.nodes: dict[str, list] = {}
        self.enclosing: dict[int, ast.AST] = {}      # node -> the function around it
        self.functions: dict[str, list[tuple[str, ast.FunctionDef]]] = {}
        self.owner: dict[int, str] = {}
        self._locals: dict[int, dict[str, list]] = {}
        for name, source in sources.items():
            tree, nodes, enclosing, defined = _parsed(source)
            self.nodes[name] = nodes
            self.enclosing.update(enclosing)
            for function in defined:
                self.functions.setdefault(function.name, []).append((name, function))
                self.owner[id(function)] = name
            self.modules[name] = _Module(name, tree, nodes)
        self._replacements: list[tuple[str, int, str, str]] = []
        # (function name, parameter) -> the call sites' argument expressions
        self.arguments: dict[tuple[str, str], list[tuple[str, ast.expr, ast.AST]]] = {}
        for module in self.modules.values():
            for node in self.nodes[module.name]:
                if isinstance(node, ast.Call):
                    self._record_call(module.name, node)
        self._resolving: set = set()

    # ------------------------------------------------------------------ calls and parameters
    @staticmethod
    def _callee(call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return None

    @staticmethod
    def _params(function) -> list[str]:
        args = function.args
        return [a.arg for a in args.posonlyargs + args.args]

    def _record_call(self, module: str, call: ast.Call) -> None:
        name = self._callee(call)
        if name is None or name not in self.functions:
            return
        for _, function in self.functions[name]:
            params = self._params(function)
            offset = 1 if params[:1] in (['self'], ['cls']) and isinstance(call.func, ast.Attribute) else 0
            for index, argument in enumerate(call.args):
                if isinstance(argument, ast.Starred):
                    break
                position = index + offset
                if position < len(params) and _reason_param(params[position]):
                    self.arguments.setdefault((name, params[position]), []).append((module, argument, call))
            for keyword in call.keywords:
                if keyword.arg and _reason_param(keyword.arg) and keyword.arg in (
                        params + [a.arg for a in function.args.kwonlyargs]):
                    self.arguments.setdefault((name, keyword.arg), []).append((module, keyword.value, call))

    def _enclosing_function(self, node):
        return self.enclosing.get(id(node))

    # ------------------------------------------------------------------ resolution
    def resolve(self, module: str, expr, at=None) -> set:
        """The shapes ``expr`` (in ``module``, inside the function around ``at``) can take."""
        if expr is None:
            return {WILD}
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                return {expr.value}
            return set()     # None and the like: no reason
        if isinstance(expr, ast.JoinedStr):
            shapes = {''}
            for part in expr.values:
                if isinstance(part, ast.Constant):
                    shapes = _product(shapes, {str(part.value)})
                elif isinstance(part, ast.FormattedValue):
                    inner = self.resolve(module, part.value, at or expr) if part.format_spec is None else {WILD}
                    shapes = _product(shapes, inner or {WILD})
            return shapes
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            left = self.resolve(module, expr.left, at or expr)
            right = self.resolve(module, expr.right, at or expr)
            return _product(left or {WILD}, right or {WILD})
        if isinstance(expr, ast.IfExp):
            return self.resolve(module, expr.body, at or expr) | self.resolve(module, expr.orelse, at or expr)
        if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.Or):
            out = set()
            for value in expr.values:
                out |= self.resolve(module, value, at or expr)
            return out
        if isinstance(expr, ast.Name):
            return self._resolve_name(module, expr.id, at or expr)
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                and expr.func.attr == 'replace' and len(expr.args) >= 2
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in expr.args[:2])):
            # ``reason.replace("combat:disengage-", "combat:avoid-unprofitable-unique-", 1)``
            old, new = expr.args[0].value, expr.args[1].value
            receiver = self.resolve(module, expr.func.value, at or expr) - {WILD}
            if receiver:
                return {_normal(shape.replace(old, new, 1)) for shape in receiver}
            # An unresolvable receiver (``self.last_reason``): every reason sent elsewhere that
            # has ``old``, rewritten (``sites`` applies it once the other sites are known).
            self._replacements.append((module, expr.lineno, old, new))
            return {WILD}
        if isinstance(expr, ast.Attribute):
            owner = expr.value
            if isinstance(owner, ast.Name):
                imported = self.modules[module].imports.get(owner.id)
                if imported is not None and imported[1] is None and imported[0] in self.modules:
                    return self._resolve_constant(imported[0], expr.attr)
            return {WILD}
        return {WILD}

    def _resolve_constant(self, module: str, name: str) -> set:
        key = (module, name)
        if key in self._resolving or module not in self.modules:
            return {WILD}
        target = self.modules[module]
        self._resolving.add(key)
        try:
            if name in target.constants:
                return self.resolve(module, target.constants[name])
            imported = target.imports.get(name)
            if imported is not None and imported[1] is not None:
                return self._resolve_constant(imported[0], imported[1])
            return {WILD}
        finally:
            self._resolving.discard(key)

    def _resolve_name(self, module: str, name: str, at) -> set:
        function = self._enclosing_function(at)
        if function is not None and not isinstance(function, ast.Lambda):
            local = self._local_values(function, name)
            if local:
                key = (module, id(function), name)
                if key in self._resolving:
                    return {WILD}
                self._resolving.add(key)
                try:
                    out = set()
                    for value in local:
                        out |= self.resolve(module, value, value)
                    return out
                finally:
                    self._resolving.discard(key)
            params = self._params(function) + [a.arg for a in function.args.kwonlyargs]
            if name in params:
                return self._resolve_parameter(function, name)
        return self._resolve_constant(module, name)

    def _local_values(self, function, name: str) -> list:
        table = self._locals.get(id(function))
        if table is None:
            table = self._locals[id(function)] = self._local_table(function)
        return table.get(name, [])

    @staticmethod
    def _local_table(function) -> dict[str, list]:
        """Every local name of ``function`` -> the expressions assigned to it (None: unknown)."""
        table: dict[str, list] = {}

        def add(name, value):
            table.setdefault(name, []).append(value)

        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        add(target.id, node.value)
                    elif isinstance(target, ast.Tuple):
                        paired = (isinstance(node.value, ast.Tuple)
                                  and len(node.value.elts) == len(target.elts))
                        for index, element in enumerate(target.elts):
                            if isinstance(element, ast.Name):
                                add(element.id, node.value.elts[index] if paired else None)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                add(node.target.id, node.value)
            elif isinstance(node, ast.NamedExpr):
                add(node.target.id, node.value)
            elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.target, ast.Name):
                add(node.target.id, None)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                add(node.target.id, None)
        return table

    def _resolve_parameter(self, function, name: str) -> set:
        key = ('param', function.name, name)
        if key in self._resolving:
            return {WILD}
        out = set()
        default = self._default(function, name)
        if default is not None:
            out |= self.resolve(self._module_of(function), default, default)
        sites = self.arguments.get((function.name, name), [])
        if not sites:
            return out | {WILD}
        self._resolving.add(key)
        try:
            for module, argument, call in sites:
                out |= self.resolve(module, argument, call)
        finally:
            self._resolving.discard(key)
        return out

    def _module_of(self, function) -> str:
        return self.owner.get(id(function), '')

    @staticmethod
    def _default(function, name: str):
        args = function.args
        positional = args.posonlyargs + args.args
        defaults = dict(zip([a.arg for a in positional[len(positional) - len(args.defaults):]], args.defaults))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if default is not None:
                defaults[arg.arg] = default
        return defaults.get(name)

    # ------------------------------------------------------------------ the sites
    def sites(self) -> list[Site]:
        found = []
        for module in self.modules.values():
            for node in self.nodes[module.name]:
                for expr in self._sent(node):
                    shapes = frozenset(s for s in self.resolve(module.name, expr, expr) if s != WILD)
                    if shapes:
                        found.append(Site(module.name, getattr(expr, 'lineno', node.lineno), shapes))
        for module in self.modules.values():
            for node in self.nodes[module.name]:
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and REASON_LIKE.match(node.value)):
                    found.append(Site(module.name, node.lineno, frozenset({node.value})))
        for (function, param), arguments in self.arguments.items():
            for module, argument, call in arguments:
                shapes = frozenset(s for s in self.resolve(module, argument, call) if s != WILD)
                if shapes:
                    found.append(Site(module, argument.lineno, shapes))
        known = {shape for site in found for shape in site.shapes}
        for module, line, old, new in sorted(set(self._replacements)):
            shapes = frozenset(_normal(shape.replace(old, new, 1)) for shape in known if old in shape)
            if shapes:
                found.append(Site(module, line, shapes))
        return found

    @staticmethod
    def _sent(node) -> list:
        """The expressions ``node`` puts into a reason."""
        out = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _is_reason_target(target):
                    out.append(node.value)
                elif isinstance(target, ast.Tuple):
                    for index, element in enumerate(target.elts):
                        if _is_reason_target(element):
                            if isinstance(node.value, ast.Tuple) and len(node.value.elts) == len(target.elts):
                                out.append(node.value.elts[index])
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == 'reason':
                    out.append(keyword.value)
        return out


def _is_reason_target(target) -> bool:
    return ((isinstance(target, ast.Attribute) and target.attr == 'last_reason')
            or (isinstance(target, ast.Name) and target.id == 'last_reason'))


def repository_sources() -> dict[str, str]:
    # The registry's own rows are not reasons the package sends.
    return {path.stem: path.read_text(encoding='utf-8') for path in sorted(POLICY_ROOT.glob('*.py'))
            if path.stem != 'reasons'}


def shapes(sources: dict[str, str] | None = None) -> dict[str, list[tuple[str, int]]]:
    """Every resolved reason shape -> where the source sends it."""
    scanner = Scanner(sources if sources is not None else repository_sources())
    out: dict[str, list[tuple[str, int]]] = {}
    for site in scanner.sites():
        for shape in site.shapes:
            out.setdefault(shape, []).append((site.module, site.line))
    return out


def analyze(sources: dict[str, str] | None = None) -> list[str]:
    findings = []
    for shape, places in sorted(shapes(sources).items()):
        if reasons.escape_shaped(shape) and reasons.lookup(shape) is None:
            where = ', '.join(f'{module}.py:{line}' for module, line in sorted(set(places))[:3])
            findings.append(f'unregistered escape-shaped reason {shape!r} ({where}): '
                            'declare it in hengbot/reasons.py (counted, or excluded with the owner rule)')
    return findings


def main(argv: list[str]) -> int:
    if '--print' in argv:
        for shape, places in sorted(shapes().items()):
            entry = reasons.lookup(shape)
            where = ', '.join(f'{module}:{line}' for module, line in sorted(set(places))[:2])
            print(f'{shape}\t{entry.kind if entry else "-"}\t{where}')
        return 0
    findings = analyze()
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
