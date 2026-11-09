"""Threat tiers: the per-monster flags and the escape means (design 4.1-4.4).

Split out of ``threat_tiers`` (maintainability review 2026-11-09, step 4): what a monster can
do the player cannot undo (``irreversible_kinds``), what grows with time (``worsens_kinds``),
the escape means usable now (``escape_means``, the blind teleport ``blind_teleport_key``) and
whether they can be restored, and the monsters that need not be fought (``need_not_fight``).
``threat_tiers`` re-exports every name here.
"""

from __future__ import annotations

from hengbot import (
    destruction_use,
    me_absorbed_substitutes,
    me_capability,
    quest_no_teleport,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_STAFF_TELEPORTATION, TVAL_SCROLL, TVAL_STAFF
from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE, OPPOSITION_ABILITY


SV_SCROLL_TELEPORT_LEVEL = 10
# The reason suffix of a carried Staff of Teleportation used blind (blind_teleport_key).
STAFF_REASON_SUFFIX = "-staff"

# 4.1: what each damage needs to be prevented (snapshot abilities).
STAT_DRAIN_BLOWS = {
    "LOSE_STR": ("sustain_str",), "LOSE_INT": ("sustain_int",), "LOSE_WIS": ("sustain_wis",),
    "LOSE_DEX": ("sustain_dex",), "LOSE_CON": ("sustain_con",), "LOSE_CHR": ("sustain_chr",),
    "LOSE_ALL": ("sustain_str", "sustain_int", "sustain_wis", "sustain_dex", "sustain_con",
                 "sustain_chr"),
}
# player-damage.cpp: acid drains CHR, elec DEX, fire and cold STR (1 in 16 per unresisted hit).
ELEMENTS = {
    "acid": ("ACID", frozenset({"BR_ACID", "BA_ACID", "BO_ACID"}), "sustain_chr"),
    "elec": ("ELEC", frozenset({"BR_ELEC", "BA_ELEC", "BO_ELEC"}), "sustain_dex"),
    "fire": ("FIRE", frozenset({"BR_FIRE", "BA_FIRE", "BO_FIRE"}), "sustain_str"),
    "cold": ("COLD", frozenset({"BR_COLD", "BA_COLD", "BO_COLD", "BO_ICEE"}), "sustain_str"),
}


# ---------------------------------------------------------------- flags

def irreversible_kinds(policy, snapshot, monster) -> tuple:
    """4.1: the irreversible damage ``monster``'s race can deal the unprotected player.

    Exp drain never counts (D5); disenchant is listed (its action stays with 11-05)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None:
        return ()
    player = snapshot.player
    abilities = set(player.abilities)
    sources = player.ability_sources
    effects = {blow.effect for blow in knowledge.blows}
    spells = set(knowledge.abilities)
    kinds = []
    for effect, sustains in STAT_DRAIN_BLOWS.items():
        if effect in effects and not set(sustains) <= abilities:
            kinds.append("stat-drain")
            break
    if "DISEASE" in effects and "sustain_con" not in abilities:
        kinds.append("stat-drain")
    if ("TIME" in effects or "BR_TIME" in spells) and "resist_time" not in abilities:
        kinds.append("stat-drain")
    for name, (blow, element_spells, sustain) in ELEMENTS.items():
        if blow not in effects and not element_spells & spells:
            continue
        immune = name in player.immunities
        resist = f"resist_{name}" in abilities
        if not (immune or resist or sustain in abilities):
            kinds.append("stat-drain")
        # Item destruction stops only with resistance AND opposition (player-damage.cpp).
        source = sources.get(f"resist_{name}", frozenset()) if sources else frozenset()
        lasting = bool(source & {"equipment", "permanent"}) or (resist and not source)
        opposed = "temporary" in source or OPPOSITION_ABILITY in abilities
        if not (immune or (lasting and opposed)):
            kinds.append("item-destruction")
    if effects & {"EAT_ITEM", "UN_POWER"}:
        kinds.append("item-destruction")
    if ("UN_BONUS" in effects or "BR_DISE" in spells) and "resist_disen" not in abilities:
        kinds.append("disenchant")
    return tuple(dict.fromkeys(kinds))


def worsens_kinds(policy, monster) -> tuple:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    kinds = []
    if monster.can_summon:
        kinds.append("summon")
    if monster.can_multiply:
        kinds.append("multiply")
    if knowledge is not None and "SHRIEK" in knowledge.abilities:
        kinds.append("shriek")
    return tuple(kinds)


def _stair_distance(snapshot) -> int | None:
    here = snapshot.player.position
    distances = [here.distance_to(grid.position) for grid in snapshot.grids.values()
                 if grid.has_up_stairs or grid.has_down_stairs]
    return min(distances, default=None)


def escape_means(policy, snapshot, hostiles) -> tuple:
    """4.2: the escape means usable now; empty is 逃げられない."""
    player = snapshot.player
    means = []
    readable = not (player.blind or player.confused) and policy._can_read_scrolls(snapshot)
    teleport_blocked = policy._teleport_blocked_by_equipment(snapshot)
    forbidden = quest_no_teleport.forbids(policy, snapshot)
    scrolls = {item.sval for item in snapshot.inventory
               if item.tval == TVAL_SCROLL and item.aware and item.count > 0}
    if readable and not teleport_blocked and not forbidden:
        if scrolls & {8, 9}:
            means.append("teleport-scroll")
        if SV_SCROLL_TELEPORT_LEVEL in scrolls:
            means.append("teleport-level")
    if readable and any(item.is_recall_scroll for item in snapshot.inventory):
        means.append("recall")
    if not teleport_blocked and not forbidden:
        if not player.confused and any(
                item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                and item.aware and item.charges > 0 for item in snapshot.inventory):
            means.append("teleport-staff")
        if (not player.confused and not quest_no_teleport.forbids_absorbed(policy, snapshot)
                and me_capability.has(policy, snapshot, "staff", SV_STAFF_TELEPORTATION)
                and me_capability.charges(policy, snapshot, "staff", SV_STAFF_TELEPORTATION) > 0):
            means.append("absorbed-teleport")
    if destruction_use.holds_means(policy, snapshot) and destruction_use._scene_holds(
            policy, snapshot):
        means.append("destruction")
    stair = _stair_distance(snapshot)
    chasers = [monster for monster in hostiles
               if not monster.asleep and policy._monster_can_approach(snapshot, monster)
               and monster.speed > player.speed]
    if not chasers or (stair is not None
                       and all(stair < monster.distance for monster in chasers)):
        means.append("walk")
    return tuple(means)


def blind_teleport_key(policy, snapshot, reason: str) -> str | None:
    """Blind and not confused: the absorbed Teleportation, else a carried Staff of
    Teleportation, the means ``escape_means`` counts; None otherwise.

    The scroll a rung reads cannot be read blind (cmd-read.cpp:37 cmd_limit_blind), but the
    ``m`` command refuses only confusion (cmd-magiceat.cpp:463 cmd_limit_confused) and the
    staff refuses neither (cmd-usestaff.cpp do_cmd_use_staff, use-execution.cpp
    ObjectUseEntity::execute: confusion halves the skill, stun may refuse it), and
    SV_STAFF_TELEPORTATION is teleport_player 100 (cmd-usestaff.cpp:101-105).  n1-c life-171
    (2026-11-08 20:08, 城65階): blind at HP 259/993 in the one-shot tier beside ハスター with
    the absorbed staff at 24/24, 98%, the ladder found no readable escape and fired a rocket.
    The rungs that read a relocation scroll ask this in the scroll's place when blind: design
    3.1 即死→逃げる, owner 2026-11-06 「低HPで召喚・引き寄せ・速い敵が見えたら…テレポート/帰還」,
    owner 2026-11-08 「その敵の感知範囲内なら早急に離脱する」.  ``last_reason`` is ``reason``
    (with the cast suffix for the absorbed power, which admits the device key)."""
    means = blind_teleport_means(policy, snapshot)
    if means is None:
        return None
    if means == ABSORBED:
        policy.last_reason = reason + me_absorbed_substitutes.CAST_SUFFIX
        return me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION].key
    key = reserved_item_command(policy, snapshot, "staff", means)
    if key is not None:
        policy.last_reason = reason + STAFF_REASON_SUFFIX
    return key


ABSORBED = "absorbed"


def blind_teleport_means(policy, snapshot):
    """``blind_teleport_key``'s means: ``ABSORBED``, the carried staff, else None."""
    player = snapshot.player
    if (not player.blind or player.confused or snapshot.store is not None
            or policy._teleport_blocked_by_equipment(snapshot)
            or quest_no_teleport.forbids(policy, snapshot)):
        return None
    power = me_absorbed_substitutes.TELEPORTATION
    # The menu walk of the blind cast is the one status_cure.absorbed_cure_key uses.
    if (me_absorbed_substitutes.blind_castable(snapshot)
            and not quest_no_teleport.forbids_absorbed(policy, snapshot)
            and me_capability.has(policy, snapshot, *power)
            and me_capability.charges(policy, snapshot, *power) > 0):
        return ABSORBED
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                 and item.aware and item.charges > 0), None)


def escape_restorable(policy, snapshot) -> bool:
    """4.2 restore: a cure for blindness / confusion, or a removable anti-teleport item."""
    player = snapshot.player
    if (player.blind or player.confused) and policy._find_status_cure_potion(snapshot) is not None:
        return True
    return any(policy._blocks_teleport(item) and not item.is_cursed
               for item in snapshot.equipment)


def need_not_fight(policy, snapshot, monster, row, protected: bool) -> str | None:
    """4.3: ``fearful``, or a monster that cannot reach the player at all.

    The 3-board distance history ("not approaching") is a later step's new policy attribute."""
    if protected:
        return None
    if monster.fearful and not monster.asleep:
        return "fearful"
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if policy._monster_can_approach(snapshot, monster):
        return None
    if row is None or row.get("operational_ranged_prediction", 0) > 0:
        return None
    if row.get("can_teleport_player_to"):
        return None
    if knowledge is not None and "SHRIEK" in knowledge.abilities and policy._has_line_of_fire(
            snapshot, monster.position, snapshot.player.position) and policy._monster_cast_distance(
            monster.position, snapshot.player.position) <= MONSTER_SPELL_MAX_RANGE:
        return None
    if monster.can_summon and policy._summoner_may_summon_next_turn(snapshot, monster):
        return None
    return "cannot-reach"
