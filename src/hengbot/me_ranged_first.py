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

Beside the target the same candidates and melee are weighed instead (owner
2026-11-01, #47 D57: 「見込みの大きい方を使う」): the one with the larger
expected damage per player action is used, and None leaves the turn to the
caller's melee.  The scores: an absorbed power's me_device_attacks score
(displayed success x damage after the known resistance, capped by the
target's HP; Magic Missile at an optimistic 100% when no row was displayed),
a carried wand's, a thrown torch's and melee's attack_expectation figure
(melee scores zero against a touch aura or while afraid).  A tie keeps the
order above, so melee wins only when it is strictly larger (n1-c life-085:
the Lv18 Magic-Eater fired 3d6 missiles at an AC 1 jelly its two hands would
have hit for about four times as much).
"""

from hengbot import attack_expectation, me_device_attacks
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


def afraid_key(policy, snapshot, adjacent) -> str | None:
    """Afraid beside ``adjacent``: this ranged order alone, else None.

    Fear refuses melee only (cmd-attack.cpp:228); the absorbed powers check
    confusion (cmd-magiceat.cpp:492), wands randomize under confusion
    (zapwand-execution.cpp:69) and throws check neither.  The combat rungs
    called this order inside their unafraid melee branch, so an afraid
    Magic-Eater waited beside its attacker (#47 hit-no-action-1101, n1-c
    life-085's jelly).  The callers' melee keeps its fear check; the
    adjacent chooser scores melee zero while afraid (attack_expectation)."""
    if (not adjacent or not snapshot.player.afraid
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0])):
        return None
    return attack_key(policy, snapshot, policy._weakest(adjacent))


def _missile_ready(policy, snapshot) -> bool:
    """Whether the absorbed Magic Missile may be fired (notes an empty or
    unlearned power the game reported)."""
    observed = snapshot.magic_eater_wand_charges
    if observed == -1:
        # The wand type is not learned; absorbing happens only in town.
        policy._me_missile_unlearned_floor = snapshot.floor_key
    elif observed == 0:
        policy._me_missile_empty_turn = snapshot.turn
    return (getattr(policy, "_me_missile_unlearned_floor", None) != snapshot.floor_key
            and getattr(policy, "_me_missile_empty_turn", None) != snapshot.turn)


def _fire_missile(policy, direction) -> str:
    policy.last_reason = MISSILE_REASON
    return "mBp" + direction


def _attack_wand(policy, snapshot, target, direction):
    # A carried wand is the same wand_effect (zapwand-execution.cpp:102), so a
    # town ball keeps the absorbed powers' area rule.
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_WAND and item.known
                 and item.sval in ATTACK_WAND_SVALS and item.charges > 0
                 and not item.charging
                 and not me_device_attacks.catches_unbeatable_friendly(
                     policy, snapshot, me_device_attacks.POWERS[("wand", item.sval)],
                     target, direction)), None)


def _use(policy, snapshot, verb, item, direction, reason) -> str | None:
    key = reserved_item_command(policy, snapshot, verb, item, suffix=direction)
    if key is not None:
        policy.last_reason = reason
    return key


def _first_key(policy, snapshot, target, direction) -> str | None:
    """The fixed order (a target that is not adjacent)."""
    # 2026-10-31: an absorbed attack power stronger than Magic Missile, on
    # quest floors too, except quest 1 where D17 throws torches first.
    if snapshot.floor_key[2] != 1:
        device = me_device_attacks.attack_key(policy, snapshot, target, direction)
        if device is not None:
            return device
    if not applies(snapshot):
        return None
    if _missile_ready(policy, snapshot):
        return _fire_missile(policy, direction)
    wand = _attack_wand(policy, snapshot, target, direction)
    if wand is not None and (key := _use(policy, snapshot, "wand", wand, direction, WAND_REASON)):
        return key
    torch = _throwable_torch(policy, snapshot)
    if torch is not None and (key := _use(policy, snapshot, "throw", torch, direction, TORCH_REASON)):
        return key
    return None


def _adjacent_options(policy, snapshot, target, direction) -> list:
    """(expected damage per action, key sender) of each ranged answer, in the fixed order."""
    options = []
    if snapshot.floor_key[2] != 1:
        best = me_device_attacks.strongest(policy, snapshot, target, direction)
        if best is not None:
            options.append((best[0], lambda: me_device_attacks.device_key(policy, best[1], direction)))
    if not applies(snapshot):
        return options
    if _missile_ready(policy, snapshot):
        seen = me_device_attacks.seen_missile_score(policy, snapshot, target, direction)
        options.append((me_device_attacks.missile_score(policy, snapshot, target) if seen is None else seen,
                        lambda: _fire_missile(policy, direction)))
    wand = _attack_wand(policy, snapshot, target, direction)
    if wand is not None:
        options.append((attack_expectation.carried_wand(policy, snapshot, target, wand),
                        lambda: _use(policy, snapshot, "wand", wand, direction, WAND_REASON)))
    torch = _throwable_torch(policy, snapshot)
    if torch is not None:
        options.append((attack_expectation.torch_throw(policy, snapshot, target, torch),
                        lambda: _use(policy, snapshot, "throw", torch, direction, TORCH_REASON)))
    return options


def _strongest_adjacent_key(policy, snapshot, target, direction) -> str | None:
    """The answer with the larger expected damage per action; None is melee."""
    melee = attack_expectation.melee(policy, snapshot, target)
    # sorted() is stable: a tie keeps the fixed order.
    for score, send in sorted(_adjacent_options(policy, snapshot, target, direction),
                              key=lambda option: -option[0]):
        if score < melee:
            return None
        if (key := send()) is not None:
            return key
    return None


def _aim(snapshot, target) -> str:
    origin, cell = snapshot.player.position, target.position
    return DIRECTION_KEYS[(max(-1, min(1, cell.y - origin.y)),
                           max(-1, min(1, cell.x - origin.x)))]


def best_expected(policy, snapshot, target) -> float:
    """The larger expected damage per action this chooser would deal beside ``target``."""
    options = _adjacent_options(policy, snapshot, target, _aim(snapshot, target))
    return max([score for score, _send in options]
               + [attack_expectation.melee(policy, snapshot, target)])


def attack_key(policy, snapshot, target) -> str | None:
    """The ranged answer to ``target`` (adjacent or ray-aligned), else None."""
    origin, cell = snapshot.player.position, target.position
    direction = _aim(snapshot, target)
    if origin.distance_to(cell) <= 1:
        return _strongest_adjacent_key(policy, snapshot, target, direction)
    return _first_key(policy, snapshot, target, direction)
