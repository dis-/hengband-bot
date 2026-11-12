"""Threat tiers: the keys of the selected supply fight (plan step 7, 3.4, D3, D4, D7).

Split out of ``threat_tiers`` (maintainability review 2026-11-09, step 4): the reasons, the
fight's target and stop conditions, and the key of each supply (Healing, resistance, good ammo,
wand / staff charges, attack scrolls).  The rung itself (``supply_fight_key``) and its gates
(``supply_fight_applies``, ``committed_supply_fight_viable``) stay in ``threat_tiers``: they call
``tiered`` and ``acts_here``, which tests patch there.  ``threat_tiers`` re-exports every name.
"""

from __future__ import annotations

from hengbot import attack_expectation, me_device_attacks
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_POTION_RESIST_COLD,
    SV_POTION_RESISTANCE,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_WAND,
)
from hengbot.policy_constants import HEAL_ORDER
from hengbot.threat_projection import (
    ATTACK_SCROLLS,
    HEAL_AMOUNTS,
    SV_POTION_RESIST_HEAT,
    _launcher_stacks,
    _race_flags,
    _ranged_ready,
    _resistance_after,
    _scroll_reads,
    heal_credit,
    scroll_damage_at,
)


# The selected supply fight (plan step 7, 3.4, D3, D4, D7): the reasons it answers with.
SUPPLY_SPEED_REASON = "supply-fight:quaff-speed"
SUPPLY_HEAL_REASON = "supply-fight:quaff-healing"
SUPPLY_RESIST_REASON = "supply-fight:quaff-resistance"
SUPPLY_AMMO_REASON = "supply-fight:fire-good-ammo"
SUPPLY_WAND_REASON = "supply-fight:aim-wand"
SUPPLY_STAFF_REASON = "supply-fight:use-staff"
SUPPLY_SCROLL_REASON = "supply-fight:read-attack-scroll"
# The cheapest healing potion first (each credited as in the projection):
# policy_constants.HEAL_ORDER, imported above.


def _fight_target(policy, hostiles, result):
    """The selected monster the fight is for: the committed race while it is in view, else the
    nearest selected one."""
    selected = [monster for monster in hostiles if monster.index in result.selected]
    committed = policy._unique_combat_committed_race_id
    for monster in selected:
        if monster.race_id == committed:
            return monster
    return min(selected, key=lambda monster: (monster.distance, monster.index), default=None)


def supply_fight_stopped(snapshot, hostiles, target=None) -> bool:
    """D4: today's stop conditions of the committed unique fight: the player afraid, blind,
    confused or paralysed, a breeder in view, or another summoner in view (with no ``target``:
    any summoner, the decided side's hold reading the engagement as a whole)."""
    player = snapshot.player
    return bool(
        player.afraid or player.blind or player.confused or player.paralyzed
        or any(monster.can_multiply for monster in hostiles)
        or any(monster.can_summon and (target is None or monster.index != target.index)
               for monster in hostiles))


def ranged_plan(policy, snapshot, result, target) -> bool:
    """D4 「the adjacency requirement is dropped for ranged plans」: the plan spends an attack
    supply (good ammo, charges, scrolls), or its free attack on the target is not melee."""
    plan = result.supply_plan
    if plan is not None and (plan.good_ammo or plan.charges or plan.scrolls):
        return True
    free = result.free_damage.get(target.index, 0.0)
    return free > 0 and free > attack_expectation.melee(policy, snapshot, target)


def _aim(policy, snapshot, target) -> str | None:
    """A direction key that reaches ``target``: beside it, or on a clear ray (``_ranged_target``)."""
    if target.distance <= 1 or policy._ranged_target(snapshot, [target]) is target:
        return policy._direction_key(snapshot.player.position, target.position)
    return None


def _spend(policy, snapshot, target, verb, item, reason, suffix=""):
    key = reserved_item_command(policy, snapshot, verb, item, suffix=suffix)
    if key is not None:
        policy.last_reason = reason
        policy._unique_combat_committed_race_id = target.race_id
    return key


def _heal_key(policy, snapshot, result, target):
    """Owner 2026-11-12 (「計画に揃える」: 「HP が次の1手の最大を下回ったら飲む。計画どおりの本数で
    戦え、薬の無駄が減る。…即死の判定（次の1手で HP 以上）はこれまでどおり先に効く。」): drink
    once the HP is down to the next action's p95, the point the plan credits a dose at
    (``threat_projection.heal_credit``); a dose with nothing to restore there is not drunk.  The
    即死 rungs stand above this one and answer that board first, as before."""
    player = snapshot.player
    if player.hp >= player.max_hp or player.hp > result.next_action_p95:
        return None
    for sval in HEAL_ORDER:
        potion = policy._find_exact_potion(snapshot, sval)
        if potion is None or heal_credit(HEAL_AMOUNTS[sval], player.max_hp,
                                         result.next_action_p95) <= 0:
            continue
        return _spend(policy, snapshot, target, "quaff", potion, SUPPLY_HEAL_REASON)
    return None


def _resistance_key(policy, snapshot, target):
    if _resistance_after(snapshot) is None:
        return None
    for sval in (SV_POTION_RESISTANCE, SV_POTION_RESIST_HEAT, SV_POTION_RESIST_COLD):
        potion = policy._find_exact_potion(snapshot, sval)
        if potion is not None:
            return _spend(policy, snapshot, target, "quaff", potion, SUPPLY_RESIST_REASON)
    return None


def _good_ammo_key(policy, snapshot, result, target):
    launcher = policy._equipped_launcher(snapshot)
    if launcher is None or not _ranged_ready(snapshot):
        return None
    direction = _aim(policy, snapshot, target)
    if direction is None:
        return None
    free = result.free_damage.get(target.index, 0.0)
    for good, damage, number in (
            (good, damage, number) for number, (good, damage, _rounds)
            in enumerate(_launcher_stacks(policy, snapshot, target))):
        if good and damage > free:
            stacks = [item for item in snapshot.inventory
                      if item.tval == launcher.ammo_tval and item.count > 0]
            return _spend(policy, snapshot, target, "fire", stacks[number], SUPPLY_AMMO_REASON,
                          direction)
    return None


def _charge_key(policy, snapshot, result, target):
    if not _ranged_ready(snapshot) or snapshot.inside_arena:
        return None
    flags, level = _race_flags(policy, target), snapshot.player.level
    free = result.free_damage.get(target.index, 0.0)
    direction = _aim(policy, snapshot, target)
    best = None
    for item in snapshot.inventory:
        kind = "wand" if item.tval == TVAL_WAND else "staff" if item.tval == TVAL_STAFF else None
        if kind is None or not item.known or item.charges <= 0 or item.charging:
            continue
        power = me_device_attacks.POWERS.get((kind, item.sval))
        if power is None or power.group_only or (kind == "wand" and direction is None):
            continue
        damage = (attack_expectation.device_use_success(snapshot.player.device_skill, power.level)
                  * me_device_attacks.expected_damage(power, level, flags))
        if damage > free and (best is None or damage > best[0]):
            best = (damage, kind, item)
    if best is None:
        return None
    _damage, kind, item = best
    if kind == "wand":
        return _spend(policy, snapshot, target, "wand", item, SUPPLY_WAND_REASON, direction)
    return _spend(policy, snapshot, target, "staff", item, SUPPLY_STAFF_REASON)


def _scroll_key(policy, snapshot, result, target):
    reads = _scroll_reads(snapshot)
    free = result.free_damage.get(target.index, 0.0)
    if not reads or scroll_damage_at(reads[0], target.distance) <= free:
        return None
    sval = next(sval for sval, scroll in ATTACK_SCROLLS.items() if scroll == reads[0])
    item = next((item for item in snapshot.inventory
                 if item.tval == TVAL_SCROLL and item.sval == sval and item.aware), None)
    if item is None:
        return None
    key = policy._read_key(snapshot, item)
    if key is not None:
        policy.last_reason = SUPPLY_SCROLL_REASON
        policy._unique_combat_committed_race_id = target.race_id
    return key
