"""The Speed dose a scene takes: class 16's absorbed Speed first, else a carried potion.

Owner 2026-11-01: 「スピードの薬の購入ルールについて。スピードの杖の取り込み後、成功率が
80%以上なら以降スピードの薬の購入、持ち歩きをやめる。スピードの薬を使用する場面では代わりに
取り込んだ杖を試みる。」

The purchase and carry half is the ``me_capability.REPLACES`` row (Speed staff ->
Speed potion, ``reliable``: the displayed success rate is at least
``RELIABLE_MIN_SUCCESS``, the *Destruction* row's number).  This module is the use
half, for every scene that drank a Potion of Speed:

 * ``key``: that row's power cast in its place (me_absorbed_substitutes
   ``item_cast_key``: the row holds and the power has a charge here), else a
   carried potion (above the scene's reserve), else None (the scene as before).
 * A failed cast (the executor's ``failed`` refusal; cmd-magiceat.cpp prints
   「呪文をうまく唱えられなかった！」, spends the turn and keeps the charge) re-arms
   the scene once (``rearm``: its one-shot mark, a JSON-safe path), and on that
   floor its next ask drinks a carried potion instead of casting again.
 * A scene whose trigger holds again once the dose has run out (a reviewed
   quest plan's ``speed_potion_use_when``) passes ``renew``: when the speed
   field has shown the haste and shows it no longer on the same floor, its
   one-shot mark is re-armed (``rearm``), so the trigger asks for the next dose.
 * ``available`` / ``spare``: the dose a scene's fight model may credit.

Game (C:/hengband/src): the staff cast is ``staff_effect`` (cmd-magiceat.cpp:577)
-> SV_STAFF_SPEED ``set_acceleration(randint1(30) + (powerful ? 30 : 15))``
(cmd-item/cmd-usestaff.cpp:239-243); the potion is ``set_acceleration(randint1(25)
+ 15)``, or +5 turns when already hasted (object-use/quaff/quaff-effects.cpp:375-383).
Both are the one acceleration effect, +10 speed (player-status/player-speed.cpp:
189-190); only the duration differs (16-45 or, powerful, 31-60 turns against
16-40, without the potion's +5 extension).
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import me_absorbed_substitutes as substitutes
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_SPEED, TVAL_POTION


POTION = (TVAL_POTION, SV_POTION_SPEED)
MEMORY = "_speed_dose_memory"


@dataclass
class DoseMemory:
    pending: tuple | None = None       # (turn, owner reason, rearm) of the last cast
    failed_floor: tuple | None = None  # a cast failed here: the next ask drinks a potion
    renewal: tuple | None = None       # (floor, rearm, haste seen) of a ``renew`` dose


def _memory(policy) -> DoseMemory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = DoseMemory()
        setattr(policy, MEMORY, memory)
    return memory


def _rearm(policy, rearm) -> None:
    """Undo a scene's one-shot mark: (attribute, value) or (attribute, key, value)."""
    if rearm is None:
        return
    if len(rearm) == 2:
        setattr(policy, rearm[0], rearm[1])
        return
    container = getattr(policy, rearm[0], None)
    if container is not None:
        container[rearm[1]] = rearm[2]


def _observe_renewal(policy, snapshot, memory) -> None:
    """Re-arm a ``renew`` scene once the haste its dose gave has run out."""
    floor, rearm, seen = memory.renewal
    hasted = policy._player_hasted(snapshot)
    if floor != snapshot.floor_key:
        memory.renewal = None
    elif hasted:
        memory.renewal = (floor, rearm, True)
    elif seen:
        memory.renewal = None
        _rearm(policy, rearm)


def observe(policy, snapshot) -> None:
    """Every decision: settle the last cast (a failure re-arms its scene) and
    re-arm a ``renew`` scene whose haste has ended."""
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        return
    if memory.renewal is not None:
        _observe_renewal(policy, snapshot, memory)
    if memory.failed_floor is not None and (
            memory.failed_floor != snapshot.floor_key or policy._player_hasted(snapshot)):
        memory.failed_floor = None
    if memory.pending is None:
        return
    turn, owner, rearm = memory.pending
    if snapshot.completed_operation_owner == owner:
        refusal = (snapshot.completed_operation_receipt or {}).get("refusal")
        if isinstance(refusal, str) and refusal.startswith("failed"):
            memory.failed_floor = snapshot.floor_key
            _rearm(policy, rearm)
        memory.pending = None
    elif snapshot.turn != turn:
        memory.pending = None


def _cast_key(policy, snapshot) -> str | None:
    memory = getattr(policy, MEMORY, None)
    if memory is not None and memory.failed_floor == snapshot.floor_key:
        return None
    return substitutes.item_cast_key(policy, snapshot, POTION)


def key(policy, snapshot, reason: str, *, rearm=None, potion_reserve: int = 0,
        renew: bool = False) -> str | None:
    """The scene's Speed dose, setting ``last_reason`` (the cast's ends in
    ``CAST_SUFFIX``); None when it has none."""
    cast = _cast_key(policy, snapshot)
    if cast is not None:
        policy.last_reason = reason + substitutes.CAST_SUFFIX
        _memory(policy).pending = (snapshot.turn, policy.last_reason, rearm)
        return _renewing(policy, snapshot, cast, rearm, renew)
    potion = policy._find_exact_potion(snapshot, SV_POTION_SPEED)
    if potion is None or policy._exact_potion_count(snapshot, SV_POTION_SPEED) <= potion_reserve:
        return None
    policy.last_reason = reason
    return _renewing(policy, snapshot, reserved_item_command(policy, snapshot, "quaff", potion),
                     rearm, renew)


def _renewing(policy, snapshot, command, rearm, renew):
    """Remember a ``renew`` dose so its scene re-arms when the haste ends."""
    if renew and rearm is not None:
        _memory(policy).renewal = (snapshot.floor_key, rearm, False)
    return command


def spare(policy, snapshot, potion_reserve: int = 0) -> int:
    """The doses a fight model may spend: the potions above the reserve, at
    least one while the absorbed power serves."""
    potions = max(0, policy._exact_potion_count(snapshot, SV_POTION_SPEED) - potion_reserve)
    return max(potions, int(_cast_key(policy, snapshot) is not None))


def available(policy, snapshot) -> bool:
    return spare(policy, snapshot) > 0
