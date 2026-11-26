"""Which way each supported class is played (one reading for every class check).

Owner 2026-11-26 (verbatim): 「n1-aとn1-bは自由なキャラクタと戦略で勝利を目指すこと。」
「1体は魔道具術師以外にして」.  The supervisor chose a Rogue (盗賊) played exactly like the
Warrior: melee, a launcher and the carried staffs, wands, rods, scrolls and potions (the
Rogue's magic-device skill, class-info.cpp ``c_dev 37 / x_dev 12`` against the Warrior's
``18 / 7``, makes the carried devices reliable; the device rules read the board's skill,
destruction_means.device_success), and its Sorcery spells as one more means of the
capabilities those rules already have (``casts_realm_spells``, realm_spells).

* ``plays_as_warrior``: the classes the Warrior's rules drive (the Home catalogue errands,
  the dominated-gear disposal, the Warrior's quest plan rows).  The Magic-Eater keeps its
  own rules (``PLAYER_CLASS_MAGIC_EATER`` checks); class-table numbers that really differ
  between Warrior and Rogue (blows, shots) live in equipment_class_profile.
* ``realm_books_unusable``: the classes whose realm books the bot never reads (the
  Warrior and the Berserker have no realm), so every book is an unusable book
  (policy_helpers ``unusable-book``).  The Magic-Eater (no realm) keeps its own book rules
  (unwanted_kinds, item_fate).
* ``casts_realm_spells``: the classes that cast their realm's book spells (the Rogue, owner
  2026-11-26 「盗賊は魔法を使える。無視する戦略ならばそれも良いが、多少なり使うと大きく助けになる。」).
  Its own realm's first and second books are kept and read (realm_spells, realm_spell_book); the
  other realms' cheap books stay unwanted (unwanted_kinds) and its own third and fourth books stay
  sale loot (item_fate ``unused-book``: no spell of theirs is cast).
* ``class_row``: a strategy's ``*_by_class`` row for the class, the Warrior's row for a
  class played as the Warrior when the file names no row of its own (strategy/quests).
"""
from __future__ import annotations

from typing import Any, Mapping

PLAYER_CLASS_WARRIOR = 0  # src/player-info/class-types.h
PLAYER_CLASS_ROGUE = 3
PLAYER_CLASS_MAGIC_EATER = 16
PLAYER_CLASS_BERSERKER = 23

WARRIOR_PLAY_CLASSES = frozenset({PLAYER_CLASS_WARRIOR, PLAYER_CLASS_ROGUE})
# Classes whose realm books the bot never reads.
BOOKLESS_PLAY_CLASSES = frozenset({PLAYER_CLASS_WARRIOR, PLAYER_CLASS_BERSERKER})
# Classes that cast their realm's book spells (realm_spells).
CASTER_PLAY_CLASSES = frozenset({PLAYER_CLASS_ROGUE})


def plays_as_warrior(class_id: Any) -> bool:
    """The class the Warrior's rules drive (Warrior, Rogue)."""
    return class_id in WARRIOR_PLAY_CLASSES


def realm_books_unusable(class_id: Any) -> bool:
    """Every realm book is unusable to this class as the bot plays it."""
    return class_id in BOOKLESS_PLAY_CLASSES


def casts_realm_spells(class_id: Any) -> bool:
    """The class casts its realm's book spells as the bot plays it (the Rogue)."""
    return class_id in CASTER_PLAY_CLASSES


def class_row(rows: Mapping[str, Any] | None, class_id: Any, default: Any = None) -> Any:
    """``rows[str(class_id)]``; a class played as the Warrior falls back to the Warrior's row."""
    if not rows:
        return default
    key = str(class_id)
    if key in rows:
        return rows[key]
    if plays_as_warrior(class_id) and str(PLAYER_CLASS_WARRIOR) in rows:
        return rows[str(PLAYER_CLASS_WARRIOR)]
    return default


def class_listed(classes, class_id: Any) -> bool:
    """``class_id`` in a strategy's class list; a class played as the Warrior is listed with it."""
    classes = tuple(classes or ())
    return class_id in classes or (plays_as_warrior(class_id) and PLAYER_CLASS_WARRIOR in classes)
