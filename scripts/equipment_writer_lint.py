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

Stage E2 (2026-11-22) put the target behind ``equipment_target``: the four raw categories above
are allowed in that module only (and the registry's names), so a direct read of the old
internals elsewhere fails.  The writers stay at their sites through named functions, pinned here
so stage E3 sees every one:

- ``target-store-call``: a call of ``equipment_target.TARGET_WRITERS`` (``init_loadout_target``,
  ``record_loadout_search``, ``replace_loadout_target``, ``set_unsearched_loadout_target``,
  ``clear_loadout_target``);
- ``search-reset-call``: a call of ``equipment_target.SEARCH_RESETTERS``
  (``invalidate_loadout_search``, a forced re-search, and ``forget_loadout_search_in_state``).

E2 also put the character's abilities behind ``ability_sources`` (worn / pack / Home):

- ``ability-read``: ``player.abilities`` / ``player.ability_sources`` (on ``player`` or
  ``<x>.player``) read;
- ``ability-table``: the ability -> flag table ``RESIST_FLAG_BY_ABILITY`` read (an import is
  not a read).

Both are allowed in ``ability_sources`` only (``model`` builds the board).

Stage E3 (2026-11-22) added the visit's fixed target (``fix_visit_target``, a target writer) and
the Q7 take-off of a worn banned piece (``set_unsearched_loadout_target``): policy_equipment's
``target-store-call`` 6 -> 8.  Stage E4 (2026-11-22) folded destination_band_floor's engage (a forced re-search) into the
search's own destination floor: its ``search-reset-call`` 1 -> 0.

Stage E5 (2026-11-22, owner Q6) put every temporary swap's end behind ``slot_lending``: the
return to the target loadout's piece goes through its two exits (``wield_back``, ``take_back``),
so the swap ends of mining_loadout (2), policy_shop (3) and policy's breakout restore (1) moved
there (``slot_lending`` wear-exit 2).

``ALLOWED`` is today's set (2026-11-22, E2 on main 23febce5a; E3 as above).  A module or a
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
sys.path.insert(0, str(ROOT / "src"))
from hengbot.equipment_target import SEARCH_RESETTERS as SEARCH_RESET_CALLS  # noqa: E402
from hengbot.equipment_target import TARGET_WRITERS as TARGET_STORE_CALLS  # noqa: E402
TARGET_MODULE = "equipment_target"
ABILITY_ATTRIBUTES = frozenset({"abilities", "ability_sources"})
ABILITY_TABLE = "RESIST_FLAG_BY_ABILITY"
# The categories only their owner module may have (the old internals); a reader elsewhere goes
# through equipment_target / ability_sources.
OWNED_CATEGORIES = {
    "target-read": TARGET_MODULE, "target-write": TARGET_MODULE,
    "search-reset": TARGET_MODULE, "target-name": TARGET_MODULE,
    "ability-read": "ability_sources", "ability-table": "ability_sources",
}

ALLOWED: dict[str, dict[str, int]] = {
    "ability_sources": {"ability-read": 3, "ability-table": 5},
    "equipment_capacity": {"search-reset-call": 1},
    "equipment_mutation": {"wear-command": 2},
    "equipment_target": {"search-reset": 5, "target-name": 2, "target-write": 5},
    "ladder_objectives": {"wear-exit": 2},
    "me_powerful_activation": {"target-store-call": 1},
    "policy": {"search-reset-call": 2, "target-store-call": 5, "wear-exit": 4},
    "policy_calibration": {"search-reset-call": 3},
    "policy_equipment": {"search-reset-call": 1, "target-store-call": 8, "wear-exit": 11},
    "policy_fundraising": {"wear-exit": 1},
    "policy_identification": {"target-store-call": 1},
    "policy_observation": {"target-store-call": 1},
    "policy_opening": {"wear-exit": 1},
    "policy_quest": {"wear-exit": 3},
    "policy_state": {"search-reset-call": 1},
    "policy_supply": {"wear-exit": 1},
    "policy_town": {"wear-exit": 1},
    "quest25_druj_gear": {"wear-exit": 3},
    "slot_lending": {"wear-exit": 2},
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


def _is_player(node: ast.AST) -> bool:
    return ((isinstance(node, ast.Name) and node.id == "player")
            or (isinstance(node, ast.Attribute) and node.attr == "player"))


def _target_module_call(call: ast.Call) -> str | None:
    """The function name of an ``equipment_target.<name>(...)`` call."""
    func = call.func
    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == TARGET_MODULE):
        return func.attr
    return None


def analyze_source(source: str) -> Counter:
    """The counts of one module's source (see the module docstring for the categories)."""
    counts: Counter = Counter()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            target_call = _target_module_call(node)
            if target_call in TARGET_STORE_CALLS:
                counts["target-store-call"] += 1
            elif target_call in SEARCH_RESET_CALLS:
                counts["search-reset-call"] += 1
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
        if (isinstance(node, ast.Attribute) and node.attr in ABILITY_ATTRIBUTES
                and isinstance(node.ctx, ast.Load) and _is_player(node.value)):
            counts["ability-read"] += 1
        elif ((isinstance(node, ast.Name) and node.id == ABILITY_TABLE
               and isinstance(node.ctx, ast.Load))
              or (isinstance(node, ast.Attribute) and node.attr == ABILITY_TABLE)):
            counts["ability-table"] += 1
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
            owner = OWNED_CATEGORIES.get(category)
            if seen > limit and owner is not None and module != owner:
                out.append(f"{module}: {category} {seen} > allowed {limit} -- a direct read of "
                           f"the old internals; go through {owner}")
            elif seen > limit:
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
