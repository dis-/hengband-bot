"""D21: the Magic-Eater answers an adjacent attacker at range before melee.

Recorded 2026-10-30 deaths of the class-16 viewing character on Yeek cave 1F
(lives 8, 9 and 11): it meleed giant white mice, an insect swarm and small
kobolds to death with dual-wielded blades or diggers, missing most blows,
while it carried an absorbed Magic Missile, attack wands and lit torches.  A
bolt or a thrown torch needs no melee to-hit roll against the target's AC.

Order: the absorbed Magic Missile (``mBp``; the power list reports an empty
or unlearned power and the next decision falls through), a known attack wand
from the pack, a spare lit torch, then the caller's melee.  Only the generic
dungeon combat rungs call this; quest floors keep their reviewed strategies
(me_q1_torch, q34 missiles) and every other class keeps melee.
"""

from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater import MISSILE_REASON
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import TVAL_WAND
from hengbot.policy_constants import DIRECTION_KEYS


WAND_REASON = "ranged:aim-wand"
TORCH_REASON = "ranged:throw-torch"
# sv-wand-types.h: bolts, balls and breaths that damage the first monster on
# the ray.  Wonder (24) is random (it can clone or haste) and is never aimed.
ATTACK_WAND_SVALS = frozenset({14, 15, 16, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29})
TVAL_LIGHT = 39
SV_LIGHT_TORCH = 0


def applies(snapshot) -> bool:
    player = snapshot.player
    return (
        player.class_id == PLAYER_CLASS_MAGIC_EATER
        and not snapshot.in_town
        and snapshot.floor_key[2] == 0
        and not player.blind
        and not player.confused
    )


def _throwable_torch(policy, snapshot):
    torches = [item for item in snapshot.inventory if item.is_torch and item.fuel > 0]
    if not torches:
        return None
    light = next((item for item in snapshot.equipment if item.slot == "light"), None)
    burning_torch = light is not None and (light.tval, light.sval) == (TVAL_LIGHT, SV_LIGHT_TORCH)
    # The light keeps one replacement when it is itself a torch.
    if burning_torch and sum(item.count for item in torches) <= 1:
        return None
    return torches[0]


def attack_key(policy, snapshot, target) -> str | None:
    """The ranged answer to ``target`` (adjacent or ray-aligned), else None."""
    if not applies(snapshot):
        return None
    origin, cell = snapshot.player.position, target.position
    direction = DIRECTION_KEYS[(max(-1, min(1, cell.y - origin.y)),
                                max(-1, min(1, cell.x - origin.x)))]
    observed = snapshot.magic_eater_wand_charges
    if observed == -1:
        # The wand type is not learned; absorbing happens only in town.
        policy._me_missile_unlearned_floor = snapshot.floor_key
    elif observed == 0:
        policy._me_missile_empty_turn = snapshot.turn
    if (getattr(policy, "_me_missile_unlearned_floor", None) != snapshot.floor_key
            and getattr(policy, "_me_missile_empty_turn", None) != snapshot.turn):
        policy.last_reason = MISSILE_REASON
        return "mBp" + direction
    wand = next((item for item in snapshot.inventory
                 if item.tval == TVAL_WAND and item.known
                 and item.sval in ATTACK_WAND_SVALS and item.charges > 0
                 and not item.charging), None)
    if wand is not None:
        key = reserved_item_command(policy, snapshot, "wand", wand, suffix=direction)
        if key is not None:
            policy.last_reason = WAND_REASON
            return key
    torch = _throwable_torch(policy, snapshot)
    if torch is not None:
        key = reserved_item_command(policy, snapshot, "throw", torch, suffix=direction)
        if key is not None:
            policy.last_reason = TORCH_REASON
            return key
    return None
