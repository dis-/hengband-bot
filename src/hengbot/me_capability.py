"""What the Magic-Eater (class 16) has absorbed, and what an absorbed power replaces.

#47 maintainability round 2 (N1).  Owner rules for the whole bot: 「今後条件を
追加する可能性があること、取り込み魔法道具は今後も増えることに留意して保守性を
維持するように作って。」 (2026-10-31) and 「修正の際にも保守性が向上するように
努めて」 (2026-10-28).

Evidence (the one rule every reader uses; every fact is one the player saw):
 * the power's row in the last list the game displayed for its kind
   (cmd-item/cmd-magiceat.cpp lists only powers with a count;
   me_device_attacks.observe_lists keeps the last list of each kind, for
   class 16 only), or
 * the absorption the bot observed itself: the staff sequence's record
   (``MeStaffSequence.absorbed``), keyed by ``record_key(kind, sval)``.
A list without the row predates the absorption (mind-magic-eater.cpp only
adds to a power's count, so an absorbed power stays listed), so the record
still serves then.  Checkpoints written before #47 N1 keyed the stage staffs
by their int sval; ``migrate`` moves them to the one key form when read.

Facts about one power, keyed by (kind, sval) ("staff", "wand", "rod"):
 ``absorbed``          the evidence above (no class check: the board is not needed)
 ``has``               class 16 and ``absorbed``
 ``count``             the power's count: the displayed ``max``, else the record
 ``charges``           usable now: the displayed row (a rod's count less the
                       charging ones), else ``recorded_charges``
 ``recorded_charges``  the record's count, but 0 on a board whose displayed
                       list shows the power empty (it regenerates, so a later
                       board serves it again)

``REPLACES`` is the table of what an absorbed power stands in for: one row
per (power, replaced item kind or quest carry).  A row either waives the
item (``replaced_by_absorbed``, for the uses it names: ``PURCHASE`` no
purchase path buys it, ``ORDER`` no pick of the shop's ordinary buy order
takes its kind, ``CANDIDATE`` it is no ordinary shop candidate, ``NEED`` a
requirement for it is met) or adds the power's charges to the
item's count (``replacing_charges``, read as ``AMOUNT`` names), when its
named condition (``WHEN``) holds.  The purchase, supply, quest-carry and
identification code ask these two functions; adding a device that replaces
an item is one row, a new condition one predicate in ``WHEN``.  The cast in
place of the item (a quest carry, or a ``cast`` row's item) is
me_absorbed_substitutes (``replacing_power``, ``substitute_powers``).
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import me_device_policy
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_SCROLL_DETECT_TREASURE, SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE,
    SV_POTION_SPEED, SV_STAFF_DESTRUCTION, SV_STAFF_DETECT_GOLD, SV_STAFF_IDENTIFY,
    SV_STAFF_LITE, SV_STAFF_REMOVE_CURSE, SV_STAFF_SPEED, SV_WAND_STONE_TO_MUD,
    TVAL_POTION, TVAL_SCROLL, TVAL_STAFF,
)


# -- the evidence ---------------------------------------------------------------

def record_key(kind: str, sval: int) -> str:
    """The absorption record's key of a power ("staff:5"; JSON-safe in captures)."""
    return f"{kind}:{sval}"


def _migrated(key) -> str:
    # Before #47 N1 the stage staffs were keyed by their int sval.
    return record_key("staff", key) if isinstance(key, int) else key


def migrate(sequence) -> None:
    """Move a restored record's old int keys to ``record_key`` (in place)."""
    for name in ("absorbed", "empty_turn"):
        table = getattr(sequence, name)
        if any(not isinstance(key, str) for key in table):
            setattr(sequence, name, {_migrated(key): value for key, value in table.items()})


def _record(policy):
    sequence = getattr(policy, "_me_staff_sequence", None)
    if sequence is not None:
        migrate(sequence)
    return sequence


def recorded(policy) -> dict:
    """record_key -> the count the record holds."""
    sequence = _record(policy)
    return sequence.absorbed if sequence is not None else {}


def names(kind: str, sval: int) -> tuple:
    """The power list's name (ja, en): the device policy table's row."""
    tval = next(tval for tval, each in me_device_policy.KINDS.items() if each == kind)
    return me_device_policy.devices()[(tval, sval)].names


def observed_row(policy, kind: str, sval: int) -> dict | None:
    """The power's row in the last list the game displayed for its kind."""
    lists = getattr(policy, "_me_device_lists", None) or {}
    if kind not in lists:
        return None
    listed = names(kind, sval)
    return next((row for row in lists[kind][1] if row.get("name") in listed), None)


def _magic_eater(snapshot) -> bool:
    """Class 16; ``None`` (a caller without a board) reads the evidence alone,
    which only class 16 ever records."""
    return snapshot is None or snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def absorbed(policy, kind: str, sval: int) -> bool:
    """The power is in a displayed list or in the absorption record."""
    return observed_row(policy, kind, sval) is not None or record_key(kind, sval) in recorded(policy)


def has(policy, snapshot, kind: str, sval: int) -> bool:
    return _magic_eater(snapshot) and absorbed(policy, kind, sval)


def count(policy, snapshot, kind: str, sval: int) -> int:
    """The power's count: the displayed list's ``max``, else the record."""
    if not _magic_eater(snapshot):
        return 0
    row = observed_row(policy, kind, sval)
    listed = int(row.get("max") or 0) if row is not None else 0
    return max(listed, recorded(policy).get(record_key(kind, sval), 0))


def recorded_charges(policy, snapshot, kind: str, sval: int) -> int:
    """The record's count, 0 on a board whose displayed list shows it empty.

    The list is read only when a power is cast or browsed; a power seen empty
    on this board serves nothing until game time passes (it regenerates, and
    an inn rest refills it).
    """
    if snapshot is None or not _magic_eater(snapshot):
        return 0
    key = record_key(kind, sval)
    count_ = recorded(policy).get(key)
    if count_ is None:
        return 0
    sequence = policy._me_staff_sequence
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") == kind:
        for row in listed.get("rows", ()):
            if row.get("name") in names(kind, sval) and row.get("current") == 0:
                sequence.empty_turn[key] = snapshot.turn
    return 0 if sequence.empty_turn.get(key) == snapshot.turn else count_


def charges(policy, snapshot, kind: str, sval: int) -> int:
    """Usable charges: the displayed row, else ``recorded_charges``."""
    row = observed_row(policy, kind, sval)
    if row is None:
        return recorded_charges(policy, snapshot, kind, sval)
    if kind == "rod":
        charging, count_ = row.get("charging"), row.get("max")
        return count_ - charging if isinstance(charging, int) and isinstance(count_, int) else 0
    current = row.get("current")
    return current if isinstance(current, int) else 0


# -- what an absorbed power replaces ----------------------------------------------

@dataclass(frozen=True)
class Kind:
    """An item kind; ``sval`` None is every sval of the tval."""
    tval: int
    sval: int | None


@dataclass(frozen=True)
class Carry:
    """A quest carry: its ``required_force`` group (QUEST_*.jsonc) and name."""
    category: str
    name: str


# No purchase path buys the item: not a purchase rung, the needs stage, the
# Identify swap, nor (with ORDER and CANDIDATE) the ordinary buy order.
PURCHASE = "purchase"
# No pick of the shop's ordinary buy order (its candidates and its direct
# picks) takes a shelf row of the item's kind: the shop's excluded classes,
# which every pick lets the Identify swap pass.
ORDER = "order"
CANDIDATE = "candidate"  # not one of the shop's ordinary purchase candidates
NEED = "need"            # a requirement for the item (supply, identification, quest) is met
EVERY_USE = frozenset({PURCHASE, ORDER, CANDIDATE, NEED})

# The ``reliable`` condition's displayed success rate, the owner's one number for
# both rows that use it: 2026-10-31 「*破壊*の杖のみ、成功率が80%以上なら取り込んだ
# 魔力を要求に数える」 and 2026-11-01 「スピードの杖の取り込み後、成功率が80%以上なら…」.
RELIABLE_MIN_SUCCESS = 80


@dataclass(frozen=True)
class Replacement:
    power: tuple | None     # (kind, sval); None: the item's own kind (the staff sequence's)
    replaces: Kind | Carry
    when: str = "held"      # a WHEN predicate
    amount: str | None = None  # an AMOUNT reading: charges count as the item's; None waives it
    uses: frozenset = EVERY_USE  # what a waiving row answers
    cast: bool = False      # a scene casts the power where it would use the item


def _held(policy, snapshot, row, target) -> bool:
    return has(policy, snapshot, *row.power)


def _full_count(policy, snapshot, row, target) -> bool:
    """The count reached a full staff's charges (a staff's first absorption
    sets it to the staff's charges, mind-magic-eater.cpp)."""
    from hengbot.me_staff_sequence import max_charges

    return count(policy, snapshot, *row.power) >= max_charges(row.power[1])


def _reliable(policy, snapshot, row, target) -> bool:
    """The displayed success rate is at least ``RELIABLE_MIN_SUCCESS`` (only
    the displayed list prints the failure percent, cmd-magiceat.cpp)."""
    entry = observed_row(policy, *row.power)
    return (_magic_eater(snapshot) and entry is not None
            and int(entry.get("success") or 0) >= RELIABLE_MIN_SUCCESS)


def _staff_sequence(policy, snapshot, row, target) -> bool:
    """「2本目は買わない」: after Q1 the staff sequence alone buys its staffs
    (asked of a shelf row; a kind alone names no shelf row)."""
    from hengbot.me_staff_sequence import purchase_excluded

    return not isinstance(target, (Kind, tuple)) and purchase_excluded(policy, snapshot, target)


def _stage_staff(policy, snapshot, row, target) -> bool:
    """After Q1 the ordinary order takes no staff of a stage reached so far,
    but the Identify swap (asked of a shelf row)."""
    from hengbot.me_staff_sequence import order_excluded

    return not isinstance(target, (Kind, tuple)) and order_excluded(policy, snapshot, target)


WHEN = {
    "held": _held,
    "full-count": _full_count,
    "reliable": _reliable,
    "staff-sequence": _staff_sequence,
    "stage-staff": _stage_staff,
}
AMOUNT = {
    "charges": lambda policy, snapshot, kind, sval: max(0, charges(policy, snapshot, kind, sval)),
}

REPLACES = (
    # 2026-10-30 「2本目は買わない」: the sequence's own purchase rung buys them.  First:
    # its predicate also reads a displayed staff list into the record
    # (me_staff_sequence.read_powers), before any other row of a staff is asked.
    Replacement(None, Kind(TVAL_STAFF, None), when="staff-sequence", uses=frozenset({CANDIDATE})),
    # After Q1 no pick of the ordinary order takes a stage staff (b9ec9b4a9; the
    # sequence's own rung buys them), 2026-11-01 21h 7 「表へ移す（入れ替えのための
    # 買い直しの例外も表の条件に）」: but the Identify swap.
    Replacement(None, Kind(TVAL_STAFF, None), when="stage-staff", uses=frozenset({ORDER})),
    # 2026-10-31 18h 1 「光の杖を取り込んでいる場合、クエスト要求の光の巻物を免除する」
    # (「光の巻物→購入を抑制」: a waived carry claims no scroll).
    Replacement(("staff", SV_STAFF_LITE), Carry("required_scrolls", "light")),
    # 4 「岩石溶解を取り込んでいるとき、クエストの魔法棒要求の代替にできる」: one
    # charge per breach wall, like a wand's.
    Replacement(("wand", SV_WAND_STONE_TO_MUD), Carry("utility_tools", "wall_breach"),
                amount="charges"),
    # 5 「*破壊*の杖のみ、成功率が80%以上なら取り込んだ魔力を要求に数える」 (the 50F+ gate).
    # ``cast``: destruction_use casts it (owner 2026-11-04).
    Replacement(("staff", SV_STAFF_DESTRUCTION), Kind(TVAL_STAFF, SV_STAFF_DESTRUCTION),
                when="reliable", amount="charges", cast=True),
    # 2026-11-01 「スピードの杖の取り込み後、成功率が80%以上なら以降スピードの薬の購入、
    # 持ち歩きをやめる。スピードの薬を使用する場面では代わりに取り込んだ杖を試みる。」
    # (the scenes' dose: speed_dose).
    Replacement(("staff", SV_STAFF_SPEED), Kind(TVAL_POTION, SV_POTION_SPEED),
                when="reliable", cast=True),
    # 2026-10-30 「以降、鑑定と財宝感知は取り込みで賄う」.
    Replacement(("staff", SV_STAFF_IDENTIFY), Kind(TVAL_STAFF, SV_STAFF_IDENTIFY),
                uses=frozenset({NEED})),
    # 2026-11-01 21h 5 「今残っている回数で数える」: the displayed current charges
    # first, like every other power (the record only when no list was read).
    Replacement(("staff", SV_STAFF_DETECT_GOLD), Kind(TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
                amount="charges"),
    # 2026-10-31 18h 2 「鑑定の杖を21回取り込んだあとは鑑定の杖を購入しない。持ち物の要求からも外す。」
    # 2026-11-01 21h 6 「どちらの流れでも買わない」 (every use, like the two scroll rows).
    Replacement(("staff", SV_STAFF_IDENTIFY), Kind(TVAL_STAFF, SV_STAFF_IDENTIFY),
                when="full-count"),
    # 2026-10-31 night 「該当の杖を取り込んだら上位鑑定と上位解呪の巻物は以降購入せず
    # 強力発動で対応する」 (me_powerful_activation casts them).
    Replacement(("staff", SV_STAFF_IDENTIFY), Kind(TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY)),
    Replacement(("staff", SV_STAFF_REMOVE_CURSE), Kind(TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)),
)


def _target(target) -> Kind | Carry:
    """A Carry, an item (``tval``/``sval``) or a (tval, sval) pair."""
    if isinstance(target, (Kind, Carry)):
        return target
    if isinstance(target, tuple):
        return Kind(*target)
    return Kind(target.tval, target.sval)


def _rows(target):
    wanted = _target(target)
    for row in REPLACES:
        if isinstance(row.replaces, Carry):
            if row.replaces == wanted:
                yield row
        elif (isinstance(wanted, Kind) and row.replaces.tval == wanted.tval
              and row.replaces.sval in (None, wanted.sval)):
            yield row


def waiving_rows(policy, snapshot, target, use: str = NEED):
    """The waiving rows for ``target`` that answer ``use`` and whose condition holds."""
    return (row for row in _rows(target) if row.amount is None and use in row.uses
            and WHEN[row.when](policy, snapshot, row, target))


def replaced_by_absorbed(policy, snapshot, target, use: str = NEED) -> bool:
    """``target`` (an item, a (tval, sval) pair or a ``Carry``) is not bought
    (``PURCHASE``, ``CANDIDATE``) or its requirement is met (``NEED``)."""
    return next(waiving_rows(policy, snapshot, target, use), None) is not None


def replacing_charges(policy, snapshot, target) -> int:
    """The charges the counting rows for ``target`` add to the item's count."""
    return sum(AMOUNT[row.amount](policy, snapshot, *row.power) for row in _rows(target)
               if row.amount is not None and WHEN[row.when](policy, snapshot, row, target))


def replacing_power(target) -> tuple | None:
    """(kind, sval) of the first row's power for ``target`` (a quest casts it)."""
    return next((row.power for row in _rows(target) if row.power is not None), None)


def substitute_powers() -> tuple:
    """(kind, sval) of every power cast in place of an item: a quest carry
    row's, or a ``cast`` row's."""
    return tuple(dict.fromkeys(row.power for row in REPLACES
                               if isinstance(row.replaces, Carry) or row.cast))


def force_count(policy, snapshot, force: dict, name: str) -> int:
    """``force``'s required count of a ``FORCE_KINDS`` item, 0 once an absorbed
    power meets it (acceptance, entry, purchase and the town route read this)."""
    if replaced_by_absorbed(policy, snapshot, FORCE_KINDS[name]):
        return 0
    return int(force.get(name, 0))


# required_force names (QUEST_*.jsonc) of an item kind a REPLACES row can meet.
FORCE_KINDS = {"speed_potions": Kind(TVAL_POTION, SV_POTION_SPEED)}
