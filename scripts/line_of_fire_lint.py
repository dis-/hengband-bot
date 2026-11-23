"""The line-of-fire readings outside their one module (hengbot.line_of_fire).

Whole-bot maintainability review 2026-11-17 (N4 / 5(a)-7): the line of fire was read through
seven names in two places, the counting reading (line_of_fire, an unknown grid a wall) and the
danger reading (policy ``_monster_in_line_of_fire``, an awake monster's unknown grids open), each
calling itself the only one.  Every reading now lives in line_of_fire under its own name
(``counting``, ``danger``, ``projectable``, ``straight_line``, ``player_projectable``, ``player_reaches``,
``fire_reaches``), and ``line_of_fire.READERS`` lists which caller reads which and why.

Findings:

- a call of a reading that ``READERS`` does not list (module, function, reading), and a row of
  ``READERS`` no call has (stale);
- a use or a definition of a retired name (the policy methods ``_monster_in_line_of_fire``,
  ``_has_line_of_fire``, ``_may_project``, ``_player_may_project``, ``_fire_reaches``;
  ``line_of_fire.in_fire`` / ``line_of_fire.reaches``), in src or tests;
- a line of fire computed outside line_of_fire: a ``projection_path`` whose blocker reads the
  monster's projection blocker (``_may_block_projection``), or the player's
  (``_stops_player_projection``) without ``through=True`` (a beam, me_powers, is not a line
  of fire to a target);
- a ``projection_path`` outside line_of_fire given a stop of its own (any blocker that does
  not read ``_may_block_projection`` / ``_stops_player_projection``) that ``READERS`` does not
  list under the reading ``own_stop``.  Maintainability review 2026-11-18 (S7-3 / 6(a)-8):
  the glass bug class (ea26e01d4a, n1-c life-216 Glass castle 60F) was a path that stopped on
  a known grid without LOS instead of one without PROJECTION, written by hand and passed to
  ``projection_path``; read ``line_of_fire.player_path`` instead, or list the call with why.

    python scripts/line_of_fire_lint.py          # exit 1 on a finding
    python scripts/line_of_fire_lint.py --print  # the (module, function, reading) of every call
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
TEST_ROOT = ROOT / "tests"
MODULE = "line_of_fire"
READINGS = frozenset({"counting", "counting_reaches", "danger", "projectable", "straight_line",
                      "player_projectable", "player_reaches", "cell_exposed", "player_path", "fire_reaches"})
# counting_reaches is the counting reading from a cell; the table names ``counting`` for it.
TABLE_NAME = {"counting_reaches": "counting"}
# A projection_path given a stop of its own outside line_of_fire: READERS lists each with why.
OWN_STOP = "own_stop"
# The blockers that are the bot's projection readings (policy_combat): not a stop of one's own.
PROJECTION_BLOCKERS = frozenset({"_may_block_projection", "_stops_player_projection"})
RETIRED_METHODS = frozenset({"_monster_in_line_of_fire", "_has_line_of_fire", "_may_project",
                             "_player_may_project", "_fire_reaches"})
RETIRED_MODULE_NAMES = frozenset({"in_fire", "reaches"})


def readers_table(root: Path = POLICY_ROOT) -> dict:
    """``line_of_fire.READERS`` read from the source (no import: the lint runs without the bot)."""
    tree = ast.parse((root / f"{MODULE}.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "READERS" for target in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{MODULE}.py has no READERS table")


class _Calls(ast.NodeVisitor):
    def __init__(self, module: str, own: bool) -> None:
        self.module = module
        self.own = own  # the line_of_fire module itself: its readings are called by bare name
        self.stack: list[str] = []
        self.calls: list[tuple[str, str, str, int]] = []
        self.retired: list[tuple[str, int, str]] = []
        self.computed: list[tuple[str, int, str]] = []

    def _scope(self, node, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node) -> None:
        if node.name in RETIRED_METHODS:
            self.retired.append((self.module, node.lineno, f"def {node.name}"))
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _function(self) -> str:
        return self.stack[-1] if self.stack else "<module>"

    def visit_Attribute(self, node) -> None:
        if node.attr in RETIRED_METHODS:
            self.retired.append((self.module, node.lineno, node.attr))
        if (isinstance(node.value, ast.Name) and node.value.id == MODULE
                and node.attr in RETIRED_MODULE_NAMES):
            self.retired.append((self.module, node.lineno, f"{MODULE}.{node.attr}"))
        self.generic_visit(node)

    def visit_Call(self, node) -> None:
        func = node.func
        name = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                and func.value.id == MODULE and func.attr in READINGS:
            name = func.attr
        elif self.own and isinstance(func, ast.Name) and func.id in READINGS:
            name = func.id
        if name is not None:
            self.calls.append((self.module, self._function(), TABLE_NAME.get(name, name), node.lineno))
        if (isinstance(func, ast.Name) and func.id == "projection_path") or (
                isinstance(func, ast.Attribute) and func.attr == "projection_path"):
            self._projection(node)
        self.generic_visit(node)

    def _projection(self, node) -> None:
        if self.own:
            return
        names = {sub.attr for arg in [*node.args, *(k.value for k in node.keywords)]
                 for sub in ast.walk(arg) if isinstance(sub, ast.Attribute)}
        through = any(k.arg == "through" and isinstance(k.value, ast.Constant) and k.value.value
                      for k in node.keywords)
        if "_may_block_projection" in names or ("_stops_player_projection" in names and not through):
            self.computed.append((self.module, node.lineno, "projection_path"))
        elif not names & PROJECTION_BLOCKERS:
            # A stop of its own (a lambda, a local function, a name): a reading READERS lists.
            self.calls.append((self.module, self._function(), OWN_STOP, node.lineno))


def scan(root: Path = POLICY_ROOT, tests: Path = TEST_ROOT):
    calls, retired, computed = [], [], []
    for path in sorted(root.glob("*.py")):
        visitor = _Calls(path.stem, own=path.stem == MODULE)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        calls += visitor.calls
        retired += visitor.retired
        computed += visitor.computed
    for path in sorted(tests.glob("*.py")) if tests.exists() else ():
        visitor = _Calls("tests/" + path.stem, own=False)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        retired += visitor.retired
    return calls, retired, computed


def findings(root: Path = POLICY_ROOT, tests: Path = TEST_ROOT) -> list[str]:
    calls, retired, computed = scan(root, tests)
    table = readers_table(root)
    lines = []
    seen = {(module, function, reading) for module, function, reading, _line in calls}
    for module, function, reading, line in calls:
        if (module, function, reading) in table:
            continue
        if reading == OWN_STOP:
            lines.append(f"{module}.py:{line} {function} passes a stop of its own to projection_path "
                         f"(the glass class: a stop on LOS, not PROJECTION): read "
                         f"line_of_fire.player_path, or add ({module!r}, {function!r}, {OWN_STOP!r}) "
                         f"to line_of_fire.READERS with why")
        else:
            lines.append(f"{module}.py:{line} {function} reads line_of_fire.{reading}, not in "
                         f"line_of_fire.READERS: add the row with why it reads that one")
    for key in sorted(set(table) - seen):
        lines.append(f"line_of_fire.READERS row {key} has no call: remove it")
    for module, line, name in retired:
        lines.append(f"{module}.py:{line} uses the retired {name}: read line_of_fire by name")
    for module, line, name in computed:
        lines.append(f"{module}.py:{line} computes a line of fire ({name}) outside line_of_fire")
    return sorted(set(lines))


def main(argv: list[str]) -> int:
    if "--print" in argv:
        calls, _retired, _computed = scan()
        for key in sorted({(m, f, r) for m, f, r, _line in calls}):
            print(key)
        return 0
    lines = findings()
    for line in lines:
        print(line)
    print(f"line_of_fire_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
