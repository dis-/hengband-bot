"""The safe-now layer of the dungeon ladder (dungeon_ladder.LADDER, layer "safe-now").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the combat layer
(ladder_combat), above the objectives, rest, descent and idle.  The survival gate (starvation
safety), the blind board's unseen blow and wait for sight, the mana food's loot, the floor
powers and mapping, the quest target's detection, the Magic-Eater's absorb, the junk to
destroy now and the consumables to use now.  The rungs are asked top-down and the first key
returned wins, as in ``_decide``; ``PASS`` hands the decision on to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.
"""
from __future__ import annotations

from hengbot import area_mapping, consumable_policy, junk_destroy_now, magic_eater, me_powers, quest_target_search, status_cure
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, strategic_hostiles, physical_hostiles):
    """The safe-now layer's answer, or PASS when none of its rungs acts."""
    # 2s. Survival gate (R1): starvation safety is mode- and objective-
    # independent. It runs ABOVE fundraising/quests/descent because every
    # one of those returns keys on its own and would otherwise starve this
    # step of decisions — which is exactly how a mining run walked a
    # character to food_state "weak" with an empty pack (2026-07-17).
    survival = policy._town_producer_entry("_survival_gate_key#2", lambda: policy._survival_gate_key(snapshot, physical_hostiles))
    if survival is not None:
        return survival
    # Owner 2026-11-07 「分からない隣のマスにも攻撃する」: a blind board's unseen
    # melee blow is struck back before the floor work (status_cure).
    blow = status_cure.dungeon_unseen_blow_key(policy, snapshot, physical_hostiles)
    if blow is not None:
        return blow
    # Owner 2026-11-07 「敵がいなくなったら目が見えるまで休む。」: blind with no
    # attacker left, the floor work below waits for sight (status_cure).
    sight = status_cure.dungeon_wait_for_sight_key(policy, snapshot)
    if sight is not None:
        return sight

    mana_food_loot = policy._town_producer_entry("_mana_food_loot_key", lambda: policy._mana_food_loot_key(
        snapshot, strategic_hostiles
    ))
    if mana_food_loot is not None:
        return mana_food_loot

    # Class 16's absorbed detection/light powers, after the survival rungs (me_powers).
    floor_power = me_powers.power_key(policy, snapshot, me_powers.FLOOR)
    if floor_power is not None:
        return floor_power
    floor_map = area_mapping.after_destruction_key(policy, snapshot)
    if floor_map is not None:
        return floor_map
    # A Scroll of Magic Mapping is read when picked up, above the junk rung (area_mapping).
    picked_map = area_mapping.picked_up_scroll_key(policy, snapshot)
    if picked_map is not None:
        return picked_map
    # A carried device that can show a random quest's unseen target (quest_target_search).
    target_search = quest_target_search.detection_key(policy, snapshot)
    if target_search is not None:
        return target_search
    # Class 16's device policy table: an absorb_now device is absorbed on
    # the spot when safe (me_device_policy, owner 2026-10-31).
    floor_absorb = magic_eater.absorb_key(policy, snapshot, physical_hostiles)
    if floor_absorb is not None:
        return floor_absorb
    # Carried junk is destroyed on the first safe decision, not at the
    # return (owner 2026-11-02, junk_destroy_now).
    junk_now = policy._town_producer_entry("junk_destroy_now.destroy_now_key", lambda: junk_destroy_now.destroy_now_key(policy, snapshot), board=snapshot)
    if junk_now is not None:
        return junk_now
    # A 「拾って使う」 scroll of the owner's table is read at the same safe
    # point (consumable_policy, owner 2026-11-02).
    use_now = policy._town_producer_entry("consumable_policy.use_now_key", lambda: consumable_policy.use_now_key(policy, snapshot), board=snapshot)
    if use_now is not None:
        return use_now
    return PASS
