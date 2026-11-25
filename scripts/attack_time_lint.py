"""Attack power is compared per 10 game turns, through one reader.

Owner 2026-11-19 (verbatim): 「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりのダメージで
評価して」, scope 「攻撃力の判定すべて」.  The per-action figures (attack_expectation's melee,
launcher, device and throw readers, the quest gate's measured melee, the hands' expectation) are
compared only after attack_expectation.per_10_game_turns (or the loadout comparison's
speed_valuation.per_game_time, the same arithmetic) has scaled them.

A finding is a comparison (``<``, ``<=``, ``>``, ``>=``; not a sign test against 0) in
``src/hengbot`` that holds a per-action figure: a call of one of ``PER_ACTION``, or a name the same function bound from one, unless a
``READERS`` call wraps it.  The producers' own module (attack_expectation) and the arithmetic's
(speed_valuation) are not scanned.  A comparison of two per-action figures of the same character at
the same speed (a choice between attacks, a kill time in player actions against the monsters'
actions per player action) is the same per 10 game turns; the ones that were there on 2026-11-19 are
the recorded baseline (``scripts/attack_time_lint_baseline.json``): only new ones fail.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
# The per-action readers.
PER_ACTION = frozenset({
    "melee", "melee_against", "launcher_shot", "launcher_against", "devices_against",
    "ranged_against", "ammo_against", "torch_throw", "carried_wand", "legacy_melee", "legacy_shot",
    "_strategy_measured_dps", "_main_hand_dps", "_sub_hand_dps", "best_expected",
    "shot_power_per_turn",
})
# The modules whose attribute call of a PER_ACTION name is the per-action reader (``melee`` is a
# common word: only ``attack_expectation.melee`` counts).
PRODUCER_MODULES = frozenset({"attack_expectation", "me_ranged_first", "quest_one_turn_kill",
                              "me_deep_launcher"})
POLICY_METHODS = frozenset({"_strategy_measured_dps", "_main_hand_dps", "_sub_hand_dps"})
# The per-10-game-turn readers and their callers' thin wrappers.
READERS = frozenset({"per_10_game_turns", "per_10_game_turns_at", "per_game_time", "time_melee",
                     "time_ranged", "time_device", "_timed", "row_damage", "timed_turn",
                     })
SKIPPED = frozenset({"attack_expectation.py", "speed_valuation.py"})


# Per-action readers called by bare name inside their own module.
LOCAL_PER_ACTION = frozenset({"shot_power_per_turn"})


def _is_producer(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in LOCAL_PER_ACTION
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    attr, owner = node.func.attr, node.func.value
    if attr not in PER_ACTION:
        return False
    if attr in POLICY_METHODS:
        return True
    return isinstance(owner, ast.Name) and owner.id in PRODUCER_MODULES


def _is_reader(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    return name in READERS


def _untimed(node: ast.AST, tainted: set[str]) -> bool:
    """``node`` holds a per-action figure no reader has scaled."""
    if _is_reader(node):
        return False
    if _is_producer(node):
        return True
    if isinstance(node, ast.Name) and node.id in tainted:
        return True
    if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(_untimed(child, tainted) for child in ast.iter_child_nodes(node))


def _sign_test(node: ast.Compare) -> bool:
    """``x > 0`` and the like: the sign does not change with the speed."""
    return len(node.ops) == 1 and any(
        isinstance(side, ast.Constant) and side.value == 0 for side in (node.left, *node.comparators))


def _targets(target: ast.AST):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _targets(element)


def _function_findings(function, filename: str) -> list[str]:
    tainted: set[str] = set()
    statements = sorted((node for node in ast.walk(function) if isinstance(node, (ast.Assign, ast.AugAssign,
                                                                                    ast.AnnAssign, ast.NamedExpr))),
                        key=lambda node: (node.lineno, node.col_offset))
    for node in statements:
        value = node.value
        if value is None:
            continue
        names = (list(_targets(node.target)) if isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr))
                 else [name for target in node.targets for name in _targets(target)])
        if _untimed(value, tainted):
            tainted.update(names)
        elif not isinstance(node, ast.AugAssign):
            tainted.difference_update(names)
    findings = []
    for node in ast.walk(function):
        if isinstance(node, ast.Compare) and any(
                isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in node.ops) and not _sign_test(node):
            if any(_untimed(operand, tainted) for operand in (node.left, *node.comparators)):
                text = ast.unparse(node)
                findings.append(f"{filename}:{node.lineno}: per-action attack figure compared outside "
                                f"attack_expectation.per_10_game_turns: {text[:120]}")
    return findings


def findings_in(source: str, filename: str = "<source>") -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    seen: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for finding in _function_findings(node, filename):
                line = int(finding.split(":", 2)[1])
                key = hash((line, finding))
                if key not in seen:  # a nested function's comparison is its own
                    seen.add(key)
                    found.append(finding)
    return found


def analyze_repository(root: Path = POLICY_ROOT) -> list[str]:
    found: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.name in SKIPPED:
            continue
        found.extend(findings_in(path.read_text(encoding="utf-8"), path.name))
    return found


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lint_baseline

    problems = analyze_repository()
    print(f"attack-time lint: {len(problems)} per-action comparison(s)")
    for problem in problems:
        print(problem)
    return lint_baseline.gate(
        "attack_time_lint", "attack-time-lint", problems,
        lambda problem: lint_baseline.line_finding_key(problem, POLICY_ROOT),
        argv=sys.argv[1:] if argv is None else argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
