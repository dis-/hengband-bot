"""The Magic-Eater's per-device policy table (owner 2026-10-31).

The owner filled one row per staff, wand and rod (``me_device_policy.json``,
copied from the owner's form me-device-policy-20261031.json): ``buy_first``
「1本目を見たら買う」, ``buy_more`` 「2本目以降も買う」, ``absorb_now``
「拾って鑑定したらその場で取り込む」, ``absorb_after_charge`` 「拾って鑑定したら
持ち帰ってチャージしてから取り込む」, ``never`` 「取り込まない」 and ``stage``
(the staff sequence's stage).  Owner rule for this table: devices and
conditions will grow, so a new device is one row and a new condition one
named predicate here (me-stage2-power-usage-decision-20261031).

Owner answers (2026-10-31 night) that bind the reading:
 1. 「1本目だけ充填する」: the first copy of a ``stage`` kind not yet absorbed
    is recharged at the Tower before it is absorbed; later copies are
    absorbed on the spot.
 2. 「食料を先にする」: until the Wand of Wonder staple is held, the food rule
    (magic_eater_devices) stands, absorption waiting or not.
 3. Stone to Mud 「1本目だけ買う」: bought only while not absorbed; every
    picked-up wand is still kept (policy_home's keep-all rule), but a
    carried copy the staff sequence absorbs (owner 2026-11-07
    「岩石溶解の全部持つ決まりは、取り込む分だけ外す。」).
 4. Identify 「段階1の1本だけ」: the ``stage`` staffs are bought only by the
    staff sequence (me_staff_sequence), never by this table.

Who acts on a row:
 * ``purchase_wanted``: the shop's ``me-device:policy`` purchase rung buys one
   ``buy_first`` device of a kind neither absorbed nor held (pack or Home),
   or one more ``buy_more`` device of an absorbed kind while no copy is held,
   from the gold above what the staff sequence still needs
   (``me_staff_sequence.spare_gold``: the stage's own target or the unmet
   survival supplies).
 * ``absorb_candidate``: magic_eater.absorb_key absorbs a carried, identified,
   usable ``absorb_now`` device when safe on a dungeon or quest floor (the
   floor rung after the survival rungs); in town only the birth Magic Missile
   wand of the opening (O3) -- 「その場で」 is where it was found.
 * ``charge_first``: the staff sequence carries every ``absorb_after_charge``
   device below the count cap, its kind absorbed already or not (owner
   2026-11-07), and the first copy of a ``stage`` kind home, recharges it at
   Morivant's Tower when the spare gold pays the trip, then absorbs it
   (me_staff_sequence extras).
 * ``never``: nothing here acts; sale, food and keep rules decide.
Absorbed means what the player saw: the power in the last displayed list or
the absorption the bot observed (``me_capability.has``).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from hengbot.model import TVAL_ROD, TVAL_STAFF, TVAL_WAND

TABLE = Path(__file__).with_name("me_device_policy.json")
KINDS = {TVAL_STAFF: "staff", TVAL_WAND: "wand", TVAL_ROD: "rod"}
FLAGS = ("buy_first", "buy_more", "absorb_now", "absorb_after_charge", "never")
# mind-magic-eater.cpp import_magic_device: a power's count never exceeds 99;
# another copy absorbed at 99 adds nothing to it.
POWER_COUNT_CAP = 99


@dataclass(frozen=True)
class Device:
    tval: int
    sval: int
    names: tuple          # the power list's baseitem name (ja, en)
    stage: str | None
    buy_first: bool
    buy_more: bool
    absorb_now: bool
    absorb_after_charge: bool
    never: bool

    @property
    def kind(self) -> str:
        return KINDS[self.tval]


@lru_cache(maxsize=1)
def devices() -> dict:
    """(tval, sval) -> Device, as the owner filled the table."""
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["items"]
    return {(row["tval"], row["sval"]): Device(
        row["tval"], row["sval"], (row["name"], row["en"]), row["stage"],
        *(bool(row[flag]) for flag in FLAGS)) for row in rows}


def device(item) -> Device | None:
    return devices().get((item.tval, item.sval))


def _absorbed(policy, snapshot, row: Device) -> bool:
    from hengbot import me_capability

    return me_capability.has(policy, snapshot, row.kind, row.sval)


def _magic_eater(snapshot) -> bool:
    from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER

    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def _first_stage_copy(policy, snapshot, row: Device) -> bool:
    """「1本目だけ充填する」: a stage kind not yet absorbed."""
    return row.stage is not None and not _absorbed(policy, snapshot, row)


def _below_cap(policy, snapshot, row: Device) -> bool:
    """Another copy still raises the power's count (``POWER_COUNT_CAP``).

    The count is the displayed list's ``max`` (cmd-magiceat.cpp prints the
    power's count), else the absorption record: a lower bound, so an
    unread list never stops the absorption early.
    """
    from hengbot import me_capability

    return me_capability.count(policy, snapshot, row.kind, row.sval) < POWER_COUNT_CAP


def charge_first(policy, snapshot, row: Device | None) -> bool:
    """Carried home and recharged at the Tower before it is absorbed.

    Owner 2026-11-07 「「持ち帰って充填してから取り込む」の行は2本目以降も充填して
    取り込み、上限を増やす。」: every identified copy of an ``absorb_after_charge``
    kind, absorbed already or not, until the count is at its cap.  Buying a
    copy stays ``buy_first`` / ``buy_more`` (``purchase_wanted``).
    """
    if row is None or row.never:
        return False
    if row.absorb_after_charge:
        return _below_cap(policy, snapshot, row)
    return _first_stage_copy(policy, snapshot, row)


def _usable(item) -> bool:
    """import_magic_device refuses a charging rod (and an empty device absorbs nothing)."""
    if item.charging or (item.timeout or 0):
        return False
    return item.tval == TVAL_ROD or item.charges > 0


def absorb_candidate(policy, snapshot, *, only=None):
    """The first carried device to absorb on the spot (of the (tval, sval)
    kinds ``only`` names, when given), or None."""
    if not _magic_eater(snapshot):
        return None
    for item in snapshot.inventory:
        row = device(item)
        if only is not None and (item.tval, item.sval) not in only:
            continue
        if (row is not None and row.absorb_now and item.aware and item.known
                and _usable(item) and not _first_stage_copy(policy, snapshot, row)):
            return item
    return None


def awaits_absorption(policy, snapshot, item) -> bool:
    """A carried identified device the Tower still recharges for absorption:
    kept (not sold, shelved or destroyed) until then (me_staff_sequence.retains).
    An ``absorb_now`` device is absorbed on the floor where it was found; one
    that reaches town keeps the ordinary sale and food rules (D25 life-036
    sold its Staff of Object Location for the Word of Recall it needed)."""
    row = device(item)
    return (row is not None and item.aware and item.known
            and charge_first(policy, snapshot, row))


def _held_copy(policy, snapshot, row: Device) -> bool:
    home = getattr(policy, "_home_knowledge_items", ()) or ()
    return any((item.tval, item.sval) == (row.tval, row.sval) and item.aware
               for item in (*snapshot.inventory, *home))


def purchase_wanted(policy, snapshot, item) -> bool:
    """「1本目を見たら買う」/「2本目以降も買う」 for one shelf row."""
    from hengbot import me_staff_sequence

    row = device(item)
    if (row is None or row.stage is not None or not (row.buy_first or row.buy_more)
            or not _magic_eater(snapshot) or not item.aware
            or _held_copy(policy, snapshot, row)):
        return False
    wanted = row.buy_more if _absorbed(policy, snapshot, row) else row.buy_first
    return wanted and me_staff_sequence.spare_gold(policy, snapshot) >= item.price
