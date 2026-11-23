"""The floor plans' state against its restart record (hengbot.quest_plan_record).

Whole-bot maintainability review 2026-11-23 K1 (b)-4, owner 2026-11-23 「再起動でクエストの作戦の状態を
「保存して続きから始める」（保存した階と今の階が違えば捨てる）」: a plan's floor state that the restart
record does not name is lost on a restart, unnoticed.  This lint fails on

- a plan state of the registry (hengbot.state_registry) that is neither carried
  (``quest_plan_record.CARRIED``) nor declared not carried with its reason (``NOT_CARRIED``): a row
  owned by a plan module (``PLAN_MODULE``), a quest floor row of any module (``lifetime`` floor and
  a quest name, ``QUEST_NAME``), a generic quest strategy row (``_quest_strategy_``);
- a name of those two tables that is no registry row, or is in both;
- a navigator field left out (``NAVIGATOR_NOT_CARRIED``) that the navigator does not have, or whose
  owner module (the record that carries it) does not exist;
- a plan module that keeps state outside the policy: a ``global`` statement, or a module-level
  container a function changes (a method that changes it, an item assigned or deleted) that is not
  a declared memo of a pure function (``DERIVED``) -- the plan's state lives on the policy, where
  the registry and this record see it;
- the record not wired: the ``choose_key`` exit's ``quest_plan_record.record``, the first
  observation's ``quest_plan_record.restore``, the CLI's ``_quest_plan_record_path``.

    python scripts/quest_plan_record_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
sys.path.insert(0, str(ROOT / "src"))

# The modules of a floor plan: the fixed-quest plans and their parts, Q2/Q34's, the 99F/100F battle.
PLAN_MODULE = re.compile(r"(quest|q\d+_|angband_finale_battle|plan_)")
QUEST_NAME = re.compile(r"quest|_q\d+_|finale_battle")
STRATEGY_PREFIX = "_quest_strategy_"
MUTATORS = frozenset({"append", "add", "update", "setdefault", "pop", "popitem", "clear", "extend",
                      "insert", "remove", "discard", "appendleft", "extendleft", "sort", "reverse"})
CONTAINER_CALLS = frozenset({"dict", "list", "set", "defaultdict", "Counter", "deque", "OrderedDict"})
# The module-level containers of the plan modules that are no state: memos of a pure function of
# their key (the same key gives the same value on every board and in every process).
DERIVED = {
    "quest25_plan._PARSED": "the parsed plan values of a strategy's raw table (keyed by the table)",
    "quest_detect_remaining._COVERS": "the detection cover of a terrain and a radius",
    "quest_find_exit._TERRAINS": "the battlefield terrain with the opened cells drawn as water",
    "quest_find_exit._EXPOSURES": "the exposure map of a terrain and its casters",
    "quest_room_sweep._EXPOSURES": "the exposure map of a terrain and its casters",
}
WIRING = (
    ("policy.py", "quest_plan_record.record(self, snapshot)"),
    ("policy_observation.py", "quest_plan_record.restore(self, snapshot)"),
    ("cli.py", "policy._quest_plan_record_path"),
)


def plan_states(registry) -> set:
    return {row.name for row in registry
            if row.lifetime != "decision" and (
                PLAN_MODULE.match(row.owner)
                or (row.lifetime == "floor" and QUEST_NAME.search(row.name))
                or row.name.startswith(STRATEGY_PREFIX))}


def _module_containers(tree) -> set:
    names = set()
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        container = isinstance(value, (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp,
                                       ast.SetComp)) or (
            isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id in CONTAINER_CALLS)
        if container:
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def module_state(path: Path) -> list:
    """The findings of a plan module keeping state outside the policy."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    containers = {name for name in _module_containers(tree) if f"{path.stem}.{name}" not in DERIVED}
    found = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Global):
                found.append(f"{path.name}:{node.lineno}: global {', '.join(node.names)}")
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr in MUTATORS and isinstance(node.func.value, ast.Name)
                  and node.func.value.id in containers):
                found.append(f"{path.name}:{node.lineno}: the module's {node.func.value.id} "
                             f"changed ({node.func.attr})")
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
                targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
                for target in targets:
                    if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                            and target.value.id in containers):
                        found.append(f"{path.name}:{node.lineno}: the module's {target.value.id} "
                                     f"item changed")
    return found


def findings(root: Path = POLICY_ROOT) -> list:
    from hengbot import quest_plan_record as record
    from hengbot.quest_navigator import QuestFloorNavigator
    from hengbot.state_registry import REGISTRY

    found = []
    rows = {row.name for row in REGISTRY}
    carried, not_carried = set(record.CARRIED), set(record.NOT_CARRIED)
    if len(carried) != len(record.CARRIED):
        found.append("CARRIED names a state twice")
    for name in sorted(carried & not_carried):
        found.append(f"{name}: both carried and not carried")
    for name in sorted((carried | not_carried) - rows):
        found.append(f"{name}: named by quest_plan_record but no state_registry row")
    for reason_name, reason in record.NOT_CARRIED.items():
        if not str(reason).strip():
            found.append(f"{reason_name}: not carried without a reason")
    for name in sorted(plan_states(REGISTRY) - carried - not_carried):
        found.append(f"{name}: a plan state neither carried nor declared not carried "
                     "(quest_plan_record.CARRIED / NOT_CARRIED)")
    navigator_names = set(vars(QuestFloorNavigator)) | set(
        getattr(QuestFloorNavigator, "__dataclass_fields__", {}))
    for name, (owner, _empty) in record.NAVIGATOR_NOT_CARRIED.items():
        if name not in navigator_names:
            found.append(f"NAVIGATOR_NOT_CARRIED {name}: QuestFloorNavigator has no such field")
        if not (root / f"{owner}.py").exists():
            found.append(f"NAVIGATOR_NOT_CARRIED {name}: no module {owner}")
    for path in sorted(root.glob("*.py")):
        if PLAN_MODULE.match(path.stem):
            found.extend(module_state(path))
    for file_name, call in WIRING:
        if call not in (root / file_name).read_text(encoding="utf-8"):
            found.append(f"{file_name}: the record is not wired ({call})")
    return found


def main() -> int:
    found = findings()
    for line in found:
        print(line)
    print(f"quest_plan_record_lint: {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
