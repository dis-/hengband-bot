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
from hengbot.me_staff_sequence import cast_blocked


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


# The powers cast in place of an item (me_device_attacks_input answers them).
POWERS = {ident: _cast_power(ident) for ident in me_capability.substitute_powers()}
# Healing in the arena, where no potion works (arena.py); neither asks for a direction.
for _kind, _sval in (("rod", 9), ("staff", 18)):
    POWERS[(_kind, _sval)] = me_powers.BY_KEY.get((_kind, _sval)) or me_powers.Power(
        _kind, _sval, (), "absorbed-power", 0, 0, (), darkness_scaled=False, aimed=False)


def owns(owner) -> bool:
    return isinstance(owner, str) and owner.endswith(CAST_SUFFIX)


def cast_key(policy, snapshot, power, direction: str = "") -> str | None:
    """``m`` + kind + letter (+ direction) when the power has a charge here."""
    if (not me_capability.has(policy, snapshot, power.kind, power.sval) or cast_blocked(snapshot)
            or me_capability.charges(policy, snapshot, power.kind, power.sval) <= 0):
        return None
    return power.key + (direction if power.aimed else "")


def carry_cast_key(policy, snapshot, category: str, name: str,
                   direction: str = "") -> str | None:
    """The substitute power where a quest reads or aims this carry's item."""
    ident = me_capability.replacing_power(me_capability.Carry(category, name))
    return None if ident is None else cast_key(policy, snapshot, POWERS[ident], direction)


def item_cast_key(policy, snapshot, target, direction: str = "") -> str | None:
    """The substitute power where a scene uses ``target``'s item: a ``cast``
    row whose condition holds (me_capability.waiving_rows), with a charge."""
    row = next((row for row in me_capability.waiving_rows(policy, snapshot, target)
                if row.cast), None)
    return None if row is None else cast_key(policy, snapshot, POWERS[row.power], direction)
