"""A quest casts an absorbed Magic-Eater power in place of a carried item (owner 2026-10-31 18h).

Owner, for class 16 (魔道具術師):
 1. 「魔道具術師、光の杖を取り込んでいる場合、クエスト要求の光の巻物を免除する。」
    (19h: 「Q2→取り込んだ光の杖で受諾、クエスト内部で巻物要求のとき、代わりに杖で
    照らす」「光の巻物→購入を抑制」)
 4. 「岩石溶解を取り込んでいるとき、クエストの魔法棒要求の代替にできる。」
 2026-11-01 「スピードの薬を使用する場面では代わりに取り込んだ杖を試みる。」
    (the ``cast`` row of the Speed potion; speed_dose picks the dose)

Which power replaces which quest carry, and when, is the ``me_capability.REPLACES``
table (its ``Carry`` rows and ``cast`` rows); the carry count (policy_quest ``_quest_carry_count``
and ``_quest_named_item_count``) and the carry's purchase ask that table.  This
module only casts: where a quest would read or aim the carried item,
``cast_key`` composes ``m`` + kind + the power's letter (+ direction)
(``carry_cast_key`` for a carry, ``item_cast_key`` for a ``cast`` row's item) and the
caller adds ``CAST_SUFFIX`` to its own reason; me_device_attacks_input answers
that owner's prompts from ``POWERS`` exactly like a me_powers use.
"""

from __future__ import annotations

from hengbot import me_capability, me_powers
from hengbot.magic_eater_devices import power_command_refused
from hengbot.me_staff_sequence import cast_blocked
from hengbot.model import (
    SV_ROD_TELEPORT_AWAY, SV_STAFF_CURE_LIGHT, SV_STAFF_TELEPORTATION, SV_WAND_TELEPORT_AWAY,
)


# The reason suffix of a quest's absorbed-power cast (me_device_attacks_input).
CAST_SUFFIX = ":absorbed-power"


def _cast_power(ident: tuple) -> me_powers.Power:
    """The utility table's row, else the power as the list names it; a wand
    power asks for a direction (cmd-magiceat.cpp get_aim_dir), a staff's does
    not, and a rod's depends on the rod (is_aiming_rod), so a rod needs its row."""
    kind, sval = ident
    if ident in me_powers.BY_KEY:
        return me_powers.BY_KEY[ident]
    if kind == "rod":
        raise ValueError(f"a rod substitute needs its me_powers row: {ident}")
    return me_powers.Power(kind, sval, me_capability.names(kind, sval), "absorbed-power", 0, 0,
                           (), darkness_scaled=False, aimed=kind == "wand")


# Cure Light Wounds, the blindness cure a blind player casts (status_cure.absorbed_cure_key).
CURE_LIGHT = ("staff", SV_STAFF_CURE_LIGHT)
# Teleportation, the escape a blind player casts (threat_tiers.blind_teleport_key).
TELEPORTATION = ("staff", SV_STAFF_TELEPORTATION)
# Teleport Other, aimed at a monster that follows the player's teleport (teleport_follower).
TELEPORT_AWAY = (("rod", SV_ROD_TELEPORT_AWAY), ("wand", SV_WAND_TELEPORT_AWAY))


def _build_powers() -> dict:
    """The powers cast in place of an item (me_device_attacks_input answers them)."""
    powers = {ident: _cast_power(ident) for ident in me_capability.substitute_powers()}
    powers[CURE_LIGHT] = _cast_power(CURE_LIGHT)
    powers[TELEPORTATION] = _cast_power(TELEPORTATION)
    for ident in TELEPORT_AWAY:
        powers[ident] = _cast_power(ident)
    # Healing in the arena, where no potion works (arena.py); neither asks for a direction.
    # The staff's is also a ``cast`` row's (Q25, owner 2026-11-09), built above with its names.
    for kind, sval in (("rod", 9), ("staff", 18)):
        if (kind, sval) in powers:
            continue
        powers[(kind, sval)] = me_powers.BY_KEY.get((kind, sval)) or me_powers.Power(
            kind, sval, (), "absorbed-power", 0, 0, (), darkness_scaled=False, aimed=False)
    return powers


def _powers() -> dict:
    """``POWERS``, built on first use.  Building it at import time read
    ``me_powers.BY_KEY`` while me_powers could still be initializing (importing
    hengbot.destruction_use first: ... -> me_powers -> hunt_target ->
    retreat_enclosure -> sealed_pocket -> this module), an AttributeError."""
    powers = globals().get("POWERS")
    if powers is None:
        powers = globals()["POWERS"] = _build_powers()
    return powers


def __getattr__(name: str):
    # ``me_absorbed_substitutes.POWERS`` and ``from ... import POWERS`` (PEP 562).
    if name == "POWERS":
        return _powers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def owns(owner) -> bool:
    return isinstance(owner, str) and owner.endswith(CAST_SUFFIX)


def blind_castable(snapshot) -> bool:
    """Blind, and nothing else stops the ``m`` command: the game refuses only confusion
    (cmd-magiceat.cpp:463 cmd_limit_confused); the rest is ``cast_blocked``'s."""
    player = snapshot.player
    return (player.blind and snapshot.store is None
            and not (player.confused or player.hallucinated or player.paralyzed)
            and not power_command_refused(snapshot))


def cast_key(policy, snapshot, power, direction: str = "", *, blind_ok: bool = False) -> str | None:
    """``m`` + kind + letter (+ direction) when the power has a charge here.
    ``blind_ok``: a power the caller casts blind too (``blind_castable``)."""
    blocked = cast_blocked(snapshot) and not (blind_ok and blind_castable(snapshot))
    if (not me_capability.has(policy, snapshot, power.kind, power.sval) or blocked
            or me_capability.charges(policy, snapshot, power.kind, power.sval) <= 0):
        return None
    return power.key + (direction if power.aimed else "")


def carry_cast_key(policy, snapshot, category: str, name: str,
                   direction: str = "") -> str | None:
    """The substitute power where a quest reads or aims this carry's item."""
    ident = me_capability.replacing_power(me_capability.Carry(category, name))
    return None if ident is None else cast_key(policy, snapshot, _powers()[ident], direction)


def item_cast_key(policy, snapshot, target, direction: str = "") -> str | None:
    """The substitute power where a scene uses ``target``'s item: a ``cast``
    row whose condition holds (me_capability.cast_rows), with a charge."""
    row = next(me_capability.cast_rows(policy, snapshot, target), None)
    return None if row is None else cast_key(policy, snapshot, _powers()[row.power], direction)
