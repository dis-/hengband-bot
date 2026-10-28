"""O3: reserve the birth wand, absorb it safely, and use it at Q34's stands."""

from hengbot.model import TVAL_WAND
from hengbot.claim_register import claims


MAGIC_EATER = 16
MAGIC_MISSILE = 15  # sv-definition/sv-wand-types.h
ABSORB_REASON = "magic-eater:absorb"
MISSILE_REASON = "magic-eater:q34-missile"


def reserved_for_absorption(player, item):
    """The O3 device is an attack resource, including before identification."""
    return (player.class_id == MAGIC_EATER and item.tval == TVAL_WAND
            and item.sval == MAGIC_MISSILE)


@claims("quest-request")
def absorb_key(policy, snapshot, hostiles):
    player = snapshot.player
    if (snapshot.store is not None or hostiles or player.hungry
            or player.blind or player.confused or player.poisoned or player.cut
            or player.stunned or player.paralyzed or player.hallucinated
            or player.hp < player.max_hp):
        return None
    candidate = next((item for item in snapshot.inventory
                      if reserved_for_absorption(player, item) and item.known
                      and item.charges > 0 and not item.charging
                      and not (item.timeout or 0)), None)
    if candidate is None:
        return None
    policy.last_reason = ABSORB_REASON
    key = "G" + candidate.slot
    if snapshot.in_town:
        policy._offer_execution(
            key, producer="quest-request", work_id=ABSORB_REASON,
            next_step="quest.absorb-birth-wand",
            arguments=(policy._item_signature(candidate),),
            expected_effect="device-absorbed")
    return key


def q34_missile_key(policy, snapshot, profile, target, direction):
    if profile.quest_id != 34 or snapshot.player.class_id != MAGIC_EATER:
        return None
    # A zero is observed in the power list, never inferred from an inventory
    # wand or decremented speculatively after a failed spell. Recheck at the
    # next approved target, where natural regeneration may have restored it.
    empty = getattr(policy, "_q34_empty_magic_target", None)
    if snapshot.magic_eater_wand_charges == 0:
        empty = target.position
        policy._q34_empty_magic_target = empty
    if empty == target.position:
        return None
    policy.last_reason = MISSILE_REASON
    policy._quest_strategy_throw_exp[34] = (
        (target.race_id, target.position.y, target.position.x), snapshot.player.exp)
    return "mBp" + direction


def planned_throw_key(policy, snapshot, profile, planned_throw, torch, *, suffix):
    """Share the approved stand and kill evidence between missiles and torches."""
    from hengbot.model import Position
    from hengbot.policy_constants import WAIT_KEY
    from hengbot.item_reservation import reserved_item_command

    plan, target_monster = planned_throw
    stand = Position(*plan["stand"])
    if snapshot.player.position != stand:
        step = policy._quest_strategy_route_step(
            snapshot, profile, stand
        )
        if step is None:
            policy.last_reason = (
                "quest:blocked:q34-throw-point-unreachable"
                if profile.quest_id == 34
                else "quest-strategy:throw-point-unreachable"
            )
            return WAIT_KEY
        policy.last_reason = "quest-strategy:approach-throw-point"
        policy._declare_reach(stand)
        return policy._step_toward(snapshot, step)
    magic = q34_missile_key(policy, snapshot, profile, target_monster, suffix)
    if magic is not None:
        return magic
    if torch is not None:
        policy.last_reason = "quest-strategy:throw-torch"
        # Remember the target and the experience shown before this
        # throw: a gain on the next board while the target vanishes
        # is player-visible proof of the kill.
        policy._quest_strategy_throw_exp[profile.quest_id] = (
            (target_monster.race_id, target_monster.position.y,
             target_monster.position.x),
            snapshot.player.exp,
        )
        return (
            reserved_item_command(policy, snapshot, "throw", torch, suffix=suffix)
        )
    return None
