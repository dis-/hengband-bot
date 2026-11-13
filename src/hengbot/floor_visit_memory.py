"""The memories of one floor visit that the next visit of the same floor key must not read.

The floor key is (dungeon, level, quest): every visit of a depth has the same key, and every
Word of Recall lands on a level the game generates anew (spells-world.cpp: the recall's floor
change saves no floor to come back to).  The floor change (policy_observation ``_observe``)
already forgets the remembered map, the loot and most per-floor latches, and the modules with a
``forget_floor_visit`` are called there; the memories below were keyed by the floor key alone
and survived the town between two visits, so a fresh level read the earlier levels' facts.

n1-c life-207 (Magic-Eater Lv46, ガラスの城 60F, 2026-11-14 04:00-04:30, the owner's
「帰還の条件がおかしい気がする」): area_mapping's memory had gathered the *Destruction* circles of
sixteen and more earlier 60F levels, so each new 60F level read as destroyed around the player
from its first board: ``me-power:after-destruction:map-area`` was cast on arrival, the circles'
sure radius read as explored ground (stuck:wander, seek-secret-wall and search right after
arrival, then ``stuck:recall-escape``), and sealed_pocket's ``stuck:destroyed-circle-teleport``
read a Teleportation on arrival (04:26:08: it landed in the next fight and the dive returned).
The same root as summoner_wait's D46 (its own ``forget_floor_visit``).

One table: each row is the attribute, what makes the empty value it starts the visit with
(``None`` for an absent memory), and the owner module whose memory it is.  ``forget`` is
called on every floor change.  Not here: the destruction_use memory (its ``entitled_floor`` is
set again on every board while the means is held, before the floor change is observed), and the
Anaguma latches (the anaguma module's own work, being changed on another branch).
"""
from __future__ import annotations

VISIT_MEMORIES = (
    ("_area_mapping_memory", None, "area_mapping"),
    ("_destroyed_circle_teleport", None, "sealed_pocket"),
    ("_sealed_pocket_memory", None, "sealed_pocket"),
    ("_lit_floor_memory", None, "dark_recall"),
    ("_hazard_entry", None, "damaging_ground"),
    ("_esp_tier_hold", None, "esp_tier_hold"),
    ("_loot_frontier_tried", None, "loot_frontier"),
    ("_loot_unreachable_note", None, "loot_frontier"),
    ("_hunt_progress_floor", None, "policy_combat._hunt_step"),
    ("_summoner_counter_targets", frozenset, "policy_combat"),
    ("_locked_doors", set, "locked_doors"),
    ("_stuck_doors", set, "locked_doors"),
)


def forget(policy) -> None:
    """A new floor visit: none of the earlier visits' memories of the table."""
    for name, empty, _owner in VISIT_MEMORIES:
        setattr(policy, name, None if empty is None else empty())
