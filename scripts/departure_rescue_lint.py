#!/usr/bin/env python3
"""Fail on a departure leaf without a rescue row (town rebuild stage 2).

usage: PYTHONPATH=src python scripts/departure_rescue_lint.py

Reads every leaf the departure gates can return, from the source:

* ``_town_departure_conjuncts`` (its returned dict) and
  ``_recall_town_departure_conjuncts`` (its ``values.update`` dict),
* ``_departure_minimum`` (its ``checks`` dict),
* ``town_terminal.gather_blocked_recall`` (its ``values`` dict),

and checks hengbot.departure_rescues.RESCUES: every leaf has a row, every row
names a gate leaf, every action is a registered action, and every row has an
action or a stop reason.  It also checks that the town terminal's leaf servers
(``_DEPARTURE_LEAF_SERVERS``) name the same leaves.  Exit status 1 on a gap.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "src" / "hengbot"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _dict_keys(node: ast.AST) -> set[str]:
    return {key.value for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)}


def gate_leaves() -> dict[str, set[str]]:
    """{gate: leaf names} read from the gates' source."""
    town = ast.parse((POLICY / "policy_town.py").read_text(encoding="utf-8"))
    terminal = ast.parse((POLICY / "town_terminal.py").read_text(encoding="utf-8"))
    gates: dict[str, set[str]] = {}
    ordinary = _function(town, "_town_departure_conjuncts")
    gates["_town_departure_conjuncts"] = set().union(*(
        _dict_keys(node.value) for node in ast.walk(ordinary)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)))
    recall = _function(town, "_recall_town_departure_conjuncts")
    gates["_recall_town_departure_conjuncts"] = set().union(*(
        _dict_keys(node.args[0]) for node in ast.walk(recall)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update" and node.args and isinstance(node.args[0], ast.Dict)))
    for gate, tree, name, target in (
            ("_departure_minimum", town, "_departure_minimum", "checks"),
            ("gather_blocked_recall", terminal, "gather_blocked_recall", "values")):
        function = _function(tree, name)
        gates[gate] = set().union(*(
            _dict_keys(node.value) for node in ast.walk(function)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
            and any(isinstance(t, ast.Name) and t.id == target for t in node.targets)))
    return gates


def main() -> int:
    sys.path.insert(0, str(POLICY.parent))
    from hengbot.departure_rescues import ACTIONS, RESCUES
    from hengbot.town_terminal import _DEPARTURE_LEAF_SERVERS

    gates = gate_leaves()
    leaves = set().union(*gates.values())
    problems = []
    for gate, names in gates.items():
        if not names:
            problems.append(f"{gate}: no leaves read (the lint lost the gate's dict)")
        for leaf in sorted(names - set(RESCUES)):
            problems.append(f"{gate}: leaf {leaf!r} has no rescue row")
    for leaf, rescue in RESCUES.items():
        if leaf not in leaves:
            problems.append(f"RESCUES: {leaf!r} is no gate leaf (stale row)")
        if not rescue.actions and not rescue.stop_only:
            problems.append(f"RESCUES: {leaf!r} has neither an action nor a stop reason")
        for action in rescue.actions:
            if action not in ACTIONS:
                problems.append(f"RESCUES: {leaf!r} names unknown action {action!r}")
    for leaf in sorted(leaves - set(_DEPARTURE_LEAF_SERVERS)):
        problems.append(f"_DEPARTURE_LEAF_SERVERS: leaf {leaf!r} has no server row")
    for problem in problems:
        print(f"departure-rescue-lint: {problem}")
    print(f"departure-rescue-lint: {len(leaves)} leaves, {len(problems)} gap(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
