"""Item kinds the character never keeps (owner 2026-11-02).

Owner: 「1冊目、2冊目の安い本で枠を埋めるのをやめたい。拾ったら捨てて。」 and
「像、人形、モンスターボールも不要物に追加。」  The kinds are one junk class
(``unwanted-kind``) of ``_junk_class``, so the existing junk paths destroy a
carried one and never shelve or sell it.

* Figurines, statues (photographs included: tval 9 sval 50) and capture balls,
  by tval (src/object/tval-types.h FIGURINE = 8, STATUE = 9, CAPTURE = 11).
* The first and second book of every realm (sval 0 and 1; the town books of
  lib/edit/BaseitemDefinitions.jsonc), except the books of the character's own
  realms.  The realms are the character sheet's (``character.realms``, the
  periodic character response); while they are not yet observed no book is
  unwanted.
"""
from __future__ import annotations

from hengbot.model import (
    InventoryItem, TVAL_ARCANE_BOOK, TVAL_CAPTURE, TVAL_CHAOS_BOOK,
    TVAL_CRAFT_BOOK, TVAL_CRUSADE_BOOK, TVAL_DEATH_BOOK, TVAL_DEMON_BOOK,
    TVAL_FIGURINE, TVAL_HEX_BOOK, TVAL_HISSATSU_BOOK, TVAL_LIFE_BOOK,
    TVAL_MUSIC_BOOK, TVAL_NATURE_BOOK, TVAL_SORCERY_BOOK, TVAL_STATUE,
    TVAL_TRUMP_BOOK,
)

UNWANTED_TVALS = frozenset({TVAL_FIGURINE, TVAL_STATUE, TVAL_CAPTURE})
CHEAP_BOOK_SVALS = frozenset({0, 1})

# RealmType (src/realm/realm-types.h) -> its book (realm_books,
# src/player/player-realm.cpp).
REALM_BOOK_TVALS = {
    1: TVAL_LIFE_BOOK, 2: TVAL_SORCERY_BOOK, 3: TVAL_NATURE_BOOK,
    4: TVAL_CHAOS_BOOK, 5: TVAL_DEATH_BOOK, 6: TVAL_TRUMP_BOOK,
    7: TVAL_ARCANE_BOOK, 8: TVAL_CRAFT_BOOK, 9: TVAL_DEMON_BOOK,
    10: TVAL_CRUSADE_BOOK, 16: TVAL_MUSIC_BOOK, 17: TVAL_HISSATSU_BOOK,
    18: TVAL_HEX_BOOK,
}


def own_book_tvals(realms) -> frozenset[int] | None:
    """The book tvals of the character sheet's realms, or None when unreadable."""
    if not isinstance(realms, list):
        return None
    try:
        return frozenset(REALM_BOOK_TVALS[int(realm["id"])] for realm in realms
                         if int(realm["id"]) in REALM_BOOK_TVALS)
    except (KeyError, TypeError, ValueError):
        return None


def is_unwanted_kind(item: InventoryItem, own_books: frozenset[int] | None) -> bool:
    """Whether ``item`` is a kind the character never keeps."""
    if item.tval in UNWANTED_TVALS:
        return True
    return (item.is_spellbook and item.aware and item.sval in CHEAP_BOOK_SVALS
            and own_books is not None and item.tval not in own_books)
