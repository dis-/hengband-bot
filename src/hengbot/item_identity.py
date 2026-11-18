"""Item identity: the named readings of "is this the same item".

2026-11-18 whole-bot maintainability review S1 / (a)-1: the bot compared items
by eight hand-built definitions (the display name as-is, the name with the
trailing ``{...}`` block dropped, every trailing block dropped, every block
dropped, ...).  Each reading lives here under its own name so a caller says
which one it means; ``scripts/item_identity_lint.py`` rejects brace-stripping
regexes and hand-built ``(name, tval, ...)`` identity tuples elsewhere.

The readings deliberately stay distinct: two copies that answered differently
before keep answering differently.  What the bot remembers of an item is read
by one of them, the memory reading below (the review's Q1).

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
Remembered item (owner 2026-11-18, review Q1 「印や割引だけ違えば同じ品」)
    ``memory_identity`` / ``memory_identity_of_signature`` / ``memory_name``:
    the reading every remembered item state stores and compares by (what was
    refused for sale, refused by the Home, found unidentifiable, deferred, the
    pending take, ...).  It is the display signature with the player's own
    inscription, the discount and the ability abbreviation dropped, and the
    pseudo-ID feeling kept; see ``memory_name``.  ``MemorySignatures``,
    ``MemorySignatureMap`` and ``MemorySignatureList`` are the containers the
    remembered states are held in: they apply the reading to everything they
    hold and are asked about, so ``display_signature(item) in remembered``
    answers by the memory reading.  A letter is still chosen from a real stack
    by ``remembered_stack`` (the exact display name first).
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


# --------------------------------------------------------------------------
# The remembered item (owner 2026-11-18, review Q1).
#
# C:/hengband/src flavor/flavor-describer.cpp describe_inscription closes the
# display name with one `` {...}`` block holding, in this order and joined by
# ", ": the feeling (describe_item_feeling: a game_inscriptions word of
# flavor/flag-inscriptions-table.cpp, or 呪われている/未鑑定/空/未判明), the
# discount ("N%引き" / "N% off", hidden when an abbreviation or a player
# inscription is shown), the ability abbreviation (describe_ability_abbrev,
# only on a fully known item with abbrev_all/abbrev_extra) and the player
# inscription (get_inscription, up to a '#').  Nothing follows the block.
#
# The memory reading keeps the base name (kind, pluses, ego/artifact name,
# charges, the ammo damage text) and the feeling: a feeling is the game's
# verdict on the item ({並} and {高級品} are different items to the bot).  It
# drops the discount and the player inscription (the sale {@1}, the teleport
# suppression {.}, the Q34 mark, HEAVY_CURSE): the owner's decision is that
# these never make another item.  The ability abbreviation is dropped with
# them: from the name alone it cannot be told apart from a player
# inscription, a recorded signature carries the name alone, and the reading
# must give one answer for an item and for its recorded signature.  The
# abbreviation is shown only on a fully known item, whose name already
# carries its ego or artifact name and pluses.

# describe_item_feeling's words, in both languages.
_FEELINGS = frozenset({
    "壊れている", "恐ろしい", "無価値", "呪われている", "上質以上", "並", "上質", "高級品",
    "特別製", "未鑑定", "空", "未判明",
    "broken", "terrible", "worthless", "cursed", "uncursed", "average", "good", "excellent",
    "special", "unidentified", "empty", "tried",
})


def memory_name(name: str) -> str:
    """The name a remembered item is known by: the closing block keeps only its feeling.

    ``"鉄の矢 (99) {50%引き, @1}"`` and ``"鉄の矢 (99) {@1}"`` are ``"鉄の矢 (99)"``;
    ``"セスタス [5] {並, Q34}"`` is ``"セスタス [5] {並}"``.  A name without a closing
    block is itself.
    """
    if not name.endswith("}"):
        return name
    head, separator, block = name.rpartition(" {")
    inner = block[:-1]
    if not separator or "{" in inner or "}" in inner:
        return name
    first = inner.split(", ", 1)[0]
    return f"{head} {{{first}}}" if first in _FEELINGS else head


def memory_identity(item: Any) -> tuple[str, int, int]:
    """``display_signature`` read as a remembered item: ``(memory_name, tval, sval)``."""
    return (memory_name(item.name), item.tval, item.sval)


def memory_identity_of_signature(signature: Any) -> Any:
    """``memory_identity`` of the item a recorded ``display_signature`` named.

    Anything that is not a ``(name, tval, sval)`` signature is returned as it is,
    so a container holding an odd entry still holds it.
    """
    if (isinstance(signature, tuple) and len(signature) == 3
            and isinstance(signature[0], str)):
        memory = memory_name(signature[0])
        return signature if memory == signature[0] else (memory, signature[1], signature[2])
    return signature


def same_memory(first: Any, second: Any) -> bool:
    """Whether two recorded signatures name the same remembered item (None only None)."""
    if first is None or second is None:
        return first is second
    return memory_identity_of_signature(first) == memory_identity_of_signature(second)


def remembered_stack(items: Any, remembered: Any, signature_of: Any = display_signature) -> Any:
    """The real stack a remembered signature names, or None.

    The stack showing exactly the remembered display name comes first, so a
    letter keeps addressing the stack it was chosen from; only when no stack
    shows that name (it gained or lost an inscription or a discount) is the
    first stack of the same remembered item chosen.
    """
    if remembered is None:
        return None
    candidates = list(items)
    for item in candidates:
        if signature_of(item) == remembered:
            return item
    memory = memory_identity_of_signature(remembered)
    for item in candidates:
        if memory_identity_of_signature(signature_of(item)) == memory:
            return item
    return None


_m = memory_identity_of_signature


class MemorySignatures(set):
    """A remembered set of items: holds and answers by ``memory_identity_of_signature``.

    A plain ``set`` restored from an older checkpoint becomes one through
    ``remembered_set``.  Set algebra whose receiver is a plain set
    (``plain.issubset(remembered)``) would bypass the reading;
    ``item_identity_lint`` rejects it.
    """

    def __init__(self, iterable: Any = ()) -> None:
        super().__init__(_m(signature) for signature in iterable)

    def __reduce__(self):
        return (type(self), (list(set.__iter__(self)),), getattr(self, "__dict__", None) or None)

    def __contains__(self, signature: Any) -> bool:
        try:
            return set.__contains__(self, _m(signature))
        except TypeError:
            return False

    def add(self, signature: Any) -> None:
        set.add(self, _m(signature))

    def discard(self, signature: Any) -> None:
        set.discard(self, _m(signature))

    def remove(self, signature: Any) -> None:
        set.remove(self, _m(signature))

    def update(self, *iterables: Any) -> None:
        for iterable in iterables:
            set.update(self, (_m(signature) for signature in iterable))

    def difference_update(self, *iterables: Any) -> None:
        for iterable in iterables:
            set.difference_update(self, {_m(signature) for signature in iterable})

    def intersection_update(self, *iterables: Any) -> None:
        for iterable in iterables:
            set.intersection_update(self, {_m(signature) for signature in iterable})

    def copy(self) -> MemorySignatures:
        return type(self)(set.__iter__(self))

    def issubset(self, other: Any) -> bool:
        return set.issubset(self, {_m(signature) for signature in other})

    def issuperset(self, other: Any) -> bool:
        return set.issuperset(self, {_m(signature) for signature in other})

    def isdisjoint(self, other: Any) -> bool:
        return set.isdisjoint(self, {_m(signature) for signature in other})

    def intersection(self, *others: Any) -> MemorySignatures:
        result = self.copy()
        result.intersection_update(*others)
        return result

    def difference(self, *others: Any) -> MemorySignatures:
        result = self.copy()
        result.difference_update(*others)
        return result

    def union(self, *others: Any) -> MemorySignatures:
        result = self.copy()
        result.update(*others)
        return result

    __and__ = intersection
    __sub__ = difference
    __or__ = union


class MemorySignatureMap(dict):
    """A remembered map keyed by items: keys are ``memory_identity_of_signature``."""

    def __init__(self, items: Any = ()) -> None:
        super().__init__()
        pairs = items.items() if isinstance(items, dict) else items
        for key, value in pairs:
            dict.__setitem__(self, _m(key), value)

    def __reduce__(self):
        return (type(self), (list(dict.items(self)),), getattr(self, "__dict__", None) or None)

    def __contains__(self, key: Any) -> bool:
        try:
            return dict.__contains__(self, _m(key))
        except TypeError:
            return False

    def __getitem__(self, key: Any) -> Any:
        return dict.__getitem__(self, _m(key))

    def __setitem__(self, key: Any, value: Any) -> None:
        dict.__setitem__(self, _m(key), value)

    def __delitem__(self, key: Any) -> None:
        dict.__delitem__(self, _m(key))

    def get(self, key: Any, default: Any = None) -> Any:
        return dict.get(self, _m(key), default)

    def pop(self, key: Any, *default: Any) -> Any:
        return dict.pop(self, _m(key), *default)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        return dict.setdefault(self, _m(key), default)

    def update(self, *others: Any, **kwargs: Any) -> None:
        for other in others:
            pairs = other.items() if isinstance(other, dict) else other
            for key, value in pairs:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def copy(self) -> MemorySignatureMap:
        return type(self)(dict.items(self))


class MemorySignatureList(list):
    """A remembered queue of items.

    It keeps the recorded display signatures (they address stacks) and answers
    ``in``, ``remove``, ``index`` and ``count`` by ``memory_identity_of_signature``;
    ``remove`` takes the entry with the exact signature first.
    """

    def __reduce__(self):
        return (type(self), (list(list.__iter__(self)),), getattr(self, "__dict__", None) or None)

    def __contains__(self, signature: Any) -> bool:
        memory = _m(signature)
        return any(_m(entry) == memory for entry in list.__iter__(self))

    def index(self, signature: Any, *bounds: Any) -> int:
        memory = _m(signature)
        start = bounds[0] if bounds else 0
        stop = bounds[1] if len(bounds) > 1 else len(self)
        for position in range(start, min(stop, len(self))):
            if _m(list.__getitem__(self, position)) == memory:
                return position
        raise ValueError(f"{signature!r} is not in the remembered list")

    def remove(self, signature: Any) -> None:
        if list.__contains__(self, signature):
            list.remove(self, signature)
        else:
            del self[self.index(signature)]

    def count(self, signature: Any) -> int:
        memory = _m(signature)
        return sum(_m(entry) == memory for entry in list.__iter__(self))

    def copy(self) -> MemorySignatureList:
        return type(self)(list.__iter__(self))


def remembered_set(value: Any) -> MemorySignatures:
    """A restored remembered set as ``MemorySignatures`` (old checkpoints hold a plain set)."""
    if isinstance(value, MemorySignatures):
        return value
    return MemorySignatures(value or ())


def remembered_map(value: Any) -> MemorySignatureMap:
    """A restored remembered map as ``MemorySignatureMap``."""
    if isinstance(value, MemorySignatureMap):
        return value
    return MemorySignatureMap(value or {})


def remembered_list(value: Any) -> MemorySignatureList:
    """A restored remembered queue as ``MemorySignatureList``."""
    if isinstance(value, MemorySignatureList):
        return value
    return MemorySignatureList(value or [])
