"""The anti-teleport piece Q25 carries in for the hand druj only (phase7_druj).

Owner 2026-11-06 「反テレポート付きで他のデメリットがない装備がもしあれば、持ち込んでこの戦闘でのみ
使用する。」: the druj's Teleport Away goes through teleport_player_aux with TELEPORT_PASSIVE, which a
worn NO_TELE stops (spells-teleport.cpp, mspell-floor.cpp).  The data is the profile's
``consumable_plan.optional_carry_gear: {"anti_teleport": 1}``.

 * ``qualifies``: a known, uncursed piece of armour or jewellery with NO_TELE and no other drawback:
   none of the flags the equipment optimizer forbids for exploration besides NO_TELE
   (equipment_optimizer.FORBIDDEN_EXPLORATION_FLAGS) and no negative pval, to-hit, to-dam or
   to-AC.  A melee weapon is left out: the town's own rule sells a carried NO_TELE weapon
   (policy_shop ``shop:sell-no-teleport-weapon``) and takes one off the hand.
 * ``slot_for``: the slot it goes in, and only where taking off what is there loses no ability
   the quest requires (``required_force.resists`` with its ``resist_alternatives``, e.g. the
   see-invisible requirement): an ability that only the displaced piece gives, and that the
   piece does not give itself, is lost.
 * Town: ``home_piece`` is what quest_optional_carry takes from Home while Q25 is prepared;
   ``kept`` keeps a carried one out of the spare-gear deposit (spare_gear.released).
 * Dungeon (quest25_battle's druj phase): ``wear_key`` puts it on, remembering what it
   displaced; ``restore_key`` puts that back once the druj is dead.  Both go through the
   equipment mutation the rest of the bot wields with (policy._equipment_wield).
"""

from __future__ import annotations

from hengbot.equipment_optimizer import FORBIDDEN_EXPLORATION_FLAGS
from hengbot.model import (
    TVAL_AMULET, TVAL_BOOTS, TVAL_CLOAK, TVAL_CROWN, TVAL_DRAG_ARMOR, TVAL_GLOVES, TVAL_HARD_ARMOR,
    TVAL_HELM, TVAL_RING, TVAL_SHIELD, TVAL_SOFT_ARMOR,
)
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, RESIST_FLAG_BY_ABILITY

TR_NO_TELE = 68
GEAR_NAME = "anti_teleport"
WEAR_GOAL = "quest25-druj-anti-teleport"
RESTORE_GOAL = "quest25-druj-restore"
SLOTS_BY_TVAL = {
    TVAL_BOOTS: ("feet",), TVAL_GLOVES: ("arms",), TVAL_HELM: ("head",), TVAL_CROWN: ("head",),
    TVAL_SHIELD: ("sub_hand",), TVAL_CLOAK: ("outer",), TVAL_SOFT_ARMOR: ("body",),
    TVAL_HARD_ARMOR: ("body",), TVAL_DRAG_ARMOR: ("body",), TVAL_AMULET: ("neck",),
    TVAL_RING: ("main_ring", "sub_ring"),
}
# Ability name -> the TR flag a worn piece gives it by (the ESP alternatives included).
_ABILITY_FLAG = {**{name: flag for name, flag in RESIST_FLAG_BY_ABILITY.items() if flag >= 0},
                 "esp_undead": 105, "esp_evil": 112}


def wanted(profile) -> bool:
    return bool(profile is not None
                and profile.consumable_plan.get("optional_carry_gear", {}).get(GEAR_NAME))


def qualifies(item) -> bool:
    """「反テレポート付きで他のデメリットがない装備」."""
    return (item.is_equipment and item.tval in SLOTS_BY_TVAL and item.known
            and not item.is_cursed and TR_NO_TELE in item.known_flags
            and not (set(item.known_flags) & (FORBIDDEN_EXPLORATION_FLAGS - {TR_NO_TELE}))
            and min(item.pval, item.to_h, item.to_d, item.to_a) >= 0)


def _required(policy, force) -> list[tuple[str, ...]]:
    """Each required ability with its alternatives (any one of a group is enough)."""
    groups = []
    for name in force.get("resists", ()):
        resolved = policy._profile_resistance_name(str(name))
        groups.append((resolved, *force.get("resist_alternatives", {}).get(resolved, ())))
    return groups


def _has_after(snapshot, ability: str, removed, added) -> bool:
    flag = _ABILITY_FLAG.get(ability)
    sources = snapshot.player.ability_sources.get(ability, frozenset())
    if flag is None:
        return ability in snapshot.player.abilities
    if added is not None and flag in added.known_flags:
        return True
    if sources - {"equipment"}:
        return True       # permanent or temporary: no piece gives it
    return any(flag in worn.known_flags for worn in snapshot.equipment if worn is not removed)


def slot_for(policy, snapshot, force, item) -> str | None:
    """The slot the piece goes in losing no required ability the character has now, else None."""
    held = [group for group in _required(policy, force)
            if any(_has_after(snapshot, ability, None, None) for ability in group)]
    for slot in SLOTS_BY_TVAL.get(item.tval, ()):
        displaced = next((worn for worn in snapshot.equipment if worn.slot == slot), None)
        if all(any(_has_after(snapshot, ability, displaced, item) for ability in group)
               for group in held):
            return slot
    return None


def carried_piece(snapshot):
    return next((item for item in snapshot.inventory if qualifies(item)), None)


def worn_piece(snapshot):
    return next((item for item in snapshot.equipment if qualifies(item)), None)


def home_piece(policy, snapshot, profile):
    """The Home piece to take in for Q25, when none is carried or worn."""
    if not wanted(profile) or carried_piece(snapshot) or worn_piece(snapshot):
        return None
    if not policy._home_knowledge_current:
        return None
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    return next((item for index, item in enumerate(policy._home_knowledge_items)
                 if index < policy._home_knowledge_valid_before and qualifies(item)
                 and policy._item_signature(item) not in policy._deferred_home_items
                 and slot_for(policy, snapshot, force, item) is not None), None)


def kept(policy, snapshot, item) -> bool:
    """A carried piece stays out of the spare-gear deposit while Q25 is prepared or taken."""
    if snapshot is None or not qualifies(item):
        return False
    profile = (policy._carry_procurement_strategy(snapshot, cache_fixed_quest_head=False)
               or policy._quest_strategy_for_errand_or_floor(snapshot))
    return wanted(profile)


def wear_key(policy, snapshot, profile, memory) -> str | None:
    """Put the carried piece on; remember the piece it displaced (``memory.displaced``)."""
    if not wanted(profile) or worn_piece(snapshot) is not None:
        return None
    item = carried_piece(snapshot)
    if item is None:
        return None
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    slot = slot_for(policy, snapshot, force, item)
    if slot is None:
        return None
    displaced = next((worn for worn in snapshot.equipment if worn.slot == slot), None)
    key = policy._equipment_wield(snapshot, WEAR_GOAL, item, slot, quest_contract_exempt=True)
    if key is not None:
        memory.displaced = (slot, None if displaced is None else policy._item_signature(displaced))
        policy.last_reason = f"quest25:{WEAR_GOAL}"
    return key


def restore_key(policy, snapshot, memory) -> str | None:
    """Once the druj is dead: the displaced piece back on (「この戦闘でのみ使用」)."""
    if memory.displaced is None:
        return None
    slot, signature = memory.displaced
    worn = next((item for item in snapshot.equipment if item.slot == slot), None)
    if signature is None:
        # The slot was empty: the piece comes off again.
        if worn is None or not qualifies(worn):
            memory.displaced = None
            return None
        key = policy._equipment_takeoff(snapshot, RESTORE_GOAL, EQUIPMENT_SLOT_KEY[slot])
        if key is not None:
            policy.last_reason = f"quest25:{RESTORE_GOAL}"
        return key
    if worn is not None and policy._item_signature(worn) == signature:
        memory.displaced = None
        return None
    item = next((item for item in snapshot.inventory if policy._item_signature(item) == signature), None)
    if item is None:
        memory.displaced = None
        return None
    key = policy._equipment_wield(snapshot, RESTORE_GOAL, item, slot, quest_contract_exempt=True)
    if key is not None:
        policy.last_reason = f"quest25:{RESTORE_GOAL}"
    return key
