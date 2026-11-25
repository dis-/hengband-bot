#!/usr/bin/env python3
"""Keep the policy's readers of the ammunition carry plan on ``_ammo_plan``.

Owner 2026-11-18 「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」: the 50F+ Magic-Eater's
rounds under the floor are not ammunition (me_deep_launcher ``weak_round``).  The shared carry
plan (ammo_carry ``ammo_carry_plan``) is what every count, retention, Home top-up and purchase
reads; the policy's ``_ammo_plan`` passes it the rule's stack filter.  A direct call elsewhere
reads the weak stacks back in (n1-c life-222 2026-11-26: the plain 67/turn arrows bought to 99
every visit and fired at 95F), so it is a violation unless listed in ``ALLOWED`` with its reason.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
PLAN_NAMES = frozenset({"ammo_carry_plan", "power_ammo", "carried_average_damage"})

# (module, function) -> why the direct call stays.
ALLOWED = {
    ("ammo_carry.py", "power_ammo"): "the plan module's own helpers",
    ("ammo_carry.py", "carried_average_damage"): "the plan module's own helpers",
    ("ammo_carry.py", "damage_ammo_purchase"): "the plan module's own helpers",
    ("policy.py", "_ammo_plan"): "the one entry: passes me_deep_launcher.plan_admits",
    # Quest force accounting: a ranged quest's launcher and rounds; the 50F+ Magic-Eater's quest
    # force is read through its devices first (quest_ranged_force, me_deep_launcher.ammo_unneeded
    # closes the remainder), not through these plans.
    ("policy_quest.py", "*"): "quest force accounting (quest_ranged_force rules the Magic-Eater)",
}


def analyze_source(name: str, source: str) -> list[str]:
    tree = ast.parse(source)
    findings: list[str] = []

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Call):
                callee = child.func
                called = (callee.id if isinstance(callee, ast.Name)
                          else callee.attr if isinstance(callee, ast.Attribute) else None)
                if (called in PLAN_NAMES and (name, function) not in ALLOWED
                        and (name, "*") not in ALLOWED):
                    findings.append(f"line {child.lineno}: {function or '<module>'} calls {called} "
                                    "directly (use the policy's _ammo_plan)")
            visit(child, inner)

    visit(tree, "")
    return findings


def main() -> int:
    findings = [
        f"{path.name}: {finding}"
        for path in sorted(POLICY_ROOT.glob("*.py"))
        for finding in analyze_source(path.name, path.read_text(encoding="utf-8"))
    ]
    for finding in findings:
        print(f"ammo-plan-lint: {finding}")
    print(f"ammo-plan-lint: {len(findings)} violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
