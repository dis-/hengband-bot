"""Every melee-composing site must consult ``_can_fight_in_dungeon``.

ROOT-FIX for the 2026-10-23 Anti-melee cave death: one predicate answers
"can this character fight in this dungeon" (static NO_MELEE flag) and every
place that composes a melee attack asks it, so no producer posts melee where
the game refuses it.

A melee-composing site is a ``_direction_key(origin, target)`` call that
aims at a monster -- its second argument is ``<expr>.position`` and the key
is not a missile's ``suffix=`` -- or an alter attack
``ALTER_KEY + _direction_key(...)``.  It is guarded when an enclosing ``if``
of the same function tests the predicate, or an earlier ``if`` of the same
function returns when the predicate fails (``if not pred(...)`` or
``if ... or not pred(...)``).
"""

from __future__ import annotations

import ast
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
PREDICATE = "_can_fight_in_dungeon"


def _attr(node: ast.AST) -> str | None:
    return node.func.attr if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else None


def _tests_predicate(test: ast.AST) -> bool:
    return any(_attr(node) == PREDICATE for node in ast.walk(test))


def _refuses_on_predicate(test: ast.AST) -> bool:
    """``not pred(...)``, alone or as one alternative of an ``or``."""
    alternatives = test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) else [test]
    return any(
        isinstance(alternative, ast.UnaryOp)
        and isinstance(alternative.op, ast.Not)
        and _attr(alternative.operand) == PREDICATE
        for alternative in alternatives
    )


def _is_site(node: ast.AST, parents: dict) -> bool:
    if _attr(node) != "_direction_key" or len(node.args) != 2:
        return False
    parent = parents.get(node)
    if isinstance(parent, ast.keyword) and parent.arg == "suffix":
        return False  # a missile's aim, not a melee attack
    if (
        isinstance(parent, ast.BinOp)
        and isinstance(parent.op, ast.Add)
        and parent.right is node
        and isinstance(parent.left, ast.Name)
        and parent.left.id == "ALTER_KEY"
    ):
        return True
    target = node.args[1]
    return isinstance(target, ast.Attribute) and target.attr == "position"


def _guarded(node: ast.AST, parents: dict) -> bool:
    function = None
    child = node
    ancestor = parents.get(node)
    while ancestor is not None:
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = ancestor
            break
        if isinstance(ancestor, ast.If) and child in ancestor.body and _tests_predicate(ancestor.test):
            return True
        child = ancestor
        ancestor = parents.get(ancestor)
    if function is None:
        return False
    return any(
        isinstance(statement, ast.If)
        and statement.lineno < node.lineno
        and _refuses_on_predicate(statement.test)
        and statement.body
        and isinstance(statement.body[-1], ast.Return)
        for statement in ast.walk(function)
    )


def unguarded_melee_sites(source: str, filename: str = "<source>") -> list[str]:
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    return [
        f"{filename}:{node.lineno}: {ast.unparse(node)}"
        for node in ast.walk(tree)
        if _is_site(node, parents) and not _guarded(node, parents)
    ]


def melee_sites(source: str) -> int:
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    return sum(1 for node in ast.walk(tree) if _is_site(node, parents))


def analyze_repository(root: Path = POLICY_ROOT) -> tuple[int, list[str]]:
    count = 0
    findings: list[str] = []
    for path in sorted(root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        count += melee_sites(source)
        findings.extend(unguarded_melee_sites(source, path.name))
    return count, findings


if __name__ == "__main__":
    total, problems = analyze_repository()
    print(f"melee sites: {total}, unguarded: {len(problems)}")
    for problem in problems:
        print(problem)
    raise SystemExit(1 if problems else 0)
