"""The policy state against its declared registry (hengbot.state_registry).

Whole-bot maintainability review 2026-11-17 (N2), owner 2026-11-16 Q4 「決まりを足し検査で確かめる」:
the policy grew its state by name (``X = "_xxx"`` constants, ``getattr``/``setattr``/``hasattr``
on the policy, ``self._xxx = ...`` in ``HengbotPolicy.__init__``) with no place saying who owns
it, how long it lives, whether a *Destruction* forgets it or a checkpoint keeps it.  The
registry says it; this lint fails on

- a state name in the source that is neither a registry entry nor in ``NOT_POLICY_STATE``
  (a module-level ``X = "_xxx"`` constant, a ``getattr/setattr/hasattr/delattr`` of a ``_`` name
  on the policy, an attribute assigned in ``HengbotPolicy.__init__``),
- a registry entry no code names (an attribute, a string, or a name reached through a
  constant),
- a registry row that disagrees with the two partial tables it covers:
  ``floor_visit_memory.VISIT_MEMORIES`` (lifetime ``floor``, same owner) and
  ``monster_memory.DESTRUCTION_FORGETS`` (``destruction`` set exactly on its rows, same
  owner); every policy name of ``floor_visit_memory.KEPT`` is an entry,
- ``saved`` that disagrees with the checkpoint (``latch_onset_capture._CAPTURE_STATE_NAMES``
  and the ``_latch_capture_`` names are left out of a checkpoint; every other attribute is in).

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


def findings(modules: dict | None = None) -> list[str]:
    from hengbot import floor_visit_memory, latch_onset_capture, monster_memory, state_registry

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

    for name, sites in sorted(state_names(modules).items()):
        if name in by_name or name in state_registry.NOT_POLICY_STATE:
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
