"""Absorbed Magic-Eater powers that stand in for carried items (owner 2026-10-31 18h).

Owner, for class 16 (魔道具術師):
 1. 「魔道具術師、光の杖を取り込んでいる場合、クエスト要求の光の巻物を免除する。」
    (19h: 「Q2→取り込んだ光の杖で受諾、クエスト内部で巻物要求のとき、代わりに杖で
    照らす」「光の巻物→購入を抑制」)
 2. 「鑑定の杖を21回取り込んだあとは鑑定の杖を購入しない。持ち物の要求からも外す。」
 4. 「岩石溶解を取り込んでいるとき、クエストの魔法棒要求の代替にできる。」
(3, absorbing a carried Stone to Mud wand, is a me_staff_sequence extra.)

Every fact is one the player saw: the power's row in the last list the game
displayed for its kind (``me_powers.observed_row``, cmd-magiceat.cpp), or,
before a list shows it, the absorption the bot observed itself
(``me_staff_sequence``'s record).  Nothing is read from game internals.

``SUBSTITUTES`` is the table: one row per quest carry (``required_force``
category and name) that an absorbed power replaces, and how --
``WAIVE``: holding the power meets the requirement whatever its charges (it
regenerates); ``CHARGES``: the power's charges count as a carried device's.
The quest carry count (policy_quest ``_quest_carry_count`` and
``_quest_named_item_count``) asks ``carry_waived`` / ``carry_charges``, so
acceptance and entry agree; a waived carry also claims no item
(``_quest_carry_target_for_item``), so it is neither bought, withdrawn from
Home nor reserved for the quest.

Identify (2): once the power's count (the list's ``max``; a staff's first
absorption sets it to the staff's charges, mind-magic-eater.cpp) reaches a
full Identify staff's base pval (21, ``me_staff_sequence.max_charges``),
``identify_staff_replaced`` holds: no Identify staff is bought
(``purchase_excluded``) and the identify-staff readiness is met
(policy_supply ``_identify_staff_ready``); identification already casts the
power (``me_staff_sequence.identify_power_command``).

Casting: where a quest would read or aim the carried item, ``cast_key``
composes ``m`` + kind + the power's letter (+ direction) and the caller adds
``CAST_SUFFIX`` to its own reason; me_device_attacks_input answers that
owner's prompts from ``POWERS`` exactly like a me_powers use.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import me_powers
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_staff_sequence import POWER_NAMES, SV_STAFF_LITE, absorbed_count as recorded_count
from hengbot.me_staff_sequence import cast_blocked, max_charges
from hengbot.model import SV_STAFF_IDENTIFY, SV_WAND_STONE_TO_MUD, TVAL_STAFF


# The reason suffix of a quest's absorbed-power cast (me_device_attacks_input).
CAST_SUFFIX = ":absorbed-power"
WAIVE = "waive"
CHARGES = "charges"

LIGHT = me_powers.BY_KEY[("staff", SV_STAFF_LITE)]
IDENTIFY = me_powers.Power("staff", SV_STAFF_IDENTIFY, POWER_NAMES[SV_STAFF_IDENTIFY],
                           "identify", 0, 0, ())
# BaseitemDefinitions id 273 (岩石溶解の魔法棒); wand_effect's stone_to_mud is aimed.
STONE_TO_MUD = me_powers.Power("wand", SV_WAND_STONE_TO_MUD, ("岩石溶解", "Stone to Mud"),
                               "stone-to-mud", 0, 0, (), aimed=True)


@dataclass(frozen=True)
class Substitute:
    category: str      # required_force group (QUEST_*.jsonc)
    name: str          # the carry's name in that group
    power: me_powers.Power
    mode: str


SUBSTITUTES = (
    Substitute("required_scrolls", "light", LIGHT, WAIVE),
    # Q2's wall_breach: one Stone to Mud charge per breach wall, like a wand's.
    Substitute("utility_tools", "wall_breach", STONE_TO_MUD, CHARGES),
)
# The powers read here, and cast in place of an item (me_device_attacks_input).
POWERS = {power.ident: power for power in (LIGHT, STONE_TO_MUD)}


def _magic_eater(snapshot) -> bool:
    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def held(policy, snapshot, power) -> bool:
    """Whether the player has seen this power absorbed (any charges)."""
    if not _magic_eater(snapshot):
        return False
    row = me_powers.observed_row(policy, power)
    return (row is not None and int(row.get("max") or 0) > 0) or (
        me_powers.recorded_charges(policy, snapshot, power) > 0)


def absorbed_count(policy, snapshot, power) -> int:
    """The power's count: the displayed list's ``max``, else the absorption seen."""
    if not _magic_eater(snapshot):
        return 0
    row = me_powers.observed_row(policy, power)
    listed = int(row.get("max") or 0) if row is not None else 0
    return max(listed, recorded_count(policy, power.sval))


def identify_staff_replaced(policy, snapshot) -> bool:
    """「鑑定の杖を21回取り込んだあと」: the count reached a full staff's charges."""
    return absorbed_count(policy, snapshot, IDENTIFY) >= max_charges(SV_STAFF_IDENTIFY)


def purchase_excluded(policy, snapshot, item) -> bool:
    """「鑑定の杖を購入しない」 once the absorbed Identify replaced the staff."""
    return (item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
            and identify_staff_replaced(policy, snapshot))


def _substitute(category: str, name: str, mode: str) -> Substitute | None:
    return next((row for row in SUBSTITUTES
                 if (row.category, row.name, row.mode) == (category, name, mode)), None)


def carry_waived(policy, snapshot, category: str, name: str) -> bool:
    """「免除する」: a held power waives this quest carry."""
    row = _substitute(category, name, WAIVE)
    return row is not None and held(policy, snapshot, row.power)


def carry_charges(policy, snapshot, category: str, name: str) -> int:
    """The charges a held power adds to this quest carry's device count."""
    row = _substitute(category, name, CHARGES)
    if row is None or not held(policy, snapshot, row.power):
        return 0
    return me_powers.charges(policy, snapshot, row.power)


def owns(owner) -> bool:
    return isinstance(owner, str) and owner.endswith(CAST_SUFFIX)


def cast_key(policy, snapshot, power, direction: str = "") -> str | None:
    """``m`` + kind + letter (+ direction) when the power has a charge here."""
    if (not _magic_eater(snapshot) or cast_blocked(snapshot)
            or me_powers.charges(policy, snapshot, power) <= 0):
        return None
    return power.key + (direction if power.aimed else "")


def carry_cast_key(policy, snapshot, category: str, name: str,
                   direction: str = "") -> str | None:
    """The substitute power where a quest reads or aims this carry's item."""
    row = next((row for row in SUBSTITUTES if (row.category, row.name) == (category, name)), None)
    return None if row is None else cast_key(policy, snapshot, row.power, direction)
