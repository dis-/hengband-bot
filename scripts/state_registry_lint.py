"""The policy state against its declared registry (hengbot.state_registry).

Whole-bot maintainability review 2026-11-17 (N2), owner 2026-11-16 Q4 「決まりを足し検査で確かめる」:
the policy grew its state by name (``X = "_xxx"`` constants, ``getattr``/``setattr``/``hasattr``
on the policy, ``self._xxx = ...`` in ``HengbotPolicy.__init__``) with no place saying who owns
it, how long it lives, whether a *Destruction* forgets it or a checkpoint keeps it.  The
registry says it; this lint fails on

- a state name in the source that is neither a registry entry nor in ``NOT_POLICY_STATE``
  (a module-level ``X = "_xxx"`` constant, a ``getattr/setattr/hasattr/delattr`` of a ``_`` name
  on the policy, an attribute assigned in ``HengbotPolicy.__init__``, an attribute assigned on
  ``self`` in any other function of HengbotPolicy or its mixins); the town visit's forwarded
  names (``state_registry.town_visit_columns``, read from ``town_visit``'s tables) are entries,
- a forwarded town-visit name that is also a ``REGISTRY`` row (one declaration per name), or a
  town-visit container that is no row,
- a registry entry no code names (an attribute, a string, or a name reached through a
  constant),
- a registry row that disagrees with the two partial tables it covers:
  ``floor_visit_memory.VISIT_MEMORIES`` (lifetime ``floor``, same owner) and
  ``monster_memory.DESTRUCTION_FORGETS`` (``destruction`` set exactly on its rows, same
  owner); every policy name of ``floor_visit_memory.KEPT`` is an entry,
- ``saved`` that disagrees with the checkpoint (``latch_onset_capture._CAPTURE_STATE_NAMES``
  and the ``_latch_capture_`` names are left out of a checkpoint; every other attribute is in),
- the "reset by" column (``state_registry.RESET_BY``, review 2026-11-18 S4) out of step with the
  source: a counter-like entry (``state_registry.COUNTER_NAME``) with no ``RESET_BY`` row, a row
  of no counter-like entry, a row with neither a site nor a note, a site naming a function its
  module does not define, a reset site of the source (``reset_sites``) the row does not list, a
  listed site that resets nothing of it,
- a ``_*_path`` attribute ``cli`` attaches to the policy (``policy._x_path = ...`` or a
  ``setattr`` of one) that neither ``runtime_paths.POLICY_RUNTIME_PATH_ATTRIBUTES`` nor
  ``runtime_paths.POLICY_RUNTIME_INPUT_PATH_ATTRIBUTES`` names (review 2026-11-25 (a)-1: the
  checkpoint copies and the restore re-points only the paths of those tables), or a name in
  both tables.

A new state: add its row to ``hengbot/state_registry.py``.

    python scripts/state_registry_lint.py            # exit 1 on a finding
    python scripts/state_registry_lint.py --report   # also list the "decision" entries no
                                                     # decision boundary clears (report only)
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from dataclasses import fields as dataclass_fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
sys.path.insert(0, str(ROOT / "src"))

REGISTRY_MODULE = "state_registry"
STATE_NAME = re.compile(r"_[A-Za-z0-9_]+")
ATTRIBUTE_CALLS = ("getattr", "setattr", "hasattr", "delattr")
# The expressions that are the policy where a state is read or written by name.  ``self`` is
# the policy only in HengbotPolicy and its mixins (``_policy_classes``).
POLICY_EXPRESSIONS = frozenset({"policy", "ctx.policy", "owner", "restored"})
# The decision boundary: HengbotPolicy.choose_key clears the per-decision state before the
# producers run, and the record-only ``begin`` of the modules it calls.
DECISION_BOUNDARY = (("policy", "choose_key"), ("cross_rules", "begin"), ("safety_watch", "begin"))


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _modules(root: Path = POLICY_ROOT) -> dict:
    return {path.stem: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for path in sorted(root.glob("*.py"))}


def _string_constants(tree) -> dict:
    """Module-level ``X = "_xxx"`` constants: {X: "_xxx"}."""
    found = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str) and STATE_NAME.fullmatch(node.value.value)
                and not _dunder(node.value.value)):
            found[node.targets[0].id] = node.value.value
    return found


def _policy_classes(modules: dict) -> set:
    """HengbotPolicy and the mixins it is built from, theirs included (their ``self`` is the
    policy)."""
    bases = {}
    for tree in modules.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases.setdefault(node.name, set()).update(
                    ast.unparse(base).rsplit(".", 1)[-1] for base in node.bases)
    names, todo = set(), ["HengbotPolicy"]
    while todo:
        name = todo.pop()
        if name not in names:
            names.add(name)
            todo.extend(bases.get(name, ()))
    return names - {"object"}


class _Calls(ast.NodeVisitor):
    """The ``_`` names read or written by name on the policy in one module."""

    def __init__(self, module: str, constants: dict, policy_classes: set) -> None:
        self.module = module
        self.constants = constants
        self.policy_classes = policy_classes
        self.classes: list[str] = []
        self.found: list[tuple[str, int]] = []

    def visit_ClassDef(self, node) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def _is_policy(self, expression) -> bool:
        text = ast.unparse(expression)
        if text == "self":
            return bool(self.classes) and self.classes[-1] in self.policy_classes
        return text in POLICY_EXPRESSIONS

    def visit_Call(self, node) -> None:
        if (isinstance(node.func, ast.Name) and node.func.id in ATTRIBUTE_CALLS
                and len(node.args) >= 2 and self._is_policy(node.args[0])):
            argument = node.args[1]
            name = (argument.value if isinstance(argument, ast.Constant)
                    else self.constants.get(argument.id) if isinstance(argument, ast.Name) else None)
            if isinstance(name, str) and STATE_NAME.fullmatch(name) and not _dunder(name):
                self.found.append((name, node.lineno))
        self.generic_visit(node)


def init_attributes(modules: dict) -> dict:
    """{attribute: line} assigned on ``self`` in HengbotPolicy.__init__."""
    found = {}
    for node in ast.walk(modules["policy"]):
        if isinstance(node, ast.ClassDef) and node.name == "HengbotPolicy":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for sub in ast.walk(item):
                        targets = (sub.targets if isinstance(sub, ast.Assign)
                                   else [sub.target] if isinstance(sub, (ast.AnnAssign, ast.AugAssign))
                                   else [])
                        for target in targets:
                            for element in (target.elts if isinstance(target, ast.Tuple) else [target]):
                                if (isinstance(element, ast.Attribute)
                                        and isinstance(element.value, ast.Name)
                                        and element.value.id == "self"):
                                    found.setdefault(element.attr, element.lineno)
    return found


def state_names(modules: dict) -> dict:
    """{name: [(how, module, line)]}: every state name the source declares or reaches by name."""
    found = defaultdict(list)
    policy_classes = _policy_classes(modules)
    for module, tree in modules.items():
        if module == REGISTRY_MODULE:
            continue
        constants = _string_constants(tree)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name) and node.targets[0].id in constants:
                found[constants[node.targets[0].id]].append(("constant", module, node.lineno))
        visitor = _Calls(module, constants, policy_classes)
        visitor.visit(tree)
        for name, line in visitor.found:
            found[name].append(("by-name", module, line))
    for name, line in init_attributes(modules).items():
        found[name].append(("init", "policy", line))
    return dict(found)


def used_names(modules: dict) -> set:
    """Every attribute name and string the source (but the registry itself) holds."""
    used = set()
    for module, tree in modules.items():
        if module == REGISTRY_MODULE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                used.add(node.value)
    return used


def _boundary_clears(modules: dict) -> set:
    """The attributes a decision boundary (``DECISION_BOUNDARY``) writes."""
    cleared = set()
    for module, function in DECISION_BOUNDARY:
        for node in ast.walk(modules[module]):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store):
                        cleared.add(sub.attr)
                    elif (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                          and sub.func.id == "setattr" and len(sub.args) >= 2
                          and isinstance(sub.args[1], ast.Constant)):
                        cleared.add(sub.args[1].value)
                    elif (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                          and sub.func.attr in {"pop", "clear"} and sub.args
                          and isinstance(sub.args[0], ast.Constant)):
                        cleared.add(sub.args[0].value)
    return cleared


def never_cleared_decisions(modules: dict) -> list:
    """The "decision" entries no decision boundary writes (report only)."""
    from hengbot import state_registry

    cleared = _boundary_clears(modules)
    return [row for row in state_registry.REGISTRY
            if row.lifetime == state_registry.DECISION and row.name not in cleared]


class _Assigned(ast.NodeVisitor):
    """``self._xxx = ...`` in the functions of HengbotPolicy and its mixins."""

    def __init__(self, module: str, policy_classes: set) -> None:
        self.module = module
        self.policy_classes = policy_classes
        self.scopes: list[tuple[str, str]] = []  # ("class" | "function", name)
        self.found: dict[str, tuple[str, int]] = {}

    def visit_ClassDef(self, node) -> None:
        self.scopes.append(("class", node.name))
        self.generic_visit(node)
        self.scopes.pop()

    def visit_FunctionDef(self, node) -> None:
        self.scopes.append(("function", node.name))
        self.generic_visit(node)
        self.scopes.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _policy_self(self) -> bool:
        classes = [name for kind, name in self.scopes if kind == "class"]
        in_function = any(kind == "function" for kind, _name in self.scopes)
        return in_function and bool(classes) and classes[-1] in self.policy_classes

    def _store(self, targets, line: int) -> None:
        if not self._policy_self():
            return
        if (self.module == "policy"
                and self.scopes[:2] == [("class", "HengbotPolicy"), ("function", "__init__")]):
            return  # init_attributes
        for target in targets:
            for element in (target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]):
                if (isinstance(element, ast.Attribute) and isinstance(element.value, ast.Name)
                        and element.value.id == "self" and STATE_NAME.fullmatch(element.attr)
                        and not _dunder(element.attr)):
                    self.found.setdefault(element.attr, (self.module, line))

    def visit_Assign(self, node) -> None:
        self._store(node.targets, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        if node.value is not None:
            self._store([node.target], node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node) -> None:
        self._store([node.target], node.lineno)
        self.generic_visit(node)


def assigned_attributes(modules: dict) -> dict:
    """{attribute: (module, line)} assigned on ``self`` in a function of HengbotPolicy or a mixin
    (``HengbotPolicy.__init__`` is ``init_attributes``'s)."""
    policy_classes = _policy_classes(modules)
    found = {}
    for module, tree in modules.items():
        if module == REGISTRY_MODULE:
            continue
        visitor = _Assigned(module, policy_classes)
        visitor.visit(tree)
        for name, site in visitor.found.items():
            found.setdefault(name, site)
    return found


# --- The "reset by" column (review 2026-11-18 S4) -------------------------------------------
#
# A reset is a whole-value write of a policy attribute to an empty value: a constant (``None``,
# ``False``, ``""``, a number), an empty literal or an argument-less empty container call
# (``RESET_CALLS``; ``defaultdict(factory)`` too), or a conditional expression with such a
# branch; ``del``/``delattr``; ``.clear()``; ``__dict__.pop``/``vars(...).pop``;
# ``__dict__[name] = <empty>``; ``setattr`` to an empty value (the name a string, a module
# constant, or a ``for`` variable over a literal tuple of them).  ``__init__`` sets the first
# value and is no reset.  ``floor_visit_memory.forget`` resets every ``VISIT_MEMORIES`` name.
RESET_CALLS = frozenset({"set", "dict", "list", "tuple", "frozenset", "Counter", "defaultdict",
                         "deque", "OrderedDict"})


def _empty_value(node) -> bool:
    if isinstance(node, ast.Constant):
        value = node.value
        return value is None or value is False or value == "" or type(value) in (int, float)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.IfExp):
        return _empty_value(node.body) or _empty_value(node.orelse)
    if isinstance(node, ast.Call) and not node.keywords:
        function = node.func
        name = (function.id if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute) else None)
        return name in RESET_CALLS and (
            not node.args or (name == "defaultdict" and len(node.args) == 1))
    return False


class _Resets(_Calls):
    """The reset sites (``module.function``) of the policy's attributes in one module."""

    def __init__(self, module: str, constants: dict, policy_classes: set) -> None:
        super().__init__(module, constants, policy_classes)
        self.functions: list[str] = []
        self.loops: list[tuple[str, list[str]]] = []
        self.resets: list[tuple[str, str]] = []

    def visit_FunctionDef(self, node) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _add(self, name: str) -> None:
        function = self.functions[-1] if self.functions else "<module>"
        if function != "__init__" and STATE_NAME.fullmatch(name) and not _dunder(name):
            self.resets.append((name, f"{self.module}.{function}"))

    def _names(self, node) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.Name):
            if node.id in self.constants:
                return [self.constants[node.id]]
            for variable, names in reversed(self.loops):
                if variable == node.id:
                    return names
        return []

    def _policy_dict(self, node) -> bool:
        return ((isinstance(node, ast.Attribute) and node.attr == "__dict__"
                 and self._is_policy(node.value))
                or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "vars" and len(node.args) == 1
                    and self._is_policy(node.args[0])))

    def visit_For(self, node) -> None:
        names = None
        if isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List)):
            names = []
            for element in node.iter.elts:
                found = (self._names(element)
                         if isinstance(element, (ast.Constant, ast.Name)) else [])
                if len(found) != 1:
                    names = None
                    break
                names.extend(found)
        if names:
            self.loops.append((node.target.id, names))
        self.generic_visit(node)
        if names:
            self.loops.pop()

    def _write(self, target, value) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
                for element, element_value in zip(target.elts, value.elts):
                    self._write(element, element_value)
            return
        if not _empty_value(value):
            return
        if isinstance(target, ast.Attribute) and self._is_policy(target.value):
            self._add(target.attr)
        elif isinstance(target, ast.Subscript) and self._policy_dict(target.value):
            for name in self._names(target.slice):
                self._add(name)

    def visit_Assign(self, node) -> None:
        for target in node.targets:
            self._write(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        if node.value is not None:
            self._write(node.target, node.value)
        self.generic_visit(node)

    def visit_Delete(self, node) -> None:
        for target in node.targets:
            if isinstance(target, ast.Attribute) and self._is_policy(target.value):
                self._add(target.attr)
        self.generic_visit(node)

    def visit_Call(self, node) -> None:
        function = node.func
        if (isinstance(function, ast.Name) and function.id in ("setattr", "delattr")
                and len(node.args) >= 2 and self._is_policy(node.args[0])
                and (function.id == "delattr"
                     or (len(node.args) >= 3 and _empty_value(node.args[2])))):
            for name in self._names(node.args[1]):
                self._add(name)
        elif isinstance(function, ast.Attribute) and function.attr == "clear" and not node.args:
            owner = function.value
            if isinstance(owner, ast.Attribute) and self._is_policy(owner.value):
                self._add(owner.attr)
        elif (isinstance(function, ast.Attribute) and function.attr == "pop" and node.args
              and self._policy_dict(function.value)):
            for name in self._names(node.args[0]):
                self._add(name)
        super().visit_Call(node)


def reset_sites(modules: dict) -> dict:
    """{name: {"module.function"}}: where the source resets each policy attribute (see above)."""
    from hengbot import floor_visit_memory

    found = defaultdict(set)
    policy_classes = _policy_classes(modules)
    for module, tree in modules.items():
        if module == REGISTRY_MODULE:
            continue
        visitor = _Resets(module, _string_constants(tree), policy_classes)
        visitor.visit(tree)
        for name, site in visitor.resets:
            found[name].add(site)
    if "floor_visit_memory" in modules:
        for name, _empty, _owner in floor_visit_memory.VISIT_MEMORIES:
            found[name].add("floor_visit_memory.forget")
    return dict(found)


def _defined_functions(modules: dict) -> dict:
    """{module: {the function names it defines}}."""
    return {module: {node.name for node in ast.walk(tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for module, tree in modules.items()}


def reset_findings(modules: dict) -> list[str]:
    """The "reset by" column (``state_registry.RESET_BY``) against the source's reset sites."""
    from hengbot import state_registry

    lines = []
    counters = {row.name for row in state_registry.REGISTRY
                if state_registry.COUNTER_NAME.search(row.name)}
    table = state_registry.RESET_BY
    sites = reset_sites(modules)
    defined = _defined_functions(modules)
    for name in sorted(counters - set(table)):
        lines.append(f"reset-by: {name} is a counter-like entry with no RESET_BY row (the source "
                     f"resets it in {', '.join(sorted(sites.get(name, ()))) or 'no function'})")
    for name in sorted(set(table) - counters):
        lines.append(f"reset-by: {name} has a RESET_BY row but is no counter-like entry")
    for name in sorted(set(table) & counters):
        reset = table[name]
        if not reset.sites and not reset.note.strip():
            lines.append(f"reset-by: {name} lists no site and has no note")
        for site in reset.sites:
            module, _dot, function = site.partition(".")
            if function not in defined.get(module, ()):
                lines.append(f"reset-by: {name} lists {site}, which its module does not define")
        found = sites.get(name, set())
        for site in sorted(found - set(reset.sites)):
            lines.append(f"reset-by: {name} is reset in {site}, which its RESET_BY row does "
                         "not list")
        for site in sorted(set(reset.sites) - found):
            lines.append(f"reset-by: {name} lists {site}, which resets nothing of it")
    return lines


# --- The runtime path tables (review 2026-11-25 (a)-1) -----------------------------------------
RUNTIME_PATH_NAME = re.compile(r"_[A-Za-z0-9_]+_path")
RUNTIME_PATH_ATTACHER = "cli"


def attached_paths(modules: dict) -> dict:
    """{name: line}: the ``_*_path`` attributes ``cli`` attaches to the policy."""
    found = {}
    tree = modules.get(RUNTIME_PATH_ATTACHER)
    if tree is None:
        return found
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
        for target in targets:
            for element in (target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]):
                if (isinstance(element, ast.Attribute)
                        and ast.unparse(element.value) in POLICY_EXPRESSIONS
                        and RUNTIME_PATH_NAME.fullmatch(element.attr)):
                    found.setdefault(element.attr, element.lineno)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "setattr" and len(node.args) >= 2
                and ast.unparse(node.args[0]) in POLICY_EXPRESSIONS
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
                and RUNTIME_PATH_NAME.fullmatch(node.args[1].value)):
            found.setdefault(node.args[1].value, node.lineno)
    return found


def runtime_path_findings(modules: dict) -> list[str]:
    """Every ``_*_path`` ``cli`` attaches is in one of the runtime path tables."""
    from hengbot import runtime_paths

    written = set(runtime_paths.POLICY_RUNTIME_PATH_ATTRIBUTES)
    read = set(runtime_paths.POLICY_RUNTIME_INPUT_PATH_ATTRIBUTES)
    lines = [f"runtime-path: {name} is in both POLICY_RUNTIME_PATH_ATTRIBUTES and "
             "POLICY_RUNTIME_INPUT_PATH_ATTRIBUTES" for name in sorted(written & read)]
    for name, line in sorted(attached_paths(modules).items()):
        if name not in written | read:
            lines.append(f"{RUNTIME_PATH_ATTACHER}.py:{line} runtime-path: {name} is attached to "
                         "the policy but is in no runtime path table (runtime_paths."
                         "POLICY_RUNTIME_PATH_ATTRIBUTES for a file the policy writes, "
                         "POLICY_RUNTIME_INPUT_PATH_ATTRIBUTES for one it only reads)")
    return lines


def findings(modules: dict | None = None) -> list[str]:
    from hengbot import (floor_visit_memory, latch_onset_capture, monster_memory, state_registry,
                         town_visit)

    modules = modules if modules is not None else _modules()
    lines = []
    by_name = {}
    for row in state_registry.REGISTRY:
        if row.name in by_name:
            lines.append(f"registry: {row.name} is declared twice")
        by_name[row.name] = row
        if row.lifetime not in state_registry.LIFETIMES:
            lines.append(f"registry: {row.name} has lifetime {row.lifetime!r}, not one of "
                         f"{state_registry.LIFETIMES}")
        if not row.purpose.strip():
            lines.append(f"registry: {row.name} has no purpose")
    for name in sorted(set(by_name) & set(state_registry.NOT_POLICY_STATE)):
        lines.append(f"registry: {name} is both an entry and NOT_POLICY_STATE")

    # The town visit's tables are the registry's rows of its forwarded names.
    forwarded = {}
    containers = {"_town_visit": town_visit.TownVisit,
                  **{name: cls for name, (cls, _names) in town_visit._HOLD_CONTAINERS.items()}}
    for row, container, field in state_registry.town_visit_columns():
        cls = containers.get(container)
        if cls is not None and field not in {spec.name for spec in dataclass_fields(cls)}:
            lines.append(f"town-visit: {row.name} forwards to {container}.{field}, a field "
                         f"{cls.__name__} does not have")
        forwarded[row.name] = row
        if row.name in by_name:
            lines.append(f"town-visit: {row.name} is forwarded to {container}.{field} "
                         "(town_visit) and is also a REGISTRY row; keep the one declaration")
        if container not in by_name:
            lines.append(f"town-visit: the container {container} is not declared")
    declared = set(by_name) | set(forwarded) | set(state_registry.NOT_POLICY_STATE)

    names = state_names(modules)
    for name, (module, line) in assigned_attributes(modules).items():
        names.setdefault(name, []).append(("assigned", module, line))
    for name, sites in sorted(names.items()):
        if name in declared:
            continue
        how, module, line = sites[0]
        lines.append(f"{module}.py:{line} {name} ({how}) is not declared in "
                     "hengbot/state_registry.py")

    used = used_names(modules)
    for name in sorted(set(by_name) | set(state_registry.NOT_POLICY_STATE)):
        if name not in used:
            lines.append(f"registry: {name} is declared but no code names it")

    # The two partial tables are columns of the registry.
    for name, _empty, owner in floor_visit_memory.VISIT_MEMORIES:
        row = by_name.get(name)
        if row is None:
            lines.append(f"floor-visit: {name} (VISIT_MEMORIES) is not declared")
        elif row.lifetime != state_registry.FLOOR or row.owner != owner.split(".")[0]:
            lines.append(f"floor-visit: {name} is a VISIT_MEMORIES row of {owner}; the registry "
                         f"says lifetime {row.lifetime}, owner {row.owner}")
    for name in floor_visit_memory.KEPT:
        if name not in by_name and name not in state_registry.NOT_POLICY_STATE:
            lines.append(f"floor-visit: {name} (KEPT) is not declared")
    forgets = {row.attribute: row.module for row in monster_memory.DESTRUCTION_FORGETS}
    for name, module in sorted(forgets.items()):
        row = by_name.get(name)
        if row is None:
            lines.append(f"destruction-forget: {name} (DESTRUCTION_FORGETS) is not declared")
        elif not row.destruction or row.owner != module:
            lines.append(f"destruction-forget: {name} is a DESTRUCTION_FORGETS row of {module}; "
                         f"the registry says destruction={row.destruction}, owner {row.owner}")
    for row in state_registry.REGISTRY:
        if row.destruction and row.name not in forgets:
            lines.append(f"destruction-forget: {row.name} is marked destruction but is no "
                         "DESTRUCTION_FORGETS row")

    left_out = latch_onset_capture._CAPTURE_STATE_NAMES
    for row in state_registry.REGISTRY:
        saved = row.name not in left_out and not row.name.startswith("_latch_capture_")
        if row.saved != saved:
            lines.append(f"checkpoint: {row.name} saved={row.saved}, but the checkpoint "
                         f"{'keeps' if saved else 'leaves out'} it")
    lines.extend(reset_findings(modules))
    lines.extend(runtime_path_findings(modules))
    return lines


def main(argv) -> int:
    modules = _modules()
    lines = findings(modules)
    for line in lines:
        print(line)
    if "--report" in argv:
        rows = never_cleared_decisions(modules)
        print(f"report: {len(rows)} 'decision' entr(y/ies) no decision boundary writes:")
        for row in rows:
            print(f"  {row.name} ({row.owner})")
    print(f"state_registry_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
