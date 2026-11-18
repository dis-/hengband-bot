"""Item identity: the named readings of "is this the same item".

2026-11-18 whole-bot maintainability review S1 / (a)-1: the bot compared items
by eight hand-built definitions (the display name as-is, the name with the
trailing ``{...}`` block dropped, every trailing block dropped, every block
dropped, ...).  Each reading lives here under its own name so a caller says
which one it means; ``scripts/item_identity_lint.py`` rejects brace-stripping
regexes and hand-built ``(name, tval, ...)`` identity tuples elsewhere.

The readings deliberately stay distinct: two copies that answered differently
before keep answering differently (the review's Q1 decides whether to merge
them).

Display name as-is
    ``display_signature`` (``policy._item_signature``): name, tval, sval.  The
    sale ``{@1}``, a discount, ``{並}``, the Q34 mark and ammo damage text are
    all part of it.
Last trailing block dropped
    ``without_trailing_block`` / ``sale_identity`` /
    ``sale_identity_of_signature`` (``policy_shop._sale_item_identity``):
    one whitespace-preceded ``{...}`` at the end of the name is dropped.
Last trailing block dropped, whitespace optional
    ``without_trailing_block_loose`` (``lamp_fuel._lantern_identity``).
Every trailing block dropped
    ``without_trailing_blocks`` / ``unidentified_identity``
    (``quest_navigator._unidentified_identity``).
Every block dropped
    ``without_any_block`` (``policy_instore.shelf_item_name``).
Player inscription dropped
    ``without_player_inscription``
    (``equipment_optimizer._without_player_inscription``).
Name-free
    ``stable_identity`` (``equipment_mutation.stable_identity``) and
    ``kind`` (tval, sval).
"""

from __future__ import annotations

import re
from typing import Any


_TRAILING_BLOCK = re.compile(r"\s+\{[^{}]*\}\s*$")
_TRAILING_BLOCK_LOOSE = re.compile(r"\s*\{[^{}]*\}\s*$")
_TRAILING_BLOCKS = re.compile(r"(\s*\{[^{}]*\})+\s*$")
_ANY_BLOCK = re.compile(r"\s*\{[^{}]*\}")


def display_signature(item: Any) -> tuple[str, int, int]:
    """The display name as-is with its kind: ``(name, tval, sval)``."""
    return (item.name, item.tval, item.sval)


def kind(item: Any) -> tuple[int, int]:
    """The item kind only: ``(tval, sval)``."""
    return (item.tval, item.sval)


def without_trailing_block(name: str) -> str:
    """The name with one whitespace-preceded trailing ``{...}`` block dropped."""
    return _TRAILING_BLOCK.sub("", name)


def sale_identity(item: Any) -> tuple[str, int, int]:
    """``display_signature`` with the trailing inscription/discount block dropped.

    Live snapshots expose inscription=None while appending the inscription to
    the display name; inscribing must not change the identity owned by the
    pending two-stage sale.
    """
    return (without_trailing_block(item.name), item.tval, item.sval)


def sale_identity_of_signature(signature: tuple[str, int, int]) -> tuple[str, int, int]:
    """``sale_identity`` of the item a recorded ``display_signature`` named."""
    return (without_trailing_block(signature[0]), signature[1], signature[2])


def without_trailing_block_loose(name: str) -> str:
    """The name with one trailing ``{...}`` block dropped, no space required."""
    return _TRAILING_BLOCK_LOOSE.sub("", name)


def without_trailing_blocks(name: str) -> str:
    """The name with every trailing ``{...}`` block dropped."""
    return _TRAILING_BLOCKS.sub("", name)


def unidentified_identity(item: Any) -> tuple[int, int, str]:
    """A carried unidentified item's identity, stable when a feeling appears.

    The display name gains ``{並}`` (a pseudo-ID feeling) or an inscription
    block later; strip trailing brace blocks so the item stays the same one.
    """
    return (item.tval, item.sval, without_trailing_blocks(item.name))


def without_any_block(name: str) -> str:
    """The name with every ``{...}`` block dropped, wherever it stands."""
    return _ANY_BLOCK.sub("", name).strip()


def without_player_inscription(name: str, inscription: str) -> str:
    """The display name without the player's own inscription.

    flavor-describer.cpp describe_inscription appends the inscription (up to
    a '#', flavor-util.cpp get_inscription) as the last part of the closing
    `` {...}`` block, after ", " when the block also shows a feeling, a
    discount or the ability abbreviation.  A '%' inscription expands into
    those abbreviations, so its name is kept whole.
    """
    shown = inscription.split("#", 1)[0]
    head, separator, block = name.rpartition(" {")
    if not shown or "%" in inscription or not separator or not block.endswith("}"):
        return name
    inner = block[:-1]
    if inner == shown:
        return head
    if inner.endswith(", " + shown):
        return f"{head} {{{inner[:-len(shown) - 2]}}}"
    return name


def stable_identity(item) -> tuple | None:
    """What identifies this very item across boards, and nothing mutable.

    Base kind (tval, and sval once the flavor is aware), weight, and the
    ego/artifact class once the item is known.  Bonuses (disenchantment),
    charges, fuel, inscription, learned flags and the display name all change
    without any equipment command and are never part of it.  Knowledge-gated
    fields are None while unknown, so wearing an item that identifies it on
    the spot still matches (``equipment_mutation.same_item``).
    """
    if item is None:
        return None
    aware = getattr(item, "aware", True)
    known = getattr(item, "known", True)
    return (
        getattr(item, "tval", None),
        getattr(item, "weight", None),
        getattr(item, "sval", None) if aware else None,
        (
            bool(getattr(item, "is_ego", False)),
            bool(getattr(item, "is_artifact", False)),
        ) if known else None,
    )


def shelf_identity(item: Any) -> tuple[str, int, int]:
    """A shelf row's identity: ``without_any_block`` name with its kind."""
    return (without_any_block(item.name), item.tval, item.sval)
