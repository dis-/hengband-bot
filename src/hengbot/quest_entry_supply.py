"""The supplies a fixed quest's floor was entered with, and whether the quest has spent them.

2026-11-27 (supervisor, under the owner's 2026-11-26 permission to change in-game choices; it
refines the owner's 2026-11-16 answer A 「隘路で迎え撃ち尽きる前に帰還」): n1-c life-223 (Zombie
Magic-Eater CL42, HP 810) took Quest 25 with the two Potions of Healing its row asked
(``required_force.over_match`` lowers 5 to 2, quest_force_rows), fought the first two phases at full
HP without drinking one, and at turn 4303902, the first board of phase 2, read Word of Recall to
restock (quest25_battle_hall ``_restock_recall``: Healing potions ``<= HEALING_FLOOR`` 2) -- the
quest failed and its Amulet of Telepathy was lost.  Two places answered "are there enough Healing
potions for Q25" and disagreed (MAINTAINABILITY.md 3).

The rule: an in-quest supply floor counts only what this quest attempt has spent.  A count at or
under the floor leaves only when it is below the count the floor was entered with
(``spent_to_floor``); entering with N and still holding N never leaves.

The entry count is the count of the quest floor's first board (``observe``, every decision, before
the plans): ``STATE`` holds (floor key, {supply: count}).  A restart keeps it on the same floor
(quest_plan_record ``CARRIED``); with nothing recorded (a record that did not load), the first
count this process observes on the floor stands for it.
"""

from __future__ import annotations

from typing import Any

STATE = "_quest_entry_supplies"   # (floor key, {supply name: count}) of the quest floor's first board

HEALING = "healing"


def _counts(policy: Any, snapshot: Any) -> dict:
    from hengbot import quest_plan_base   # import cycle: the plans read this module

    return {HEALING: quest_plan_base.healing_potion_count(policy, snapshot)}


def _on_quest_floor(snapshot: Any) -> bool:
    quest = snapshot.quests.get(snapshot.floor_key[2]) if snapshot.floor_key[2] else None
    return quest is not None and bool(quest.fixed) and not snapshot.in_town


def observe(policy: Any, snapshot: Any) -> None:
    """Every decision: on a fixed quest's floor not yet recorded, its counts are the entry's."""
    if not _on_quest_floor(snapshot):
        return
    held = getattr(policy, STATE, None)
    if held is not None and tuple(held[0]) == tuple(snapshot.floor_key):
        return
    setattr(policy, STATE, (tuple(snapshot.floor_key), _counts(policy, snapshot)))


def entered_with(policy: Any, snapshot: Any, name: str) -> int:
    """The count of ``name`` this quest floor was entered with (``observe``; module docstring)."""
    observe(policy, snapshot)
    held = getattr(policy, STATE, None)
    if held is None or tuple(held[0]) != tuple(snapshot.floor_key) or name not in held[1]:
        return _counts(policy, snapshot)[name]
    return int(held[1][name])


def spent_to_floor(policy: Any, snapshot: Any, name: str, count: int, floor: int) -> bool:
    """``count`` of ``name`` is at or under ``floor`` and below the count the floor was entered with:
    the quest spent its way down to the floor (module docstring)."""
    return count <= floor and count < entered_with(policy, snapshot, name)
