"""The finale expedition's way down to its target floor, at once.

Owner 2026-11-24 (verbatim): 「決戦装備にしたら速やかに最下層まで降りること。寄り道は不要。」

n1-c life-221 (Magic-Eater Lv50, Oberon killed, the Serpent of Chaos's 100F the target): the
preparation phase finished (finale_prep step ``done``, ``lifted``) at 16:51:52 on 2026-11-24 and
Word of Recall landed on Angband 95F (the recall depth a Scroll of Reset Recall had set to 95 at
16:49:28, reset_recall, before the phase began).  From 16:52:13 the ordinary ladder owned the
floor: the exploration, the walk to the loot and its pickups, the dug pocket's hold (anaguma), the
detected threat's choke hold, the shots at what came in view; seek-downstairs was asked 12 times
of the visit's boards.  At 16:55:51 the pack was full and the ordinary return read Word of Recall
(trigger ``pack-full``): the expedition was back in town without having gone below 95F.

While the expedition is under way (``applies``: a Magic-Eater with the cap lifted, finale_prep
``lifted``, on an Angband floor from 95F down to the floor above the first finale floor whose
quest is not done, no quest floor) the descent owns the floor (``key``, the floor-avoidance
layer's rung above the dug pocket):

* the safety first, as before: the emergency ladder, the summoner shots, the summons rules, the
  sight triggers, the Resistance potion, the one-shot breath, the never-moving monsters and the
  unseen retreat stand above this rung; the awake T1's sensed leave (owner 2026-11-08) is asked
  first inside it; a hostile that attacks from beside the player refuses it (survival_preemption,
  the rung is a ``P`` row), and so does a low HP (``DESCEND_MIN_HP_RATIO``): the combat layer
  answers those boards;
* the down stairs underfoot, taken; else the arrival's powers (me_powers' FLOOR occasion: the new
  floor's detection and the deep arrival's speed, and its stairs-needed-and-unknown map); else the
  walk to the nearest usable down stairs (policy ``_descent_step``); else a carried mapping device
  or Scroll of Magic Mapping (area_mapping ``finale_descent_key``); else the exploration's step
  toward the unknown, to find the stairs;
* no loot (policy ``_normal_loot_key`` and destruction_loot decline), no dug pocket or choke hold
  (ladder_floor_avoidance skips anaguma and the detected-threat preparation), no hunt or shot from
  the combat layer while this rung walks;
* the town return: the finale's own lines only (``return_due``, finale_hold's relay-floor line:
  no Teleportation scroll and no charge of the absorbed staff, or the Restore Mana overspent),
  hunger with nothing to eat, and the Potions of Healing and *Healing* spent (``healing_spent``:
  owner 2026-11-25, answer (b)-5 「回復の薬が尽きたら帰還する」, the two the finale carries,
  angband_finale ``CARRY``; the Cure Critical Wounds count is not read); no ordinary supply
  return and no ``pack-full`` (policy_town ``_should_start_town_return``), and a full pack
  or the next depth's supply ledger refuses no stair (policy_navigation ``_descent_is_blocked``).
  The emergency recalls above are kept.

The game has no Deep Descent in Hengband (C:/hengband/src: no such scroll in
sv-definition/sv-scroll-types.h; Teleport Level goes up or down at random), so the stairs are the
way down.  99F/100F keep 「99F 100Fはサーチ禁止」 (search_ban): the descent never searches.
"""
from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import DESCEND_MIN_HP_RATIO, DOWN_STAIRS_KEY
from hengbot.stair_destination import down_destination

REASON = "finale-descent"
RUNG = "finale_descent.key"
RETURN_TRIGGER = "angband-finale:descent"
HEALING_TRIGGER = "angband-finale:descent-healing-out"
# The recall landing of the expedition (angband_cap.ANGBAND_DEPTH_CAP, angband_finale
# PREPARE_DEPTH): the descent's floors start there.
FIRST_FLOOR = 95


def target_depth(snapshot) -> int | None:
    """The first finale floor (99F Oberon, 100F the Serpent) whose quest is not done, else None."""
    from hengbot import angband_finale  # import cycle
    quests = getattr(snapshot, "quests", None) or {}
    for depth in angband_finale.FINALE_DEPTHS:
        quest = quests.get(angband_finale.FINALE[depth][0])
        if quest is None or quest.status not in angband_finale.DONE_STATUSES:
            return depth
    return None


def applies(policy, snapshot) -> bool:
    """The expedition is on its way down: a Magic-Eater with the cap lifted, on an Angband floor
    (no quest floor) from ``FIRST_FLOOR`` to the floor above ``target_depth``."""
    from hengbot import angband_finale  # import cycle
    if getattr(snapshot, "in_town", True):
        return False
    floor_key = getattr(snapshot, "floor_key", None)
    if not floor_key or floor_key[0] != DUNGEON_ANGBAND or floor_key[2]:
        return False
    if not (angband_finale.magic_eater(snapshot) and angband_finale.lifted(policy)):
        return False
    target = target_depth(snapshot)
    return target is not None and FIRST_FLOOR <= floor_key[1] < target


def return_due(policy, snapshot) -> bool:
    """The finale's own recall line on the way down (finale_hold ``return_due``)."""
    from hengbot import finale_hold  # import cycle
    return finale_hold.return_due(policy, snapshot)


def healing_spent(snapshot) -> bool:
    """No Potion of Healing and no Potion of *Healing* carried (angband_finale ``carried``): the
    finale's carry has no lower bound for them below its departure target (angband_finale
    ``CARRY``, 30 and 15), so the line is none left."""
    from hengbot import angband_finale  # import cycle
    return (angband_finale.carried(snapshot, angband_finale.HEALING)
            + angband_finale.carried(snapshot, angband_finale.STAR_HEALING)) <= 0


def _descend_here(policy, snapshot):
    here = snapshot.grid_at(snapshot.player.position)
    if here is None or not here.is_descent or not policy._is_descent_target(snapshot, here):
        return None
    if not policy._destination_depth_allowed(
            snapshot, down_destination(snapshot.dungeon_level, here)):
        return None
    policy.last_reason = f"{REASON}:descend"
    policy._offer_execution(
        DOWN_STAIRS_KEY, producer="departure", work_id=f"{REASON}:descend:{snapshot.floor_key}",
        next_step=f"departure.{REASON}.descend", expected_effect="floor-change")
    return DOWN_STAIRS_KEY


def key(policy, snapshot):
    """The descent's key on a floor ``applies`` holds for, else None (the ladder goes on)."""
    from hengbot import area_mapping, me_powers, threat_tiers  # import cycle
    if not applies(policy, snapshot) or policy._floor_navigation_exit_locked(snapshot):
        return None
    if policy._returning_to_town or snapshot.player.recalling:
        return None
    # Owner 2026-11-08: inside an awake T1's sensing radius, leave by its own order.
    sensed = threat_tiers.sensed_t1_leave_key(policy, snapshot)
    if sensed is not None:
        return sensed
    if snapshot.player.hp_ratio < DESCEND_MIN_HP_RATIO:
        return None
    descend = _descend_here(policy, snapshot)
    if descend is not None:
        return descend
    # The arrival's detection and speed, and the map where no down stairs are known.
    power = me_powers.power_key(policy, snapshot, me_powers.FLOOR)
    if power is not None:
        return power
    step = policy._town_producer_entry("_descent_step", lambda: policy._descent_step(snapshot))
    if step is not None:
        move = policy._step_toward(snapshot, step)
        if move is not None:
            policy.last_reason = f"{REASON}:seek-downstairs"
            return move
    mapped = area_mapping.finale_descent_key(policy, snapshot)
    if mapped is not None:
        return mapped
    goal = policy._town_producer_entry("_explore_step", lambda: policy._explore_step(snapshot))
    if goal is None:
        return None
    move = policy._step_toward(snapshot, goal)
    if move is not None:
        policy.last_reason = f"{REASON}:search-downstairs"
    return move
