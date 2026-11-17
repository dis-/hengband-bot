"""The readers of *Destruction*'s scene outside its one module (hengbot.destruction_use).

Whole-bot maintainability review 2026-11-17 (N1, 5(a)-3): whether the scene admits a use (the
means held, a clear head, a floor the use touches), whom the use spares and whether a monster is
inside its sure radius were read outside destruction_use by its private functions (18 sites:
``_target_race``, ``_clear_headed``, ``_floor_destroyed``, ``_scene_holds`` ...) and by 11
comparisons of a distance against ``GUARANTEED_RADIUS``.  They now go through its public readers
(``approach_gates``, ``in_sure_radius``, ``spares``, ``quest_target_race``, ``scene_holds``,
``means_in_hand``).  A module outside destruction_use fails here when it

- reads a private name of destruction_use (``destruction_use._xxx``, or imports one), or
- compares a distance against the sure radius: a comparison one side of which is
  ``GUARANTEED_RADIUS`` (or a local name bound to it), or the literal 13 against a
  ``game_distance(...)`` call or a ``.distance`` attribute.

Ask ``destruction_use.in_sure_radius`` (or add a public reader there) instead.

    python scripts/destruction_scene_lint.py      # exit 1 on any finding
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
SCENE_MODULE = "destruction_use"
RADIUS_NAME = "GUARANTEED_RADIUS"
RADIUS_VALUE = 13


def _is_radius(node, aliases) -> bool:
    if isinstance(node, ast.Name):
        return node.id == RADIUS_NAME or node.id in aliases
    return isinstance(node, ast.Attribute) and node.attr == RADIUS_NAME


def _is_distance(node) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return name == "game_distance"
    return isinstance(node, ast.Attribute) and node.attr == "distance"


def _is_thirteen(node) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value == RADIUS_VALUE


class _Sites(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.found: list[tuple[str, int, str]] = []
        # Local names bound to the sure radius (``radius = destruction_use.GUARANTEED_RADIUS``),
        # per enclosing function.
        self.aliases: list[set[str]] = [set()]

    def _site(self, node, what: str) -> None:
        self.found.append((self.module, node.lineno, what))

    def visit_FunctionDef(self, node) -> None:
        self.aliases.append(set())
        self.generic_visit(node)
        self.aliases.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node) -> None:
        if _is_radius(node.value, set()):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.aliases[-1].add(target.id)
        self.generic_visit(node)

    def visit_Attribute(self, node) -> None:
        if (isinstance(node.value, ast.Name) and node.value.id == SCENE_MODULE
                and node.attr.startswith("_") and not node.attr.startswith("__")):
            self._site(node, f"reads destruction_use.{node.attr}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node) -> None:
        if (node.module or "").split(".")[-1] == SCENE_MODULE:
            for alias in node.names:
                if alias.name.startswith("_") or alias.name == RADIUS_NAME:
                    self._site(node, f"imports destruction_use.{alias.name}")
        self.generic_visit(node)

    def visit_Compare(self, node) -> None:
        aliases = set().union(*self.aliases)
        sides = [node.left, *node.comparators]
        if any(_is_radius(side, aliases) for side in sides):
            self._site(node, "compares against the sure radius")
        elif any(_is_thirteen(side) for side in sides) and any(_is_distance(side) for side in sides):
            self._site(node, "compares a distance against 13")
        self.generic_visit(node)


def sites(root: Path = POLICY_ROOT) -> list[tuple[str, int, str]]:
    """(module, line, what) of every read outside the scene module."""
    found = []
    for path in sorted(root.glob("*.py")):
        module = path.stem
        if module == SCENE_MODULE:
            continue
        visitor = _Sites(module)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found.extend(visitor.found)
    return found


def findings(root: Path = POLICY_ROOT) -> list[str]:
    return [f"{module}.py:{line} {what}: use destruction_use's public readers "
            f"(approach_gates, in_sure_radius, ...)" for module, line, what in sites(root)]


def main() -> int:
    lines = findings()
    for line in lines:
        print(line)
    print(f"destruction_scene_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
