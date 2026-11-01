"""D21: the Magic-Eater answers an adjacent attacker at range before melee.

Recorded 2026-10-30 deaths of the class-16 viewing character on Yeek cave 1F
(lives 8, 9 and 11): it meleed giant white mice, an insect swarm and small
kobolds to death with dual-wielded blades or diggers, missing most blows,
while it carried an absorbed Magic Missile, attack wands and lit torches.  A
bolt or a thrown torch needs no melee to-hit roll against the target's AC.

Order: the strongest other absorbed attack power when it beats Magic Missile
(me_device_attacks, 2026-10-31; also on quest floors except quest 1), the
absorbed Magic Missile (``mBp``; the power list reports an empty or unlearned
power and the next decision falls through), a known attack wand from the
pack, a spare lit torch, then the caller's melee.  Town fights use the same
order (owner 2026-10-31 「近接以外の攻撃手段も街で使う」).  Only the generic
combat rungs call this; apart from the absorbed attack powers, quest floors
keep their reviewed strategies (me_q1_torch, q34 missiles) and every other
class keeps melee.
"""

from hengbot import me_device_attacks
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
        and snapshot.floor_key[2] == 0
        and not player.blind
        and not player.confused
    )


def _throwable_torch(policy, snapshot):
    torches = [item for item in snapshot.inventory if item.is_torch and item.fuel > 0]
    if not torches or policy._opening_q1_torches_reserved(snapshot):
        return None
    light = next((item for item in snapshot.equipment if item.slot == "light"), None)
    burning_torch = light is not None and (light.tval, light.sval) == (TVAL_LIGHT, SV_LIGHT_TORCH)
    # The light keeps one replacement when it is itself a torch.
    if burning_torch and sum(item.count for item in torches) <= 1:
        return None
    return torches[0]


def melee_refused(policy, snapshot) -> bool:
    """The game refuses this board's melee blow: fear or a NO_MELEE dungeon.

    Fear refuses melee only (cmd-attack.cpp:228) and so does a NO_MELEE
    dungeon (cmd-attack.cpp:202 「なぜか攻撃することができない。」); the
    absorbed powers check confusion (cmd-magiceat.cpp:492), wands randomize
    under confusion (zapwand-execution.cpp:69) and throws check neither."""
    return (snapshot.player.afraid
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0]))


def melee_refused_key(policy, snapshot, adjacent) -> str | None:
    """Beside ``adjacent`` while melee is refused: this ranged order alone, else None.

    The combat rungs called this order inside their melee branch, so an
    afraid Magic-Eater waited beside its attacker (#47 hit-no-action-1101,
    n1-c life-085's jelly), and in a NO_MELEE dungeon every rung skipped it
    (owner 2026-11-01 「遠隔と取り込んだ力は使う」).  The callers' melee keeps
    its own fear and dungeon checks."""
    if not adjacent or not melee_refused(policy, snapshot):
        return None
    return attack_key(policy, snapshot, policy._weakest(adjacent))


def outpaced_afraid_key(policy, snapshot, adjacent) -> str | None:
    """Afraid beside an attacker at least as fast: this ranged order, else None.

    Owner 2026-11-01 「遠隔の手段があれば撃つ」: walking away from it donates a
    blow every step (n1-c life-085's speed +10 jelly), so the flee rung fires
    instead of walking; without a ranged answer it flees as before.  The
    survival ladder above the flee rung answers first."""
    if not snapshot.player.afraid:
        return None
    speed = snapshot.player.speed
    return melee_refused_key(
        policy, snapshot, [monster for monster in adjacent if monster.speed >= speed])


def attack_key(policy, snapshot, target) -> str | None:
    """The ranged answer to ``target`` (adjacent or ray-aligned), else None."""
    origin, cell = snapshot.player.position, target.position
    direction = DIRECTION_KEYS[(max(-1, min(1, cell.y - origin.y)),
                                max(-1, min(1, cell.x - origin.x)))]
    # 2026-10-31: an absorbed attack power stronger than Magic Missile, on
    # quest floors too, except quest 1 where D17 throws torches first.
    if snapshot.floor_key[2] != 1:
        device = me_device_attacks.attack_key(policy, snapshot, target, direction)
        if device is not None:
            return device
    if not applies(snapshot):
        return None
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
    # A carried wand is the same wand_effect (zapwand-execution.cpp:102), so a
    # town ball keeps the absorbed powers' area rule.
    wand = next((item for item in snapshot.inventory
                 if item.tval == TVAL_WAND and item.known
                 and item.sval in ATTACK_WAND_SVALS and item.charges > 0
                 and not item.charging
                 and not me_device_attacks.catches_unbeatable_friendly(
                     policy, snapshot, me_device_attacks.POWERS[("wand", item.sval)],
                     target, direction)), None)
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
