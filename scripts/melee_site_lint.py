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


# Sites whose guard this syntactic check cannot see, each with where the guard is.
GUARDED_ELSEWHERE = {
    ("combat_answer.py", "direct_blow"):
        "adjacent_attack and strike_key callers: attack_expectation.melee_answers_none_of",
    ("unseen_strike.py", "key"): "strike_cell returns None when the predicate fails",
    ("me_q1_torch.py", "attack_key"): "the direction aims a thrown torch or missile, no melee",
}


def _enclosing_function(node: ast.AST, parents: dict) -> str | None:
    ancestor = parents.get(node)
    while ancestor is not None:
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ancestor.name
        ancestor = parents.get(ancestor)
    return None


def unguarded_melee_sites(source: str, filename: str = "<source>") -> list[str]:
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    return [
        f"{filename}:{node.lineno}: {ast.unparse(node)}"
        for node in ast.walk(tree)
        if _is_site(node, parents) and not _guarded(node, parents)
        and (filename, _enclosing_function(node, parents)) not in GUARDED_ELSEWHERE
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


# The quest plans' walks that close on a monster to melee it ask one gate (contradiction audit
# 2026-11-25 (a)-4, quest_summon_answer.melee_approach): these entries, and any function of a quest
# module that steps under ``APPROACH_REASON`` (the reason of such a walk).
GATE = "melee_approach"
MELEE_APPROACH_ENTRIES = {
    ("quest_summon_answer.py", "_blow_cells"): "the dry cells beside a monster that never comes",
    ("quest_room_sweep.py", "_fight"): "the room sweep's walk to what stands still in view",
    ("quest_summon_answer.py", "_approach"): "the chase of a summoner",
}
APPROACH_NAME = "APPROACH_REASON"


def _functions(tree):
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _asks_gate(function) -> bool:
    return any(isinstance(node, ast.Call) and (getattr(node.func, "attr", None) == GATE
                                                or getattr(node.func, "id", None) == GATE)
               for node in ast.walk(function))


def ungated_approaches(sources: dict) -> list[str]:
    """``sources``: file name -> source.  The approach walks that do not ask the gate, and the
    registered entries the source no longer has."""
    found, seen = [], set()
    for filename, source in sorted(sources.items()):
        if not filename.startswith("quest_"):
            continue
        for function in _functions(ast.parse(source)):
            key = (filename, function.name)
            steps = any(isinstance(node, ast.Name) and node.id == APPROACH_NAME for node in ast.walk(function))
            if key in MELEE_APPROACH_ENTRIES:
                seen.add(key)
            if (key in MELEE_APPROACH_ENTRIES or steps) and not _asks_gate(function):
                found.append(f"{filename}:{function.lineno}: {function.name} closes on a monster without {GATE}")
    found += [f"{filename}: entry {name} not found" for filename, name in sorted(MELEE_APPROACH_ENTRIES)
              if (filename, name) not in seen and filename in sources]
    return found


def main(argv: list[str] | None = None) -> int:
    import sys
    import lint_baseline

    total, problems = analyze_repository()
    print(f"melee sites: {total}, unguarded: {len(problems)}")
    for problem in problems:
        print(problem)
    gated = ungated_approaches({path.name: path.read_text(encoding="utf-8")
                                for path in sorted(POLICY_ROOT.glob("quest_*.py"))})
    for problem in gated:
        print(f"melee-approach-gate: {problem}")
    if gated:
        return 1
    # 2026-11-17 owner (maintainability review Q9): only sites beyond the recorded
    # baseline (scripts/melee_site_lint_baseline.json) fail.
    return lint_baseline.gate(
        "melee_site_lint", "melee-site-lint", problems,
        lambda problem: lint_baseline.line_finding_key(problem, POLICY_ROOT),
        argv=sys.argv[1:] if argv is None else argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
