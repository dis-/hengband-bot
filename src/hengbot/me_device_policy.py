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


def _usable(policy, snapshot, row: Device, item) -> bool:
    """Absorbing the copy raises the power's count (mind-magic-eater.cpp import_magic_device).

    A charging device is refused.  A rod adds its number whatever its charge (:52); a charged
    wand or staff adds its charges.  An empty wand or staff (pval 0) adds 1 to a kind already
    absorbed (count > 0: ``gain_num`` is raised to 1, :59-64) and nothing to a kind not yet
    absorbed: owner 2026-11-19 「取り込む」 for the first, ``empty_unabsorbed`` sells the second.
    The count never passes 99 (``POWER_COUNT_CAP``), so an empty copy at the cap adds nothing.
    """
    if item.charging or (item.timeout or 0):
        return False
    if item.tval == TVAL_ROD or item.charges > 0:
        return True
    return _absorbed_count(policy, snapshot, row) > 0 and _below_cap(policy, snapshot, row)


def _absorbed_count(policy, snapshot, row: Device) -> int:
    from hengbot import me_capability

    return me_capability.count(policy, snapshot, row.kind, row.sval)


def empty_unabsorbed(policy, snapshot, item) -> bool:
    """An identified empty wand or staff of an ``absorb_now`` kind the Magic-Eater has not yet
    absorbed: absorbing it adds nothing (``_usable``) and no rule recharges it first
    (``charge_first``), so it is sold (owner 2026-11-19)."""
    row = device(item)
    return bool(row is not None and _magic_eater(snapshot) and row.absorb_now
                and item.tval != TVAL_ROD and item.aware and item.known and item.charges <= 0
                and not charge_first(policy, snapshot, row)
                and _absorbed_count(policy, snapshot, row) <= 0)


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
                and _usable(policy, snapshot, row, item)
                and not _first_stage_copy(policy, snapshot, row)):
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
    if not _purchase_count_allows(policy, snapshot, row):
        return False
    # Owner 2026-11-20 「取り込んだ岩石溶解を条件に入れる」: Stone to Mud up to the finale's
    # absorbed count while the 95F exploration lasts (angband_finale).
    from hengbot import angband_finale  # import cycle
    wanted = ((row.buy_more or angband_finale.stone_to_mud_wanted(policy, snapshot, row))
              if _absorbed(policy, snapshot, row) else row.buy_first)
    return (wanted and me_staff_sequence.spare_gold(policy, snapshot) >= item.price
            and _black_market_reserve_kept(policy, snapshot, item))


def _black_market_reserve_kept(policy, snapshot, item) -> bool:
    """Owner 2026-10-08 「必需品1回分の補充代を残す」, the optional Black Market purchases'
    reserve (policy_shop._full_departure_resupply_reserve, an unknown price refusing): a table
    device bought there leaves the full departure resupply, as the Black Market's own optional
    picks do (_black_market_optional_reserve_cap).  Owner 2026-11-16 read this rung as 「余った
    資金で ... 買う」.  n1-b life-411 2026-11-17 13:08: 衝撃の魔法棒 31,808 and 力の杖 31,015
    left 1,721 gold against a 5,244 reserve, under the 3,000 poverty line, and the resumed
    character mined the Yeek cave 1F instead of the Castle dive."""
    from hengbot.model import STORE_BLACK

    store = snapshot.store
    if store is None or store.store_type != STORE_BLACK:
        return True
    reserve = policy._full_departure_resupply_reserve(snapshot)
    return reserve is not None and snapshot.player.gold - item.price >= reserve


def _purchase_count_allows(policy, snapshot, row: Device) -> bool:
    """Owner 2026-11-16 「50回を超えたら止める」: the Staff of *Destruction* is bought only while
    the priority purchase's count limit holds (bm_destruction_fund.staff_wanted)."""
    from hengbot import bm_destruction_fund, destruction_means

    return ((row.tval, row.sval) != destruction_means.STAFF
            or bm_destruction_fund.staff_wanted(policy, snapshot))


# --- The Home's devices (owner 2026-11-19) ------------------------------------------------------
#
# Owner (verbatim): 「魔法道具を自宅にため込んでいる。魔道具術師の処理ルールに従って処分」.  n1-b
# life-411 and n1-c life-217 kept every identified absorb_now device at Home: item_use_route
# counts "magic_eater:absorb" as a use, while ``absorb_candidate`` absorbs only on a dungeon floor
# and nothing took a Home copy out.  The table's rows now act on the Home copies too, through
# item_fate.fate (the one gate):
#
# * ``ABSORB``: a copy the table absorbs (``absorb_now``, charged and usable, no first stage copy;
#   or ``charge_first``) while the power is below its cap.  The Home take (policy_home
#   ``_bind_home_absorb_device_withdrawal``) brings it out; an ``absorb_now`` copy is absorbed at
#   once in town (``town_absorb_candidate``, magic_eater.absorb_key), a ``charge_first`` one is
#   carried by the staff sequence to the Tower as a carried copy is (me_staff_sequence.retains).
# * ``DESTROY``: the Staff of *Destruction* at the cap (owner 2026-11-16 「取り込み回数99なら杖を
#   拾わず壊す」, me_capped_pickup.DESTROY_ON_FLOOR).
# * None: the table's other answers stand: a ``never`` kind, a capped kind (owner 2026-11-13
#   「99回なら必ず拾わない」) and a kind no rule uses go by item_use_route (sold, or destroyed when
#   no store buys it); the zombie's food (magic_eater_devices) stays.  An empty ``absorb_now``
#   copy is absorbed when its kind is already absorbed (``_usable``) and sold when it is not
#   (``empty_unabsorbed``, through item_use_route: owner 2026-11-19 「取り込む」).
ABSORB = "absorb"
DESTROY = "destroy"


def _food_first(policy, snapshot, item) -> bool:
    """Owner 2026-10-31 「食料を先にする」: the zombie keeps charged devices while its carried food
    is short (policy_supply ``_mana_food_device_target``) or its staple is gone or drained
    (me_capped_pickup: any charged device is then food)."""
    from hengbot.magic_eater_devices import staple_food
    from hengbot.policy_constants import FOOD_TYPE_MANA

    if snapshot.player.food_type != FOOD_TYPE_MANA or item.tval == TVAL_ROD:
        return False
    staple = staple_food(snapshot)
    return (staple is None or staple.charges <= 0
            or policy._count_mana_food_devices(snapshot) < policy._mana_food_device_target(snapshot))


def absorbs(policy, snapshot, item) -> bool:
    """The table absorbs this identified copy now or after the Tower's recharge, below the cap."""
    row = device(item)
    if (row is None or row.never or not _magic_eater(snapshot) or not item.aware
            or not item.known or not _below_cap(policy, snapshot, row)):
        return False
    if charge_first(policy, snapshot, row):
        return True
    return row.absorb_now and _usable(policy, snapshot, row, item)


def home_fate(policy, snapshot, item) -> str | None:
    """``ABSORB``, ``DESTROY`` or None for a Home device of the Magic-Eater (the block above)."""
    from hengbot import me_capped_pickup

    if (not _magic_eater(snapshot) or item.tval not in KINDS or not item.aware or not item.known
            or _food_first(policy, snapshot, item)):
        return None
    if ((item.tval, item.sval) in me_capped_pickup.DESTROY_ON_FLOOR
            and me_capped_pickup.capped(policy, snapshot, item.tval, item.sval)):
        return DESTROY
    return ABSORB if absorbs(policy, snapshot, item) else None


def absorbed_in_town(policy, snapshot, item) -> bool:
    """A carried ``absorb_now`` copy the town absorbs (a Home copy taken out for it): kept
    carried until then (policy_home ``_retention_reservation_baseline_detail``)."""
    row = device(item)
    return bool(snapshot.in_town and row is not None and row.absorb_now
                and not charge_first(policy, snapshot, row)
                and absorbs(policy, snapshot, item) and not _food_first(policy, snapshot, item))


def town_absorb_candidate(policy, snapshot):
    """The first carried copy ``absorbed_in_town``, or None while the Home still gives a copy
    to take (``next_home_absorb_take``): the takes come first, then the absorptions."""
    if (getattr(policy, "_home_knowledge_current", False)
            and next_home_absorb_take(policy, snapshot) is not None):
        return None
    return next((item for item in snapshot.inventory
                 if absorbed_in_town(policy, snapshot, item)), None)


def home_absorb_takes(policy, snapshot) -> list:
    """The known Home copies whose fate is ``ABSORB``, catalogue order (``next_home_absorb_take`` takes them).

    In town, with the Home listing current and no hostile in view.
    """
    if not snapshot.in_town or not policy._home_knowledge_current or not _magic_eater(snapshot):
        return []
    if policy._physical_hostiles(snapshot):
        return []
    deferred = getattr(policy, "_deferred_home_items", ())
    return [item for item in policy._home_knowledge_items[:policy._home_knowledge_valid_before]
            if item.count > 0 and home_fate(policy, snapshot, item) == ABSORB
            and policy._item_signature(item) not in deferred]


def next_home_absorb_take(policy, snapshot):
    """The next Home copy to take for the absorption, or None: the last shelf slot first (a take
    shifts only the later slots, so the next stack keeps its address and no census is needed
    between takes), when its whole stack the pack's budget (town_pack_budget.home_take_fits) and
    weight limit admit.  The copies taken wait carried (``absorbed_in_town``) until no more
    is taken, then the town absorbs them (``town_absorb_candidate``)."""
    from hengbot.town_pack_budget import home_take_fits

    takes = home_absorb_takes(policy, snapshot)
    item = takes[-1] if takes else None
    # Only the last: an earlier one taken first would move its address (a census before it).
    if (item is None or not home_take_fits(snapshot, item, item.count, policy=policy)
            or not policy._can_add_item_without_overweight(snapshot, item)):
        return None
    return item


def absorb_errand_open(policy, snapshot) -> bool:
    """The town still absorbs: a carried copy waits (``town_absorb_candidate``) or a Home stack's
    fate is ``ABSORB``.  Its observed progress restarts its stages' deadline counts
    (town_visit_plan.ABSORB_STAGES)."""
    if not snapshot.in_town or not _magic_eater(snapshot):
        return False
    if any(absorbed_in_town(policy, snapshot, item) for item in snapshot.inventory):
        return True
    return any(item.tval in KINDS and home_fate(policy, snapshot, item) == ABSORB
               for item in getattr(policy, "_home_knowledge_items", ()) or ())
