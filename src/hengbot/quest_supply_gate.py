"""Supplies of a quest not yet taken wait for its other conditions (home-full root stage 5).

Owner 2026-11-19 (home-full root proposal, question 5) 「条件がそろってから買い自宅に置く」: the
supplies a fixed quest asks to carry (``required_force``'s scrolls, potions, throwing items,
launcher and tools; its Speed and healing potions) are bought only after every other acceptance
condition of that quest is met, and held in the Home until the quest is taken; they are not
carried before that.  QUEST_33's acceptance says the same 「満たさない間は飛ばして次のクエストを
受け、このクエストの物資も買わない」.

n1-a life-531 2026-11-19 16:05 (Warrior Lv50, no absorbed Teleportation): Q33 was the untaken
fixed-quest head, short of a resistance its force names (blindness), and its carry
(``teleport_scrolls_without_absorbed`` 40 Scrolls of Teleportation) was bought, kept on the pack,
taken out of the Home and asked at departure; the 25 scrolls the weight relief had deposited in
Telmora were withdrawn back in the Outpost and the overweight pack stopped the visit
(``town:blocked:survival:inventory_weight_ready``).

``admitted`` is the one answer every reader of an untaken quest's carry asks
(``_carry_procurement_strategy`` and ``_quest_strategy_for_errand_or_floor``, which purchase,
retention, the Home withdrawal and the departure minimum all read).  The other conditions are
the ones no purchase meets (``_approved_strategy_force_ready`` less its carries and potions):

- maximum HP and the damage floors (per 10 game turns, ``quest_force_rows.row_damage``), the
  no-healing tier's floors standing for both when it names them;
- the force's resistances (an alternative from the profile counts, ``has_ability_or_alternative``);
- the ranged damage per turn (``quest_ranged_force.turn_met``; rounds are bought);
- the one-turn kill (``quest_one_turn_kill.met``);
- for a force whose rows replace the projection, the quest level's depth abilities other than
  the *Destruction* means (a staff is bought).

Met once in a town visit, the quest stays admitted for the rest of that visit (``ADMITTED``,
keyed by the visit epoch): a ring taken off for a swap does not send its supplies Home and back.

A quest taken (or in progress) is not asked here: its supplies stay as they were.  ``home_keeps``
keeps the Home's stock of a waiting quest's kinds off the full-Home sale and destruction.
"""
from __future__ import annotations

from typing import Any

from hengbot import ability_sources
from hengbot.item_reservation import decision_memo
from hengbot.model import SV_POTION_SPEED, TVAL_POTION

ADMITTED = "_quest_supply_admitted"   # (town visit epoch, frozenset of quest ids); visit


def _visit_admitted(policy: Any) -> frozenset:
    held = getattr(policy, ADMITTED, None)
    epoch = getattr(policy, "_town_visit_epoch", None)
    if not held or epoch is None or held[0] != epoch:
        return frozenset()
    return held[1]


def _latch(policy: Any, snapshot: Any, quest_id: int) -> None:
    epoch = getattr(policy, "_town_visit_epoch", None)
    if epoch is None or not snapshot.in_town:
        return
    setattr(policy, ADMITTED, (epoch, _visit_admitted(policy) | {quest_id}))


def other_conditions_met(policy: Any, snapshot: Any, profile: Any) -> bool:
    """Every acceptance condition of ``profile`` that no purchase meets (module docstring)."""
    from hengbot import quest_force_rows, quest_one_turn_kill, quest_ranged_force
    from hengbot.policy_constants import DESTRUCTION_GATE_LABEL
    from hengbot.quest_strategies import (
        acceptance_dps_floor, acceptance_hp_floor, has_ability_or_alternative, torch_throw_output,
    )
    force = policy._strategy_force_for_snapshot(snapshot, profile)
    class_id = snapshot.player.class_id
    per_action = policy._strategy_measured_dps(snapshot, force)
    dps = quest_force_rows.row_damage(
        policy, snapshot, force, force, max(per_action, torch_throw_output(force, class_id)))
    max_hp = snapshot.player.max_hp
    no_heal = force.get("no_healing_tier")
    floors = ((isinstance(no_heal, dict) and max_hp >= acceptance_hp_floor(no_heal, class_id)
               and dps >= acceptance_dps_floor(no_heal, class_id))
              or (max_hp >= acceptance_hp_floor(force, class_id)
                  and dps >= acceptance_dps_floor(force, class_id)))
    if not floors:
        return False
    if not all(has_ability_or_alternative(force, policy._profile_resistance_name(str(name)),
                                          ability_sources.held_abilities(snapshot.player), snapshot.equipment)
               for name in force.get("resists", ())):
        return False
    if not quest_ranged_force.turn_met(policy, snapshot, force, force):
        return False
    if not quest_one_turn_kill.met(policy, snapshot, force):
        return False
    if force.get("floors_replace_projection"):
        info = policy._quest_knowledge.get(profile.quest_id)
        if info is not None and policy._missing_required_abilities(
                snapshot, info.level) - {DESTRUCTION_GATE_LABEL}:
            return False
    return True


def admitted(policy: Any, snapshot: Any, profile: Any) -> bool:
    """The untaken quest of ``profile`` may have its supplies bought, kept and carried."""
    quest_id = getattr(profile, "quest_id", None)
    if quest_id is None:
        return True
    if quest_id in _visit_admitted(policy):
        return True
    met = decision_memo(policy, "quest-supply-gate", snapshot, quest_id,
                        lambda: other_conditions_met(policy, snapshot, profile))
    if met:
        _latch(policy, snapshot, quest_id)
    return met


def waiting_profile(policy: Any, snapshot: Any) -> Any:
    """The untaken quest whose supplies wait for its other conditions, or None.

    The quest ``_quest_strategy_for_errand_or_floor`` would prepare (the earliest approved one
    not held back) when nothing is taken and it is not admitted."""
    from hengbot.policy_constants import FIXED_QUEST_ALLOWLIST, QUEST_STATUS_UNTAKEN
    from hengbot import quest_one_turn_kill
    known = policy._known_fixed_quests(snapshot)
    if policy._in_flight_fixed_quests(known):
        return None
    candidates = [
        quest for quest in known.values()
        if quest.id in FIXED_QUEST_ALLOWLIST and quest.status == QUEST_STATUS_UNTAKEN
        and policy.approved_quest_strategy(quest.id) is not None
        and not quest_one_turn_kill.holds_back(policy, snapshot, quest.id)
    ]
    if not candidates:
        return None
    profile = policy.approved_quest_strategy(min(candidates, key=policy._fixed_quest_order).id)
    return None if admitted(policy, snapshot, profile) else profile


def home_keeps(policy: Any, snapshot: Any, item: Any) -> bool:
    """A Home stack of a kind the waiting quest carries: it stays in the Home (not sold or
    destroyed by the full-Home relief) until the quest is taken.  No count cap (owner
    2026-11-19: no cap on supply spares)."""
    if getattr(item, "slot", None) != "home-surplus":
        return False
    force = decision_memo(policy, "quest-supply-waiting-force", snapshot, None, lambda: (
        None if (profile := waiting_profile(policy, snapshot)) is None
        else policy._strategy_force_for_snapshot(snapshot, profile)))
    if force is None:
        return False
    from hengbot.quest_strategies import heal_potion_sval
    if item.tval == TVAL_POTION and item.aware:
        if item.sval == SV_POTION_SPEED and int(force.get("speed_potions", 0)) > 0:
            return True
        if item.sval == heal_potion_sval(force) and int(force.get("heal_potions", 0)) > 0:
            return True
    target = policy._quest_carry_target_for_item(snapshot, item, force)
    return target is not None and target[2] > 0
