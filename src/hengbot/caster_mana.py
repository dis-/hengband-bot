"""A realm caster's maximum mana under a loadout: the glove and armour-weight penalties as a cost.

The supervisor 2026-11-27 (owner 「盗賊が反魔法装備をしているが、意図通りか？意図通りであるなら
魔法書を持ち歩いている理由を確認」): n1-a life-545, the Sorcery Rogue (CL23, 59 MP), wore 革グローブ
[1,+0], which takes a quarter of its maximum mana, for one point of AC.  The maximum mana is the
budget of every cast the bot plans (realm_spells: the escape reserve, the detections, the map,
Identify), so the loadout search counts what a set takes from it.

Game facts (C:/hengband, update_max_mana, src/player/player-status.cpp):

* :721-735 a class with ``has_glove_mp_penalty`` (lib/edit/ClassMagicDefinitions.jsonc ROGUE)
  wearing gloves keeps ``msp * 3 / 4`` unless the gloves give FREE_ACT, DEC_MANA or EASY_SPELL,
  or MAGIC_MASTERY or DEX with a positive pval (``glove_penalty``);
* :737-760 the armour weight: body, head, cloak, gloves and boots, and each hand's item of a tval
  above SWORD (a shield) in full; :799-810 the Rogue's weapon in either hand a third of its weight
  (integer division per item); the launcher is not counted (``armour_weight``);
* :827-858 over the class's ``armour_weight_limit`` (ROGUE 400, the weights in tenths of a pound)
  the Rogue keeps ``msp - msp * (weight - limit) / 1000`` (``CasterMana.weight_divisor``).

The rule (one place): the share of the maximum mana a loadout loses, times ``MANA_SHARE_VALUE``,
is taken off the loadout's survival/kill ratio as a negative utility (equipment_utility's
relative bonuses, warrior_loadout_evaluator).  ``MANA_SHARE_VALUE`` 0.4 makes the gloves' quarter
cost 10%: as much as full telepathy, the highest utility the owner named, and twice the
selection's 5% material threshold, so penalising gloves are worn only for a set more than ~11%
stronger in the ratio.  Ten pounds over the limit (10% of the mana) cost 4%.  The integer
rounding of the game's formula is not modelled (the share is what the formula keeps).

The arms fill rule (owner 2026-09-29 「空いた鎧の欄は必ず埋める」) does not make such a class wear
penalising gloves: only gloves without the penalty fill the slot (``fills_arms``,
equipment_optimizer.owned_armor_fill_slots); a penalising pair competes on this cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hengbot.class_roles import PLAYER_CLASS_ROGUE, casts_realm_spells

# object-enchant/tr-types.h
TR_DEX = 3
TR_MAGIC_MASTERY = 6
TR_EASY_SPELL = 39
TR_FREE_ACT = 46
TR_DEC_MANA = 70
GLOVE_EXEMPT_FLAGS = frozenset({TR_FREE_ACT, TR_DEC_MANA, TR_EASY_SPELL})
GLOVE_EXEMPT_PVAL_FLAGS = frozenset({TR_MAGIC_MASTERY, TR_DEX})
TVAL_SWORD = 23
TVAL_GLOVES = 31
GLOVE_KEPT = 3 / 4                 # player-status.cpp:733 msp = (3 * msp) / 4

ARMOUR_SLOTS = ("body", "head", "outer", "arms", "feet")
HAND_SLOTS = ("main_hand", "sub_hand")

# The relative margin a loadout loses per share of the maximum mana it takes (module docstring).
MANA_SHARE_VALUE = 0.4


@dataclass(frozen=True)
class CasterMana:
    """A class's mana penalties (ClassMagicDefinitions.jsonc and update_max_mana)."""
    glove_penalty: bool
    armour_weight_limit: int       # tenths of a pound
    weight_divisor: int            # msp -= msp * over / divisor
    weapon_weight_share: tuple[int, int]   # a weapon's weight counted as num / den


CASTER_MANA = {
    # ClassMagicDefinitions.jsonc ROGUE: has_glove_mp_penalty, armour_weight_limit 400;
    # player-status.cpp:799-810 the weapon / 3, :852-856 the divisor 1000.
    PLAYER_CLASS_ROGUE: CasterMana(True, 400, 1000, (1, 3)),
}


def caster_mana(class_id) -> CasterMana | None:
    """The penalties of a class that casts its realm's spells (class_roles), else None."""
    if not casts_realm_spells(class_id):
        return None
    return CASTER_MANA.get(class_id)


def glove_penalty(item) -> bool:
    """Gloves ``item`` (an EquipmentItem / InventoryItem) take a quarter of the mana: no
    FREE_ACT, DEC_MANA or EASY_SPELL, no MAGIC_MASTERY or DEX with a positive pval (known flags)."""
    if item.tval != TVAL_GLOVES:
        return False
    flags = item.known_flags
    if not GLOVE_EXEMPT_FLAGS.isdisjoint(flags):
        return False
    return not (item.pval > 0 and not GLOVE_EXEMPT_PVAL_FLAGS.isdisjoint(flags))


def fills_arms(item, class_id) -> bool:
    """Whether ``item`` counts toward the arms fill rule for ``class_id``: not penalising gloves
    of a class with the glove penalty."""
    profile = caster_mana(class_id)
    return not (profile is not None and profile.glove_penalty and glove_penalty(item))


def armour_weight(slots: Iterable[tuple[str, object]], profile: CasterMana) -> int:
    """update_max_mana's ``cur_wgt`` of ``slots`` ((slot, item) with ``.weight`` and ``.tval``)."""
    total = 0
    num, den = profile.weapon_weight_share
    for slot, item in slots:
        if slot in ARMOUR_SLOTS:
            total += item.weight
        elif slot in HAND_SLOTS:
            total += item.weight if item.tval > TVAL_SWORD else item.weight * num // den
    return total


def kept_share(slots: Iterable[tuple[str, object]], class_id) -> float:
    """The share of the maximum mana ``slots`` keep for ``class_id`` (1.0 for a non-caster)."""
    profile = caster_mana(class_id)
    if profile is None:
        return 1.0
    slots = tuple(slots)
    kept = 1.0
    if profile.glove_penalty and any(slot == "arms" and glove_penalty(item) for slot, item in slots):
        kept *= GLOVE_KEPT
    over = armour_weight(slots, profile) - profile.armour_weight_limit
    if over > 0:
        kept *= max(0.0, 1.0 - over / profile.weight_divisor)
    return kept


def mana_utility(loadout, class_id) -> float:
    """The loadout's (``equipment_optimizer.Loadout``) relative margin cost of the mana it takes:
    ``-MANA_SHARE_VALUE`` times the share lost; 0 for a class without these penalties."""
    slots = tuple((slot, owned.item) for slot, owned in loadout.slots)
    return -MANA_SHARE_VALUE * (1.0 - kept_share(slots, class_id))
