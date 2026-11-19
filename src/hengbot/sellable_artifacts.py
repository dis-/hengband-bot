"""The owner's named artifacts: sold once 50F is reached, dropped on the town floor when no store buys.

Owner 2026-11-20, on the list of Home artifacts outside each slot's top ten
(C:\\hengband-backups\\pdca\\home-full-root-1119\\n1b-artifact-candidates.md), verbatim:
「今回は名指ししたリストを売る。名指ししたもののうち、固定アーティファクトは売却可能リストに入れ、
50F到達以降は売って良い」, and for the ones no store buys: 「アーティファクトは壊せないので捨てて
帰還すること」.

The list is data (``sellable_artifacts.json``, beside this module):

* ``fixed``: the 23 fixed artifacts (★) the owner named, by the game's fixed-artifact id
  (lib/edit/ArtifactDefinitions.jsonc ``id``; the board's ``artifact_id``).  A permanent list: any
  character whose deepest floor reached (fallback_depth_floor ``deepest_reached``) is 50F or deeper
  may let them go.
* ``one_time``: the 10 random artifacts (☆) of n1-b life-411, by their exact names (the display
  name before its ``{...}`` block, with its base kind and the Magic-Eater's class): sold this time
  only, at any depth.

``listed`` is what item_fate reads (the one gate): a listed artifact is not protected, ranks as
sellable gear (``gear_tier`` ANY) and its fate is ``SELL``, or ``DROP`` when no store buys it
(``unsellable``: the store's ``store_will_buy`` refuses a ware whose price is 0,
src/store/service-checker.cpp).  Artifacts cannot be destroyed: ``can_player_destroy_object``
returns false for every fixed or random artifact (src/object-hook/hook-expendable.cpp), and the
destroy command refuses it (src/cmd-item/cmd-destroy.cpp 「{}は破壊不可能だ。」).  So a ``DROP``
artifact is taken out of the Home (``next_home_take``; policy_home
``_bind_home_artifact_drop_withdrawal``), kept carried (``carried_for_drop``: the retention, so no
deposit, sale or destroy takes it back) and dropped on the town floor before the departure
(``town_drop_key``; owner 2026-11-20 correction 「ダンジョンに持って潜る必要はない。街の床に捨てて
ダンジョンに帰還すれば消える」: the town is not a saved floor, see ``town_drop_key``).  One carried
out of town anyway (a Recall that came first) is dropped on the next dungeon floor at the first
safe moment (``drop_key``, the safe-now layer beside junk_destroy_now).  The drop command takes one
item without a prompt (src/cmd-item/cmd-item.cpp ``do_cmd_drop``: the quantity is asked only of a
stack, and only an equipped cursed item is refused).  The cells it lands on (``drop_near`` puts it
on the player's empty floor grid or the best grid within d^2 <= 10, src/floor/floor-object.cpp)
are not loot for the rest of the floor visit (``dropped_here``, read by policy
``_floor_pile_is_junk`` and kept in ``_deferred_loot``), so nothing picks it up again.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from hengbot.item_identity import without_trailing_block, without_trailing_blocks

DATA = Path(__file__).with_name("sellable_artifacts.json")
# The policy attribute (floor_visit_memory.VISIT_MEMORIES): {"cells": frozenset of the cells the
# drops landed on, "pending": the posted drop awaiting its board, or None}.
MEMORY = "_artifact_drop_memory"
OWNER = "artifact-drop"
REASON = "artifact:drop-unsellable"
TOWN_REASON = "artifact:drop-unsellable-town"
RETENTION_BRANCH = "sellable-artifact:drop-on-floor"
# drop_near's search: d = dy^2 + dx^2 <= 10 around the player (src/floor/floor-object.cpp).
DROP_SPREAD = 3


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _fixed_entry(item: Any) -> dict | None:
    kind = [item.tval, item.sval]
    entries = [entry for entry in _data()["fixed"] if entry["base"] == kind]
    artifact_id = int(getattr(item, "artifact_id", 0) or 0)
    if artifact_id:
        return next((entry for entry in entries if entry["id"] == artifact_id), None)
    # A Home ware projected from a store page carries no id: the name (★ marks a fixed artifact
    # in the Japanese build, src/flavor/named-item-describer.cpp describe_artifact_mark_ja).
    name = without_trailing_block(item.name)
    if name.startswith("☆"):
        return None
    return next((entry for entry in entries
                 if entry["ja"] in name or entry["en"] in name), None)


def _one_time_entry(snapshot: Any, item: Any) -> dict | None:
    one_time = _data()["one_time"]
    if snapshot.player.class_id != one_time["class_id"]:
        return None
    name = without_trailing_blocks(item.name).strip()
    kind = [item.tval, item.sval]
    return next((entry for entry in one_time["names"]
                 if entry["base"] == kind and entry["name"] == name), None)


def listed(policy: Any, snapshot: Any, item: Any) -> bool:
    """A known artifact the owner's list lets go on this board (see the module)."""
    if not item.is_artifact or not item.known or snapshot is None:
        return False
    if _one_time_entry(snapshot, item) is not None:
        return True
    if _fixed_entry(item) is None:
        return False
    from hengbot.fallback_depth_floor import deepest_reached
    return deepest_reached(policy, snapshot) >= _data()["reached_depth"]


def unsellable(policy: Any, item: Any) -> bool:
    """No store buys it: its price is 0 (store_will_buy, src/store/service-checker.cpp)."""
    from hengbot.baseitem_knowledge import item_base_cost
    from hengbot.store_sale import has_positive_sale_value
    return not has_positive_sale_value(item, item_base_cost(item, policy._baseitem_costs))


def drop_target(policy: Any, snapshot: Any, item: Any) -> bool:
    """A listed artifact no store buys: dropped on a dungeon floor (owner 「捨てて帰還」)."""
    return listed(policy, snapshot, item) and unsellable(policy, item)


def carried_for_drop(policy: Any, snapshot: Any, item: Any) -> bool:
    """A carried ``drop_target``: the retention keeps it carried until it is dropped
    (policy_home ``_retention_reservation_baseline_detail``)."""
    return (str(getattr(item, "slot", "")).isalpha() and len(str(item.slot)) == 1
            and drop_target(policy, snapshot, item))


# --- Town: the Home take -------------------------------------------------------------------------

def home_takes(policy: Any, snapshot: Any) -> list:
    """The known Home stacks whose fate is ``DROP``, catalogue order.

    In town, with the Home listing current and no hostile in view (as the Magic-Eater's absorb
    takes, me_device_policy ``home_absorb_takes``)."""
    from hengbot import item_fate
    if not snapshot.in_town or not policy._home_knowledge_current:
        return []
    if policy._physical_hostiles(snapshot):
        return []
    deferred = getattr(policy, "_deferred_home_items", ())
    return [item for item in policy._home_knowledge_items[:policy._home_knowledge_valid_before]
            if item.count > 0 and item.is_artifact
            and item_fate.fate(policy, snapshot, item, item_fate.SHELF) == item_fate.DROP
            and policy._item_signature(item) not in deferred]


def next_home_take(policy: Any, snapshot: Any) -> Any:
    """The next Home stack to take out to drop, or None: the last shelf slot first (a take shifts
    only the later slots), when the pack's budget and its weight limit admit it."""
    from hengbot.town_pack_budget import home_take_fits
    takes = home_takes(policy, snapshot)
    item = takes[-1] if takes else None
    if (item is None or not home_take_fits(snapshot, item, item.count, policy=policy)
            or not policy._can_add_item_without_overweight(snapshot, item)):
        return None
    return item


# --- The drop: on the town floor before the departure (a carried one on a dungeon floor) --------

def _memory(policy: Any) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = {"cells": frozenset(), "pending": None}
        setattr(policy, MEMORY, memory)
    return memory


def dropped_here(policy: Any, snapshot: Any, position: Any) -> bool:
    """A cell an artifact was dropped on during this floor visit (the town's included): not loot."""
    memory = getattr(policy, MEMORY, None)
    return snapshot is not None and memory is not None and position in memory["cells"]


def _plain_floor(policy: Any, snapshot: Any, grid: Any) -> bool:
    """The player's grid takes the drop: a plain floor holding nothing, or only what was dropped
    on it (the next drop then lands beside it, drop_near); never a stair, a door, a dungeon or
    quest entrance, a store's or a building's entrance."""
    return bool(grid is not None and grid.known and grid.passable and not grid.wall
                and (grid.object_count == 0 or dropped_here(policy, snapshot, grid.position))
                and not grid.trap
                and not grid.has_down_stairs and not grid.has_up_stairs
                and not grid.is_door and not grid.has_entrance
                and not grid.has_quest_enter and not grid.has_quest_exit
                and grid.store_number < 0 and grid.building_type < 0
                and grid.building_special < 0)


def _counts_around(snapshot: Any, position: Any) -> dict:
    return {grid.position: grid.object_count for grid in snapshot.grids.values()
            if (grid.position.y - position.y) ** 2 + (grid.position.x - position.x) ** 2
            <= DROP_SPREAD ** 2 + 1}


def _town_quiet(policy: Any, snapshot: Any) -> bool:
    """The strict quiet of junk_destroy_now, read in town: no store page, no hostile in view, not
    just hit, no impairment, no flight."""
    from hengbot import safety_facts
    facts = safety_facts.of(policy, snapshot)
    return safety_facts.strict_quiet(facts._replace(in_town=False))


def _target(policy: Any, snapshot: Any) -> Any:
    memory = _memory(policy)
    if memory["pending"] is not None:
        return None
    item = next((each for each in snapshot.inventory
                 if drop_target(policy, snapshot, each)), None)
    if item is None:
        return None
    here = snapshot.grid_at(snapshot.player.position)
    return item if _plain_floor(policy, snapshot, here) else None


def _posted(policy: Any, snapshot: Any, item: Any, key: str | None, reason: str) -> str | None:
    if key is None:
        return None
    policy.last_reason = reason
    position = snapshot.player.position
    _memory(policy)["pending"] = {"position": position, "turn": snapshot.turn,
                                  "signature": policy._item_signature(item),
                                  "counts": _counts_around(snapshot, position)}
    return key


def town_drop_key(policy: Any, snapshot: Any) -> str | None:
    """Drop one carried ``drop_target`` on the town floor when it is quiet, or None.

    Owner 2026-11-20 (correction, verbatim): 「ダンジョンに持って潜る必要はない。街の床に捨てて
    ダンジョンに帰還すれば消える」.  The town is never a saved floor: the departure's Word of Recall
    leaves it without SAVE_FLOORS (world/world-movement-processor.cpp ``execute_recall`` sets no
    floor change mode; floor/floor-leaver.cpp ``leave_floor`` returns before ``save_floor`` without
    SAVE_FLOORS, and ``exe_leave_floor`` saves only ``in_saved_floor``, floor_id != 0, which the
    town's is not), and the next floor is generated anew (floor/floor-changer.cpp ``update_floor``
    -> ``generate_floor`` -> floor/floor-generator.cpp ``clear_cave``: ``o_list.clear()``), the
    town too on the next return (``wilderness_gen``).  What lies on the town floor is gone.
    Asked before the departure (ladder_objectives, above ``_town_special_key``)."""
    if not snapshot.in_town or snapshot.store is not None or not _town_quiet(policy, snapshot):
        return None
    item = _target(policy, snapshot)
    if item is None:
        return None
    return _posted(policy, snapshot, item,
                   policy._town_item_command_entry_key(snapshot, "drop", item, OWNER), TOWN_REASON)


def drop_key(policy: Any, snapshot: Any) -> str | None:
    """Drop one carried ``drop_target`` on a dungeon floor when it is safe, or None.

    The fallback for one carried out of town (a Recall that came before the town drop): never on a
    quest floor; only on the player's plain floor grid (empty, or holding only what was dropped);
    at the strict quiet of junk_destroy_now (no hostile in view, not just hit, no impairment)."""
    from hengbot import junk_destroy_now
    from hengbot.item_reservation import reserved_item_command
    if (snapshot.in_town or snapshot.dungeon_level <= 0 or snapshot.floor_key[2]
            or snapshot.on_open_wilderness or not junk_destroy_now.safe(policy, snapshot)):
        return None
    item = _target(policy, snapshot)
    if item is None:
        return None
    return _posted(policy, snapshot, item,
                   reserved_item_command(policy, snapshot, "drop", item, OWNER), REASON)


def observe(policy: Any, snapshot: Any) -> None:
    """Settle a posted drop on the next board and keep the dropped cells out of the loot."""
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    pending = memory["pending"]
    if pending is not None:
        carried = any(policy._item_signature(item) == pending["signature"]
                      for item in snapshot.inventory)
        if not carried:
            before = pending["counts"]
            landed = frozenset(position for position, count in
                               _counts_around(snapshot, pending["position"]).items()
                               if count > before.get(position, 0))
            memory["cells"] = memory["cells"] | (landed or frozenset({pending["position"]}))
            memory["pending"] = None
        elif snapshot.turn > pending["turn"]:
            # The drop did not happen (the key was not sent or the game refused it): asked again
            # at the next quiet moment.
            memory["pending"] = None
    if memory["cells"]:
        policy._deferred_loot.update(memory["cells"])
        policy._known_loot.difference_update(memory["cells"])
