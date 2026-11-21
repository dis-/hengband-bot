#!/usr/bin/env python3
"""The owner's equipment rules live in one table: src/hengbot/equipment_rules.py.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E1, 「決まりの重複」): the
twilight robe's ban was written in six places (TR_NO_AC defined three times, two tables of banned
flags), the launcher rules and the Magic-Eater's 50F+ launcher rule in several.  E1 moved each to
``equipment_rules``; this lint keeps them there.  Over every module of ``src/hengbot`` but the
table (read from the AST) it fails:

- ``definition``: an assignment to, or a ``def`` of, one of the table's names (``RULE_NAMES``),
  except the depth table and its private accessor in policy_constants (``OWNER_EXCEPTIONS``);
- ``flag-literal``: the number of a ruled TR flag (``RULED_FLAGS``: NO_AC 141, LOW_AC 134)
  written as an element of a set/tuple/list display or as the left side of ``in`` / ``not in``
  (``141 in item.flags``) -- the flag is named through the table;
- ``grade-literal``: a set/tuple/list display holding both ``"excellent"`` and ``"special"``
  and nothing else (the high-grade pseudo-ID feelings; equipment_rules.HIGH_GRADE_PSEUDO_FEELINGS);
- ``version``: the loadout search's input key (warrior_optimization) or the policy's search memo
  (policy_equipment) does not read ``RULES_VERSION`` (a hand-bumped schema instead).

    python scripts/equipment_rules_lint.py   # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
TABLE_MODULE = "equipment_rules"

RULE_NAMES = frozenset({
    # the bans
    "TR_NO_AC", "TR_LOW_AC", "LOADOUT_BANNED_FLAGS", "EXPLORATION_FORBIDDEN_FLAGS",
    "FORBIDDEN_EXPLORATION_FLAGS", "loadout_banned", "loadout_banned_item_ids",
    "wears_loadout_banned",
    # the Light Crossbow rule and high grade
    "LIGHT_CROSSBOW_SVAL", "YIELDS_TO_LIGHT_CROSSBOW_SVALS", "_YIELDS_TO_LIGHT_XBOW_SVALS",
    "HIGH_GRADE_PSEUDO_FEELINGS", "is_high_grade", "launcher_is_high_grade",
    "ordinary_launcher_yields_to_light_crossbow",
    # the Magic-Eater's 50F+ launcher
    "UNSCORED_LAUNCHER_CLASS", "UNSCORED_LAUNCHER_DEPTH", "SHOT_POWER_FLOOR",
    "launcher_power_unscored",
    # the depth requirements' accessor and the version
    "DEPTH_ABILITY_REQUIREMENTS", "required_abilities_for_depth", "_required_abilities_for_depth",
    "RULES_REVISION", "RULES_VERSION",
})
# The depth table itself stays in policy_constants (the review: 「深さの表そのもの」 is one place).
OWNER_EXCEPTIONS = {"policy_constants": frozenset({"DEPTH_ABILITY_REQUIREMENTS",
                                                   "_required_abilities_for_depth"})}
RULED_FLAGS = {141: "TR_NO_AC", 134: "TR_LOW_AC"}
GRADE_FEELINGS = frozenset({"excellent", "special"})
VERSION_READERS = ("warrior_optimization", "policy_equipment")


def _targets(node: ast.AST):
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            for leaf in ast.walk(target):
                if isinstance(leaf, ast.Name) and isinstance(leaf.ctx, ast.Store):
                    yield leaf.id
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name


def _int(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def analyze_source(source: str, module: str) -> list[str]:
    """The findings of one module (see the module docstring)."""
    if module == TABLE_MODULE:
        return []
    out = []
    allowed = OWNER_EXCEPTIONS.get(module, frozenset())
    reads_version = False
    for node in ast.walk(ast.parse(source)):
        for name in _targets(node):
            if name in RULE_NAMES and name not in allowed:
                out.append((node.lineno, f"{module}:{node.lineno}: definition of {name} -- the rule lives in "
                           f"{TABLE_MODULE}; import it from there"))
        if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
            for element in node.elts:
                value = _int(element)
                if value in RULED_FLAGS:
                    out.append((element.lineno, f"{module}:{element.lineno}: flag-literal {value} "
                                f"-- name it {TABLE_MODULE}.{RULED_FLAGS[value]}"))
            strings = {element.value for element in node.elts
                       if isinstance(element, ast.Constant) and isinstance(element.value, str)}
            if strings == GRADE_FEELINGS and len(node.elts) == len(GRADE_FEELINGS):
                out.append((node.lineno, f"{module}:{node.lineno}: grade-literal -- name it "
                            f"{TABLE_MODULE}.HIGH_GRADE_PSEUDO_FEELINGS"))
        elif isinstance(node, ast.Compare):
            value = _int(node.left)
            if value in RULED_FLAGS and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                out.append((node.lineno, f"{module}:{node.lineno}: flag-literal {value} -- name it "
                            f"{TABLE_MODULE}.{RULED_FLAGS[value]}"))
        elif ((isinstance(node, ast.Attribute) and node.attr == "RULES_VERSION")
              or (isinstance(node, ast.Name) and node.id == "RULES_VERSION")):
            reads_version = True
    out = [finding for _line, finding in sorted(out)]
    if module in VERSION_READERS and not reads_version:
        out.append(f"{module}: version -- the search key does not read "
                   f"{TABLE_MODULE}.RULES_VERSION (a hand-bumped schema goes stale)")
    return out


def repository_findings(root: Path = POLICY_ROOT) -> list[str]:
    out = []
    for path in sorted(root.rglob("*.py")):
        module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        out.extend(analyze_source(path.read_text(encoding="utf-8"), module))
    return out


def main(argv: list[str]) -> int:
    problems = repository_findings()
    for problem in problems:
        print(f"equipment-rules-lint: {problem}")
    print(f"equipment-rules-lint: {len(problems)} finding(s)")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
