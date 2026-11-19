"""What a character never sells, destroys or drops (owner 2026-11-20).

Owner, verbatim: 「魔力復活の薬は魔道具術師が99Fと100Fをクリアするための非常に重要なアイテムである。
絶対に売ってはならない。」 -- the Potion of Restore Mana refills a Magic-Eater's absorbed powers
(spells-status.cpp restore_mana(magic_eater=true)).  n1-b life-411 deposited the ones it found,
and the full-Home relief took them out and sold them (11-20 02:57, 03:59, 05:36).

``never_disposed`` is the hard rule: the item reservation refuses every sale, destroy and
surplus sink for it (item_reservation ``item_reserved_by_other``), whichever owner asks.
No hengbot import beyond the model, so the reservation layer can read it.
"""
from __future__ import annotations

from typing import Any

from hengbot.model import SV_POTION_RESTORE_MANA, TVAL_POTION

PLAYER_CLASS_MAGIC_EATER = 16
# The reservation sinks that take an item out of the character's possession.
DISPOSAL_SINKS = frozenset({"sell", "destroy", "home-full-sale", "overweight-surplus", "drop"})


def never_disposed(snapshot: Any, item: Any) -> bool:
    """A Potion of Restore Mana of a Magic-Eater (known kind)."""
    return bool(snapshot is not None and snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
                and item.tval == TVAL_POTION and item.sval == SV_POTION_RESTORE_MANA
                and getattr(item, "aware", True))
