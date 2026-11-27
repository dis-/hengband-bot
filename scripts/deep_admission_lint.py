"""The readers of the 50F+ depth outside the one answer (hengbot.deep_admission).

Whole-bot maintainability review 2026-11-23 (K2): 「*破壊* なしで50F以降にいない」 was asked by eleven
gates with three predicates of their own, 45 reads of ``DEEP_FLOOR_DEPTH`` among them.  The
admission is now ``deep_admission.verdict``; a module outside it that reads ``DEEP_FLOOR_DEPTH``,
``DEEPEST_WITHOUT_MEANS`` or the climb's ``LANDING``, or compares a depth (a name with depth,
dungeon_level, landing, destination or floor_key in it) with 49, 50 or 51, must be on the list
below (``ALLOWED``: each site with why it reads the depth and does not ask the admission -- the
other 50F+ rules, the climb's own definition, the depth tables).  A new site fails: ask
``deep_admission.verdict`` (or add a route there), or list the site with its reason.

    python scripts/deep_admission_lint.py      # exit 1 on a site off the list
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
FACT_MODULE = "deep_admission"
NAMES = frozenset({"DEEP_FLOOR_DEPTH", "DEEPEST_WITHOUT_MEANS", "LANDING"})
DEPTH_TEXT = re.compile(r"depth|dungeon_level|landing|destination|floor_key", re.IGNORECASE)
DEEP_NUMBERS = frozenset({49, 50, 51})

# (module, function) -> (count, why the site reads the depth and does not ask the admission).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("deep_climb", "<module>"): (3, "the climb's landing and its row of gaps (the depth table's "
                                    "50F row): the climb's own definition"),
    ("deep_climb", "admits"): (1, "the climb's landing is exactly 50F (its definition; the "
                                  "readers ask it as verdict's climbing)"),
    ("deep_climb", "departure_admits"): (1, "the climb's landing is exactly 50F (as admits)"),
    ("deep_climb", "_release_climb"): (1, "the held climb ends once the kit admits its 50F "
                                          "landing (depth_safety's gaps there, n1-c life-221)"),
    ("deep_detection_rod", "<module>"): (1, "owner 2026-11-26 「50F以降は全感知のロッドを持つ」: "
                                           "the rod's rule (DEPTH), not the admission"),
    ("deep_teleport", "applies"): (1, "owner 2026-11-14 「50F以降のテレポートの条件を厳しくする」: "
                                      "the teleport rule, not the admission"),
    ("destruction_use", "ranged_breeders"): (1, "owner 2026-11-22 「群れの数に関わらず破壊対象」: "
                                                "the 50F+ breeder target, not the admission"),
    ("equipment_rules", "<module>"): (1, "owner 2026-11-18: the 50F+ launcher score left out "
                                         "(UNSCORED_LAUNCHER_DEPTH), not the admission"),
    ("explored_floor", "dead_end"): (1, "the deep floors' explored-floor study (its threshold)"),
    ("me_powers", "_deep_floor"): (1, "PLAN-50F section 4 / owner 2026-11-22 「50F以降は使わない」: "
                                      "the absorbed powers' deep rows"),
    ("policy", "_read_key"): (1, "the deep teleport's record (cross_rules.DEEP_TELEPORT)"),
    ("policy_constants", "permitted_dive_depth"): (1, "the intent's clamp to the deepest floor "
                                                      "without the means (verdict's intent)"),
    ("policy_constants", "required_depth_gates"): (1, "the depth table's *Destruction* label "
                                                      "from 50F (the gap the gates read)"),
    ("policy_constants", "required_destruction_uses"): (2, "the uses table: 5 from 50F, +5 per "
                                                           "10 floors (user 2026-09-23)"),
    ("policy_quest", "_quest_light_key"): (1, "owner 2026-11-22 「50F以降は使わない」: the room "
                                              "light, not the admission"),
    ("recall_wait_unknown_path", "key"): (1, "owner 2026-11-23 「見ていないマスも通って向かう」: the "
                                             "50F+ recall wait's walk, not the admission"),
    ("hunt_items", "walk_key"): (1, "supervisor 2026-11-28: the hunt piles' walk over unknown cells "
                                    "on 50F+ as the recall wait's (owner 2026-11-23), not the "
                                    "admission"),
}


class _Sites(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.found: list[tuple[str, str, int]] = []

    def _scope(self, node, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node) -> None:
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node) -> None:
        self._scope(node, self.stack[-1] if self.stack else "<lambda>")

    def _site(self, node) -> None:
        self.found.append((self.module, self.stack[-1] if self.stack else "<module>", node.lineno))

    def visit_Name(self, node) -> None:
        if node.id in NAMES and isinstance(node.ctx, ast.Load):
            self._site(node)

    def visit_Attribute(self, node) -> None:
        if node.attr in NAMES and isinstance(node.ctx, ast.Load):
            self._site(node)
        self.generic_visit(node)

    def visit_Compare(self, node) -> None:
        operands = (node.left, *node.comparators)
        deep = any(isinstance(operand, ast.Constant) and type(operand.value) is int
                   and operand.value in DEEP_NUMBERS for operand in operands)
        if deep and any(DEPTH_TEXT.search(ast.unparse(operand)) for operand in operands
                        if not isinstance(operand, ast.Constant)):
            self._site(node)
        self.generic_visit(node)


def sites(root: Path = POLICY_ROOT) -> list[tuple[str, str, int]]:
    """(module, function, line) of every read outside the fact module."""
    found = []
    for path in sorted(root.glob("*.py")):
        module = path.stem
        if module == FACT_MODULE:
            continue
        visitor = _Sites(module)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found.extend(visitor.found)
    return found


def findings(root: Path = POLICY_ROOT) -> list[str]:
    """A line per site off the list, per listed count exceeded, and per listed site gone."""
    found = sites(root)
    counted = Counter((module, function) for module, function, _line in found)
    lines = []
    for (module, function), count in sorted(counted.items()):
        allowed, _why = ALLOWED.get((module, function), (0, ""))
        if count > allowed:
            where = ", ".join(str(line) for m, f, line in found if (m, f) == (module, function))
            lines.append(f"{module}.py:{function} reads the 50F+ depth {count}x (listed {allowed}; "
                         f"lines {where}): ask deep_admission.verdict instead, or list the site")
    for (module, function), (allowed, _why) in sorted(ALLOWED.items()):
        if counted.get((module, function), 0) < allowed:
            lines.append(f"{module}.py:{function} is listed for {allowed} reads but has "
                         f"{counted.get((module, function), 0)}: shrink ALLOWED")
    return lines


def main() -> int:
    lines = findings()
    for line in lines:
        print(line)
    print(f"deep_admission_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
