#!/usr/bin/env python3
"""Who may wear or take off gear, and who may read or force-reset the loadout target.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E0): the gear decisions
were partly broken because twenty-odd places wear and take off gear outside the loadout search,
and seven files force the search to run again; no lint watched either.  This lint pins, per
module of ``src/hengbot``, how many places do each of these (read from the AST):

- ``wear-exit``: a call of the single wear/take-off exit or its executor
  (``_equipment_wield``, ``_equipment_takeoff``, ``_wield_weapon_key``, ``request_wield``,
  ``request_takeoff``);
- ``wear-command``: an item command composed with the literal kind ``"wield"`` / ``"takeoff"``
  (``checked_item_command``, ``reserved_item_command``, ``item_command``, ...) -- a wear key that
  bypasses the exit;
- ``target-read`` / ``target-write``: ``._equipment_optimization_preparation`` loaded / assigned
  (the search's stored result, the loadout target);
- ``search-reset``: ``._equipment_optimization_signature`` assigned (a forced re-search, and the
  search's own store);
- ``target-name``: either name as a string (``getattr``, a state dict key).

``ALLOWED`` is today's set (2026-11-22, main 7cc84c1382 plus E0's journal hooks).  A module or a
count above it is a new direct writer/reader and fails; a count below it fails too, so the pin
is lowered with the change that removed one (the later stages E2/E5 move these behind one
reader and one slot lease; each move lowers a pin here).

    python scripts/equipment_writer_lint.py          # exit 1 on a finding
    python scripts/equipment_writer_lint.py --print  # today's counts, as ALLOWED's literal
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"

WEAR_EXITS = frozenset({"_equipment_wield", "_equipment_takeoff", "_wield_weapon_key",
                        "request_wield", "request_takeoff"})
COMMAND_COMPOSERS = frozenset({"checked_item_command", "reserved_item_command", "item_command",
                               "_historical_item_command", "store_item_key"})
WEAR_KINDS = frozenset({"wield", "takeoff"})
TARGET = "_equipment_optimization_preparation"
SIGNATURE = "_equipment_optimization_signature"

ALLOWED: dict[str, dict[str, int]] = {
    "destination_band_floor": {"search-reset": 1, "target-name": 1},
    "equipment_capacity": {"search-reset": 1},
    "equipment_mutation": {"wear-command": 2},
    "ladder_objectives": {"wear-exit": 2},
    "me_powerful_activation": {"target-read": 1, "target-write": 1},
    "mining_loadout": {"target-read": 1, "wear-exit": 2},
    "policy": {"search-reset": 7, "target-read": 9, "target-write": 5, "wear-exit": 5},
    "policy_calibration": {"search-reset": 3},
    "policy_equipment": {"search-reset": 6, "target-read": 21, "target-write": 6, "wear-exit": 11},
    "policy_fundraising": {"wear-exit": 1},
    "policy_home": {"target-name": 1},
    "policy_identification": {"search-reset": 1, "target-write": 1},
    "policy_observation": {"search-reset": 1, "target-write": 1},
    "policy_opening": {"wear-exit": 1},
    "policy_quest": {"wear-exit": 3},
    "policy_shop": {"wear-exit": 3},
    "policy_state": {"target-name": 1},
    "policy_supply": {"wear-exit": 1},
    "policy_town": {"target-read": 3, "wear-exit": 1},
    "quest25_druj_gear": {"wear-exit": 3},
    "spare_gear": {"target-read": 1},
    "state_registry": {"target-name": 2},
    "zul_trip": {"wear-exit": 2},
}


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def analyze_source(source: str) -> Counter:
    """The counts of one module's source (see the module docstring for the categories)."""
    counts: Counter = Counter()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name in WEAR_EXITS:
                counts["wear-exit"] += 1
            elif name in COMMAND_COMPOSERS and any(
                isinstance(arg, ast.Constant) and arg.value in WEAR_KINDS
                for arg in node.args
            ):
                counts["wear-command"] += 1
        elif isinstance(node, ast.Attribute) and node.attr == TARGET:
            counts["target-write" if isinstance(node.ctx, ast.Store) else "target-read"] += 1
        elif isinstance(node, ast.Attribute) and node.attr == SIGNATURE:
            if isinstance(node.ctx, ast.Store):
                counts["search-reset"] += 1
        elif isinstance(node, ast.Constant) and node.value in (TARGET, SIGNATURE):
            counts["target-name"] += 1
    return counts


def repository_counts(root: Path = POLICY_ROOT) -> dict[str, Counter]:
    counts = {}
    for path in sorted(root.rglob("*.py")):
        found = analyze_source(path.read_text(encoding="utf-8"))
        if found:
            counts[path.relative_to(root).with_suffix("").as_posix().replace("/", ".")] = found
    return counts


def findings(counts: dict[str, Counter], allowed: dict[str, dict[str, int]] = ALLOWED) -> list[str]:
    out = []
    for module in sorted(set(counts) | set(allowed)):
        have, pinned = counts.get(module, Counter()), allowed.get(module, {})
        for category in sorted(set(have) | set(pinned)):
            seen, limit = have.get(category, 0), pinned.get(category, 0)
            if seen > limit:
                out.append(f"{module}: {category} {seen} > allowed {limit} -- a new direct "
                           "writer/reader of gear; go through the equipment exit, or raise the pin "
                           "with the review's consent")
            elif seen < limit:
                out.append(f"{module}: {category} {seen} < allowed {limit} -- lower the pin")
    return out


def main(argv: list[str]) -> int:
    counts = repository_counts()
    if "--print" in argv:
        for module, found in counts.items():
            print(f'    "{module}": {dict(sorted(found.items()))},')
        return 0
    problems = findings(counts)
    for problem in problems:
        print(f"equipment-writer-lint: {problem}")
    print(f"equipment-writer-lint: {len(problems)} finding(s)")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
