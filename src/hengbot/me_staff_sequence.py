"""The Magic-Eater (class 16) staff sequence after quest 1.

Owner instructions 2026-10-30 (in order):
 1. 「魔道具術師でQ1クリア後の最初の採掘の目標を明示する。
     ・資金を貯めて鑑定の杖と財宝感知の杖を1本ずつ買う」
 2. 「その後、噂でモリバントへの移動を解禁、鑑定と財宝感知をチャージマックスにして取り込む」
 3. 「2本目は買わない。以降、鑑定と財宝感知は取り込みで賄う」

Steps (each observed on the board, never assumed):
 fund     -- the first mining run's explicit gold target is the observed
             Magic-shop (or Black-market) price of one Staff of Identify plus
             one Staff of Detect Treasure.
 buy      -- exactly one of each, through the shop's purchase hooks.
 rumor    -- the existing inn rumor flow until Morivant (town 2) is listed in
             the exported ``visited_town_ids`` (what the inn teleport lists).
 travel   -- the inn teleport to Morivant.
 recharge -- Morivant's Tower of Sorcery (lib/edit/towns/03_Morivant.jsonc
             building 8, action 'a' = BACT_RECHARGE_ALL): one confirmed
             recharge of every staff, wand and rod in the pack up to the
             base pval, which market/building-recharger.cpp treats as the
             maximum.
 absorb   -- 'G' (mind-magic-eater.cpp import_magic_device); a staff's first
             absorption sets the power's count to its charges.
 return   -- the inn teleport back to the Outpost.
Afterwards both powers replace the two staffs: no further purchase, the
identify-staff readiness and treasure-detection stock count them, and the
identify / detect commands use ``m`` ``A`` and the power (cmd-magiceat.cpp
letters are I2A(sval)).  Any step that cannot proceed starts one bounded
fundraising run or ends with a named ``quest:blocked:me-staff:`` stop.

Stages (owner 2026-10-31: 「財宝感知と鑑定の取り込みは1本でいい。1本取り込めたら
次の段階に進む。次の段階は店売りの有用な魔法道具を揃えること。トラップ感知の杖
ドア/階段感知の杖 邪悪感知の杖 周辺感知の杖 まずはこれらを1本ずつ取り込むのが目標。
取り込み手順は以前と同じ。」「魔道具術師の第二段階に光の杖を追加」): ``STAGES``
lists each stage's staffs; one absorption of each completes a stage whatever
its charges, and the next stage runs the same steps (Morivant stays
unlocked).  Stage 2's five staffs
(all Magic-shop stock, store/articles-on-sale.cpp) are bought as the shelves
offer them, one each, in one buy round (``_round_open``, #47 D52): this
town's Magic shelf, then the Outpost's, then the other visited towns' that
the spare gold pays (Morivant last, where the round ends at the Tower).  The
Tower's 'a' recharges the whole pack at once and a trip's fares are paid
per visit, so the carried staffs go to the Tower once the round has no
shelf left (n1-c life-074 01:29-01:32: three Tower trips and eight fares for
one stage while Morivant and Angwil sold two of the missing staffs).  A
staff no shelf of the round sells (owner 2026-10-31 「持っている分を先に取り
込む」) does not hold the carried ones back: they go to the Tower then, and
the missing one is bought when it is stocked; the mining runs that wait for
its restock are not counted against the run limit.  A carried staff already
at its maximum is absorbed at Morivant at once (no recharge, no fare).
Completing
a stage is decided once as ``me-staff:stage<N>-complete`` (WAIT; owner
2026-10-31 「次の目標は3キャラ連続で第二段階のクリアとする」).

Other towns (owner 2026-10-31 「資金に余力が出来たら他の街も見て回ることで時短を
図る」): while a stage's staff is out of stock at the Outpost, the gold above
the stock-out run's own target (``_stockout_target``) that pays a trip sends
the sequence to the other visited towns' Magic shops (Morivant last), one
after another, before it mines for the restock (``_next_search_leg``).

Extras (owner 2026-10-31 18h 「岩石溶解の魔法棒を入手したあと、資金に余裕がある
ときにMAXまでチャージして取り込む。」, and the device policy table, owner
2026-10-31 night): a carried, identified device the table charges first
(``me_device_policy.charge_first``: an ``absorb_after_charge`` row, or the
first copy of a stage kind that is not the current stage's own) rides along
on any Tower visit (recharged to its maximum by the same 'a' and absorbed
after the stage's staffs), and starts a Tower trip of its own only when the
gold above what the stage still needs (``spare_gold``: ``_stockout_target``,
or the unmet supplies once every stage is complete) pays the expedition
(``_extras_spare``); it never starts a fundraising run.  Owner 2026-11-07
「「持ち帰って充填してから取り込む」の行は2本目以降も充填して取り込み、上限を増やす。」:
an ``absorb_after_charge`` kind's later copies ride along as well (each one
raises the power's count, mind-magic-eater.cpp, up to 99), one 'G' per
carried stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hengbot import me_capability, morivant_tower
from hengbot.magic_eater import ABSORB_REASON
from hengbot.magic_eater_devices import (
    PLAYER_CLASS_MAGIC_EATER, power_command_refused, staple_food, staple_needs_recharge,
)
from hengbot.me_powers_refresh import KIND_LETTER, SEQUENCE_READ_REASON
from hengbot.model import (
    STORE_BLACK, STORE_HOME, STORE_MAGIC, SV_STAFF_DETECT_DOOR, SV_STAFF_DETECT_EVIL, SV_STAFF_DETECT_GOLD,
    SV_STAFF_DETECT_TRAP, SV_STAFF_IDENTIFY, SV_STAFF_LITE, SV_STAFF_MAPPING, TVAL_STAFF,
)
from hengbot.morivant_tower import RECHARGE_ALL_TAIL, TOWER_OF_SORCERY
from hengbot.policy_constants import (
    FIXED_QUEST_TOWNS, MORIVANT_TOWN_ID, OUTPOST_TOWN_ID, QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED, REST_MACRO, STORE_STUCK_LIMIT, TOWN_TELEPORT_COST,
    WAIT_KEY,
)
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


@dataclass(frozen=True)
class Stage:
    number: int
    svals: tuple
    # Stage 1 buys both staffs on one visit (owner 2026-10-30); stage 2 buys
    # whatever its shelf offers and funds the rest (owner 2026-10-31).
    partial_buy: bool


STAGES = (
    Stage(1, (SV_STAFF_IDENTIFY, SV_STAFF_DETECT_GOLD), False),
    Stage(2, (SV_STAFF_DETECT_TRAP, SV_STAFF_DETECT_DOOR, SV_STAFF_DETECT_EVIL,
              SV_STAFF_MAPPING, SV_STAFF_LITE), True),
)
SEQUENCE_SVALS = tuple(sval for stage in STAGES for sval in stage.svals)
# cmd-magiceat.cpp prints and accepts I2A(sval) for every power.
POWER_LETTER = {sval: chr(ord("a") + sval) for sval in SEQUENCE_SVALS}
# The power list prints the baseitem name (the device policy table's row).
POWER_NAMES = {sval: me_capability.names("staff", sval) for sval in SEQUENCE_SVALS}
# Base pval and cost when the definitions cannot be read (the ids above).
_FALLBACK_BASE = {SV_STAFF_IDENTIFY: (21, 400), SV_STAFF_DETECT_GOLD: (19, 200),
                  SV_STAFF_DETECT_TRAP: (12, 350), SV_STAFF_DETECT_DOOR: (15, 350),
                  SV_STAFF_DETECT_EVIL: (14, 350), SV_STAFF_MAPPING: (11, 750),
                  SV_STAFF_LITE: (19, 250)}
# The Tower facts (rechargeable kinds, prices, building 8, the 'a' tail) live
# in hengbot.morivant_tower, shared with the Q2 breach recharge.

RECHARGE_ALL_REASON = "me-staff:recharge-all"
RUMOR_BATCH_LIMIT = 10  # 400 rumors: a visible stop instead of an endless inn
FUNDRAISE_RUN_LIMIT = 6
# The expedition's runs fund until the cost is reached (owner 2026-11-08):
# FUNDRAISE_RUN_LIMIT does not count them (_fundraise).
EXPEDITION_WHYS = frozenset({"rumor-travel-recharge", "travel-recharge"})
ATTEMPT_LIMIT = 3

REASON = "me-staff:"
PRODUCER = "quest-request"  # the claim family of every sequence key
STOP_REASON = "quest:blocked:me-staff"
DETECT_POWER_KEY = "mA" + POWER_LETTER[SV_STAFF_DETECT_GOLD]
DETECT_REASON = "fundraise:me-detect-treasure"
BUY_RUNG = "me-staff:buy"
STAPLE = "staple"  # the Wand of Wonder's key in attempts / pending
STOCKOUT_WHY = "staff-stockout"


@dataclass
class MeStaffSequence:
    """The sequence's own facts; the board supplies everything else."""
    # me_capability.record_key(kind, sval) -> absorbed count (me_capability reads it)
    absorbed: dict = field(default_factory=dict)
    bought: frozenset = frozenset()
    fundraise_runs: int = 0
    fundraise_target: int | None = None
    fundraise_why: str | None = None               # the current run's objective
    target_reached: bool = False                   # the current run met its target
    reached_runs: int = 0                          # runs that met their target
    expedition_runs: int = 0                       # expedition runs started (uncapped)
    shelf_after_turn: int = -1
    rumor_batches: int = 0
    attempts: dict = field(default_factory=dict)   # (step, record key) -> count
    pending: tuple | None = None                   # (step, ((record key, charges), ...))
    # The key this decision chose and what it counts once posted:
    # (decision sequence, key, ((step, record key), ...), pending).  See _stage.
    staged: tuple | None = None
    empty_turn: dict = field(default_factory=dict)  # record key -> turn seen empty
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)
    failure: str | None = None
    # Observable progress (flight recorder, decision log): the stage being
    # worked (len(STAGES) + 1 when all are done), its staffs not yet
    # absorbed, and stage number -> turn it was completed.
    stage: int = 1
    remaining: tuple = ()
    completed_stages: dict = field(default_factory=dict)
    # The game's staff power list was read in this process (``read_powers``).
    powers_read: bool = False
    # town -> turn its observed Magic shelf lacked the stage's missing staffs.
    searched_towns: dict = field(default_factory=dict)


_device_definitions = morivant_tower.device_definitions
# Base pval and cost of the sequence's staffs when the definitions lack them.
_FALLBACK_KINDS = {(TVAL_STAFF, sval): (pval, 0, cost)
                   for sval, (pval, cost) in _FALLBACK_BASE.items()}


def _base_definitions() -> dict:
    found = _device_definitions()
    return {sval: found[(TVAL_STAFF, sval)][::2] if (TVAL_STAFF, sval) in found
            else _FALLBACK_BASE[sval] for sval in SEQUENCE_SVALS}


def max_charges(sval: int) -> int:
    """building-recharger.cpp: a staff is full at its base pval."""
    return _base_definitions()[sval][0]


def recharge_price_per_charge(item) -> int:
    """building-recharger.cpp: max(10, base cost / 10 * number) per charge."""
    return max(10, _base_definitions()[item.sval][1] // 10 * max(1, item.count))


def _recharge_all_price(item, definitions: dict) -> int:
    """building_recharge_all's price of one pack item (an upper bound)."""
    return morivant_tower.recharge_all_price(item, definitions, _FALLBACK_KINDS)


def recharge_cost(snapshot) -> int:
    """The Tower's 'a' total over every rechargeable pack item."""
    return morivant_tower.recharge_cost(snapshot, _FALLBACK_KINDS)


def state(policy) -> MeStaffSequence:
    record = getattr(policy, "_me_staff_sequence", None)
    if record is None:
        record = policy._me_staff_sequence = MeStaffSequence()
    me_capability.migrate(record)
    return record


def applies(policy, snapshot) -> bool:
    """Class 16 after Q1 was rewarded, on protocol-3 boards."""
    if (snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER
            or getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
            or not getattr(snapshot, "quests", None)):
        return False
    q1 = policy._known_fixed_quests(snapshot).get(1)
    return q1 is not None and q1.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}


def _displayed_staff_rows(policy, snapshot):
    """The rows of the staff list on this board, else of the last one this
    life displayed, else None."""
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") == "staff":
        return listed.get("rows", ())
    remembered = (getattr(policy, "_me_device_lists", None) or {}).get("staff")
    return remembered[1] if remembered is not None else None


def read_powers(policy, snapshot) -> bool:
    """Whether the game's staff power list was read in this process.

    The record lives in the policy's memory only, so a restart forgot every
    absorption: the new process sold the carried stage-2 staffs and bought
    the absorbed Identify and Treasure staffs again (#47 n1-c life-054,
    owner 「2本目は買わない」).  The power list (cmd-magiceat.cpp, read by
    the turn-free browse ``b A``) is the game's own record: every sequence
    power it lists is absorbed.  The staff list any browse of this life
    displayed (``me_device_attacks.observe_lists``, e.g. the periodic
    refresh on a dungeon floor) is that record as well: n1-c life-112
    (2026-11-03 00:05) browsed it on Yeek cave 9F, recalled, and in town
    the sequence's own ``bA`` lost its boards to the Home scan, the dump
    and the periodic wand/rod reads until power-list-unavailable stopped
    the bot.
    """
    record = state(policy)
    rows = _displayed_staff_rows(policy, snapshot)
    if rows is not None:
        names = {name: sval for sval, pair in POWER_NAMES.items() for name in pair}
        for row in rows:
            sval = names.get(row.get("name"))
            if sval is None:
                continue
            key = me_capability.record_key("staff", sval)
            if key not in record.absorbed:
                record.absorbed = {**record.absorbed,
                                   key: max(1, int(row.get("max") or row.get("current") or 0))}
        record.powers_read = True
    return record.powers_read


def _absorbed(policy, sval: int) -> bool:
    return me_capability.absorbed(policy, "staff", sval)


def carried_extras(policy, snapshot) -> dict:
    """record key -> the carried identified device the table charges before absorbing.

    The current stage's own staffs stay ``carried_staffs``.
    """
    from hengbot import me_device_policy

    staffs = carried_staffs(policy, snapshot)
    found = {}
    for item in snapshot.inventory:
        row = me_device_policy.device(item)
        if row is None:
            continue
        key = me_capability.record_key(row.kind, row.sval)
        if (not (item.aware and item.known) or key in found
                or (row.tval == TVAL_STAFF and row.sval in staffs)):
            continue
        if me_device_policy.charge_first(policy, snapshot, row):
            found[key] = item
    return found


def _short_of_max(item) -> bool:
    """The Tower's 'a' would add charges (building-recharger.cpp)."""
    if item.tval == TVAL_STAFF and item.sval in SEQUENCE_SVALS:
        return item.charges < max_charges(item.sval)
    return morivant_tower.charges_after_recharge(item) > item.charges


def stage_complete(policy, stage: Stage) -> bool:
    """「1本取り込めたら次の段階に進む」: one absorption of each, any charges."""
    return all(_absorbed(policy, sval) for sval in stage.svals)


def current_stage(policy) -> Stage | None:
    return next((stage for stage in STAGES if not stage_complete(policy, stage)), None)


def complete(policy) -> bool:
    return current_stage(policy) is None


def active_svals(policy) -> tuple:
    """The staffs of every stage reached so far (later stages stay ordinary)."""
    stage = current_stage(policy)
    last = stage.number if stage is not None else STAGES[-1].number
    return tuple(sval for each in STAGES if each.number <= last for sval in each.svals)


def remaining_svals(policy) -> tuple:
    stage = current_stage(policy)
    return () if stage is None else tuple(
        sval for sval in stage.svals if not _absorbed(policy, sval))


def is_sequence_staff(item, policy) -> bool:
    return item.tval == TVAL_STAFF and item.sval in active_svals(policy) and item.aware


def carried_staffs(policy, snapshot) -> dict:
    """sval -> carried known staff of the current stage, not yet absorbed."""
    needed = remaining_svals(policy)
    staffs = {}
    for item in snapshot.inventory:
        if (item.tval == TVAL_STAFF and item.sval in needed and item.aware
                and item.known and item.sval not in staffs):
            staffs[item.sval] = item
    return staffs


def _needed(policy, snapshot) -> list:
    """The current stage's staffs neither absorbed nor carried."""
    carried = carried_staffs(policy, snapshot)
    return [sval for sval in remaining_svals(policy) if sval not in carried]


def cast_blocked(snapshot) -> bool:
    """Whether no absorbed power may be cast on this board."""
    player = snapshot.player
    return (snapshot.store is not None or player.blind or player.confused
            or player.hallucinated or player.paralyzed or power_command_refused(snapshot))


def power_key(policy, snapshot, sval: int) -> str | None:
    """``m A <letter>`` for an absorbed power that may serve this board (the
    record's count, as ``me_capability.recorded_charges`` reads it)."""
    if (me_capability.recorded_charges(policy, snapshot, "staff", sval) <= 0
            or cast_blocked(snapshot)):
        return None
    return "mA" + POWER_LETTER[sval]


def identify_power_available(policy, snapshot) -> bool:
    return power_key(policy, snapshot, SV_STAFF_IDENTIFY) is not None


def identify_power_command(policy, snapshot, target, *, full: bool) -> str | None:
    """The absorbed Identify power instead of a staff (never *Identify*)."""
    if full or getattr(target, "slot", None) not in "abcdefghijklmnopqrstuvw":
        return None
    key = power_key(policy, snapshot, SV_STAFF_IDENTIFY)
    return key + target.slot if key is not None else None


def _unread_sequence_staff(policy, snapshot, item) -> bool:
    """Any sequence staff while the power list is unread (``read_powers``)."""
    return (item.tval == TVAL_STAFF and item.sval in SEQUENCE_SVALS and item.aware
            and not read_powers(policy, snapshot))


def purchase_excluded(policy, snapshot, item) -> bool:
    """「2本目は買わない」: class 16 never buys these staffs after Q1 itself."""
    return applies(policy, snapshot) and (
        is_sequence_staff(item, policy) or _unread_sequence_staff(policy, snapshot, item))


def order_excluded(policy, snapshot, item) -> bool:
    """After Q1 no pick of the ordinary buy order takes a staff of a stage
    reached so far (known or not), but the emptiest-for-fuller Identify swap
    (``_identify_staff_swap_purchase``; owner 2026-11-01 21h 7)."""
    return (applies(policy, snapshot) and item.tval == TVAL_STAFF
            and item.sval in active_svals(policy)
            and not policy._identify_staff_swap_purchase(item))


def retains(policy, snapshot, item) -> bool:
    """A bought staff (or a device the policy table still absorbs) stays
    carried until it is absorbed."""
    from hengbot import me_device_policy

    return applies(policy, snapshot) and (
        _unread_sequence_staff(policy, snapshot, item)
        or (is_sequence_staff(item, policy) and not _absorbed(policy, item.sval))
        or me_device_policy.awaits_absorption(policy, snapshot, item))


def stows(policy, snapshot, item) -> bool:
    """A staff that waits at Home while stage 1 is worked.

    Owner 2026-11-08 (n1-b life-340: an unidentified 檜の杖 priced as the
    dearest staff made the Tower's recharge 51,145 of a 57,099 gold
    expedition): 「一旦他の杖を自宅に仕舞って鑑定の杖と財宝感知の杖だけ取り込んで、
    鑑定してから再度考える。」  Until stage 1 is complete every staff but
    the Staff of Identify and the Staff of Detect Treasure (unidentified ones
    included) is shelved at Home, so the Tower's 'a' prices only those two.
    Once stage 1 is complete the absorbed Identify is a carried
    identification source and the ordinary Home rules take the stored
    staffs up again (``_identification_waiting_deposit``).
    """
    if item.tval != TVAL_STAFF or item.is_equipment or not applies(policy, snapshot):
        return False
    stage = current_stage(policy)
    return stage is STAGES[0] and not (item.aware and item.sval in stage.svals)


def stowed_staffs(policy, snapshot) -> list:
    """The carried staffs ``stows`` sends to Home."""
    return [item for item in snapshot.inventory if stows(policy, snapshot, item)]


def _stow_pending(policy, snapshot) -> bool:
    """A carried staff Home can still take this visit (the expedition waits).

    Home's own rules decide: Home must not be attempted already, unavailable
    or blocked this visit, and its deposit finder must have work (the staff
    is one of its candidates, ``_home_deposit_candidate``; a full Home is the
    full-Home relief's).  Otherwise the expedition is priced with the staff
    carried.
    """
    if not snapshot.in_town or not any(
            policy._item_signature(item) not in policy._home_rejected_deposits
            and policy._home_deposit_quantity(snapshot, item) > 0
            for item in stowed_staffs(policy, snapshot)):
        return False
    if (STORE_HOME in policy._town_store_attempted or not policy._home_available(snapshot)
            or policy._town_store_blocked_under_applicable_bound(STORE_HOME)):
        return False
    return policy._find_home_deposit(snapshot) is not None


# -- the shop: same hook points as the opening route's purchase ------------

def _fresh_pages(policy, snapshot) -> dict:
    record = state(policy)
    town = policy._effective_town_id(snapshot)
    pages = {}
    for store in (STORE_MAGIC, STORE_BLACK):
        page = policy._town_supplier_stock.get(store)
        observed = policy._town_supplier_stock_observations.get(store)
        if (page is not None and observed is not None and observed[0] == town
                and observed[1] >= record.shelf_after_turn):
            pages[store] = page
    if snapshot.store is not None and snapshot.store.store_type in (STORE_MAGIC, STORE_BLACK):
        pages[snapshot.store.store_type] = snapshot.store
    return pages


def offers(policy, snapshot) -> dict:
    """sval -> (store, cheapest observed offer) for each staff still needed."""
    needed = _needed(policy, snapshot)
    found = {}
    for store, page in _fresh_pages(policy, snapshot).items():
        for item in page.items:
            if (item.count > 0 and item.tval == TVAL_STAFF and item.sval in needed
                    and (item.sval not in found or item.price < found[item.sval][1].price)):
                found[item.sval] = (store, item)
    return found


def buy_target(policy, snapshot) -> int | None:
    """The explicit gold target: one of each still-needed staff, as priced.

    A partial-buy stage prices the needed staffs its shelves offer; stage 1
    needs both on offer.
    """
    stage = current_stage(policy)
    needed = _needed(policy, snapshot)
    found = offers(policy, snapshot)
    if stage is None or not found or (
            not stage.partial_buy and any(sval not in found for sval in needed)):
        return None
    return sum(offer[1].price for offer in found.values())


def shopping(policy, snapshot) -> bool:
    """Whether the sequence owns this shelf: it has a staff to buy here.

    Only a page that sells one of the still-needed staffs at an affordable
    one-of-each total is the sequence's own.  Every other page keeps the
    ordinary buy order (the staffs themselves stay excluded by
    ``purchase_excluded``), so the explicit-target fundraising run can buy
    its light, oil, digger and detection kit (D9, 2026-10-30: owning every
    page refused the kit and the run never left town).
    """
    return _page_purchase(policy, snapshot) is not None


def purchase(policy, snapshot):
    """The shelf row to buy on this page (quantity one), or None."""
    return _page_purchase(policy, snapshot)


def _page_purchase(policy, snapshot):
    if (snapshot.store is None or not applies(policy, snapshot)
            or not read_powers(policy, snapshot) or _phase(policy, snapshot) != "buy"):
        return None
    target = buy_target(policy, snapshot)
    if target is None or snapshot.player.gold < target:
        return None
    for sval in remaining_svals(policy):
        offer = offers(policy, snapshot).get(sval)
        if offer is not None and offer[0] == snapshot.store.store_type:
            return next((item for item in snapshot.store.items if item == offer[1]), None)
    return None


# -- the town owner --------------------------------------------------------

def _stocked_out(policy, snapshot) -> bool:
    """A partial-buy stage whose observed shelves sell none of its missing staffs."""
    stage = current_stage(policy)
    return (stage is not None and stage.partial_buy and bool(_needed(policy, snapshot))
            and STORE_MAGIC in _fresh_pages(policy, snapshot)
            and buy_target(policy, snapshot) is None)


def _phase(policy, snapshot) -> str:
    town = policy._effective_town_id(snapshot)
    visited = snapshot.visited_town_ids
    unlocked = visited is not None and MORIVANT_TOWN_ID in visited
    stage = current_stage(policy)
    carried = carried_staffs(policy, snapshot)
    extras = carried_extras(policy, snapshot)
    missing = _needed(policy, snapshot)
    devices = (*carried.values(), *extras.values())
    short = any(_short_of_max(item) for item in devices) or staple_needs_recharge(snapshot)
    round_open = _round_open(policy, snapshot)
    if (stage is not None and (not missing or (carried and stage.partial_buy and not round_open))) or (
            unlocked and town == MORIVANT_TOWN_ID and devices and not (short and round_open)) or (
            extras and not round_open and _extras_spare(policy, snapshot, unlocked)):
        # Every staff of the stage in hand (or every one the buy round's
        # shelves sell: 「持っている分を先に取り込む」), some at Morivant
        # with nothing left to buy first (or already full), or an extra the
        # spare gold takes there.
        if not unlocked:
            return "rumor"
        if town != MORIVANT_TOWN_ID:
            return "travel"
        return "recharge" if short else "absorb"
    # 「減ったら塔でチャージする」 (from stage 1's completion on): the staple
    # Wand of Wonder goes back to the Tower through the same steps.
    if stage_complete(policy, STAGES[0]) and staple_needs_recharge(snapshot) and unlocked:
        return "recharge" if town == MORIVANT_TOWN_ID else "travel"
    if stage is not None:
        return "buy"
    return "return" if town != OUTPOST_TOWN_ID else "done"


def tower_feeds_staple(policy, snapshot) -> bool:
    """The Tower's recharge is what ends this hunger, and the gold pays for it.

    「減ったら塔でチャージする」.  Hungry but not yet weak, ``_find_edible`` eats
    only the staple, so no Home or shelf device relieves it (n1-c life-128
    2026-11-04 13:05: two empty Wands of Wonder, 38170 gold against a 3344 gold
    expedition, the trip already walking to the inn; the mana override took the
    board from it and retired the Lv36 character).
    """
    staple = staple_food(snapshot)
    if staple is None or staple.charges > 0 or not applies(policy, snapshot):
        return False
    phase = _phase(policy, snapshot)
    if phase == "travel":
        return snapshot.player.gold >= _expedition_cost(snapshot, supply_cost(policy, snapshot))
    return phase == "recharge" and snapshot.player.gold >= recharge_cost(snapshot) + TOWN_TELEPORT_COST


def _stop(policy, detail: str) -> str:
    state(policy).failure = detail
    policy.last_reason = STOP_REASON
    return ""


def supply_cost(policy, snapshot) -> int:
    """Gold the departure plan's still-unmet survival supplies cost.

    Supervisor 2026-10-30 (owner: 「生存処理を優先しなければキャラクタは死亡
    する。」): recall, teleport, cure and the rest are bought first, so every
    explicit target carries them on top of the sequence's own cost.  With the
    staple carried its food shortage is the Tower's recharge, already in
    ``recharge_cost``, so food is not priced twice.  A quest's carry list is
    the quest strategy's own procurement, not this run's.  An unknown price
    adds nothing here (the ordinary reserve refuses optional spending for it).
    """
    excluded = frozenset({"food"}) if staple_food(snapshot) is not None else frozenset()
    reserve = policy._required_departure_supply_reserve(
        snapshot, excluded_kinds=excluded, quest_carry=False)
    return reserve or 0


def _fundraise(policy, snapshot, target: int, why: str) -> str:
    """One existing fundraising run whose objective is ``target`` gold.

    The limit counts runs that came back short of their target; a run that
    met it and whose gold then went to survival supplies is no failure
    (D25 life-036).  Met runs keep their own limit, so a target that keeps
    drifting still ends in a named stop.  A staff-stockout run waits for the
    shelf's restock (``mines_floor_out``), not for gold: it is in neither
    count (owner 2026-10-31, #47 n1-c life-054/057: six restocks without
    Detect Evil ended the sequence).

    The expedition's own gold (``EXPEDITION_WHYS``: the rumors, fares and
    the Tower's recharge) is funded until it is reached, with no run limit
    (owner 2026-11-08, 「資金集めの回数の上限を外し、届くまで資金集めを続ける。」;
    n1-b life-340 Lv8, 28,189 of 57,099 gold, stopped as fundraise-limit after
    six runs that each brought gold home).  Such a run is in neither count
    while it is short; one that met its target counts as a met run in both
    (``town_key``), so the target-drift stop still ends a target that keeps
    moving and the staff purchase keeps its own failure count.
    """
    record = state(policy)
    stockout = why == STOCKOUT_WHY
    expedition = why in EXPEDITION_WHYS
    if (not stockout and not expedition
            and record.fundraise_runs - record.reached_runs >= FUNDRAISE_RUN_LIMIT):
        return _stop(policy, f"fundraise-limit:{why}:{target}")
    if not stockout and record.reached_runs >= FUNDRAISE_RUN_LIMIT:
        return _stop(policy, f"fundraise-target-drift:{why}:{target}")
    record.fundraise_runs += 0 if stockout or expedition else 1
    record.expedition_runs += 1 if expedition else 0
    record.fundraise_target = target
    record.fundraise_why = why
    record.shelf_after_turn = snapshot.turn
    morivant_tower.start_fundraising_run(policy, snapshot, target)
    policy.last_reason = f"{REASON}fundraise:{why}:{target}"
    return WAIT_KEY


def _fundraising_owns(policy) -> bool:
    record = state(policy)
    return (policy._fundraising_mode in {"prepare", "mine", "scavenge"}
            and record.fundraise_target is not None
            and getattr(policy, "_supply_stockout_gold_target", None) == record.fundraise_target)


def mines_floor_out(policy) -> bool:
    """Whether the current explicit-target run ignores its gold target.

    A staff-stockout run exists to pass the Magic shop's restock time, so it
    is one ordinary mining run: like the warrior's run it returns when the
    floor is mined out (or on the survival, pack and light triggers), never
    on the first nugget that crosses its target (D35 life-045, 2026-10-31:
    target gold + 1, one vein of 146 dug, then fundraise:ascend).
    """
    record = getattr(policy, "_me_staff_sequence", None)
    return (record is not None and record.fundraise_why == STOCKOUT_WHY
            and _fundraising_owns(policy))


def _expedition_cost(snapshot, supplies: int) -> int:
    """Fares to Morivant and back, the Tower's recharge and the supplies."""
    return morivant_tower.expedition_cost(snapshot, supplies, _FALLBACK_KINDS)


def _rumor_expedition_cost(snapshot, supplies: int) -> int:
    """The rumor phase's total: the expedition plus the inn's reads."""
    return morivant_tower.rumor_expedition_cost(snapshot, supplies, _FALLBACK_KINDS)


# -- other towns' Magic shops ---------------------------------------------

def _stockout_target(policy, snapshot, supplies: int, unlocked: bool) -> int:
    """Gold the stage still needs anyway: the missing staffs' base estimate and
    the rumor/travel/recharge expedition (D35: never gold + 1)."""
    estimate = sum(_base_definitions()[sval][1] * 2 for sval in _needed(policy, snapshot))
    expedition = (_expedition_cost(snapshot, supplies) if unlocked
                  else _rumor_expedition_cost(snapshot, supplies))
    return estimate + expedition


def spare_gold(policy, snapshot) -> int:
    """「資金に余裕」: the gold above what the stage still needs
    (``_stockout_target``; the unmet supplies once every stage is complete)."""
    supplies = supply_cost(policy, snapshot)
    unlocked = morivant_tower.morivant_unlocked(snapshot)
    needs = (supplies if complete(policy)
             else _stockout_target(policy, snapshot, supplies, unlocked))
    return snapshot.player.gold - needs


def _extras_spare(policy, snapshot, unlocked: bool) -> bool:
    """The spare gold pays the Tower expedition of its own (fares, the
    whole-pack recharge, and the rumors while Morivant is locked)."""
    trip = (_expedition_cost(snapshot, 0) if unlocked
            else _rumor_expedition_cost(snapshot, 0))
    return spare_gold(policy, snapshot) >= trip


def _note_searched(policy, snapshot) -> None:
    """Remember this town's observed Magic shelf lacking the missing staffs."""
    if _stocked_out(policy, snapshot):
        state(policy).searched_towns[policy._effective_town_id(snapshot)] = snapshot.turn


def _searched(policy, town: int) -> bool:
    """Whether ``town``'s shelf lacked them since the restock wait began."""
    record = state(policy)
    return town in record.searched_towns and record.searched_towns[town] >= record.shelf_after_turn


def _shelf_done(policy, snapshot) -> bool:
    """This town's Magic shelf has nothing more for the round: observed
    without a missing staff, or (outside the Outpost, whose shelf is always
    looked at again) given up since the restock wait began."""
    town = policy._effective_town_id(snapshot)
    return _stocked_out(policy, snapshot) or (town != OUTPOST_TOWN_ID and _searched(policy, town))


def _next_shelf(policy, snapshot, supplies: int, unlocked: bool) -> int | None:
    """The round's next town: the Outpost first, then ``_search_town``."""
    if (policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID
            and not _searched(policy, OUTPOST_TOWN_ID)):
        return OUTPOST_TOWN_ID
    return _search_town(policy, snapshot, supplies, unlocked)


def _round_open(policy, snapshot) -> bool:
    """A partial-buy stage's buy round still has a shelf to look at or buy
    from: this town's, or a next town (``_next_shelf``).  The carried staffs
    wait for its end, so one Tower trip serves the stage (#47 D52)."""
    stage = current_stage(policy)
    if stage is None or not stage.partial_buy or not _needed(policy, snapshot):
        return False
    if not _shelf_done(policy, snapshot):
        return True
    return _next_shelf(policy, snapshot, supply_cost(policy, snapshot),
                       morivant_tower.morivant_unlocked(snapshot)) is not None


def _search_town(policy, snapshot, supplies: int, unlocked: bool) -> int | None:
    """The next visited town to look in, when the spare gold pays the trip.

    余力 is the gold above ``_stockout_target`` (the staffs' estimate, the
    kit, both fares to Morivant and the Tower recharge).  The trip is the
    inn fare there and the one back (_town_teleport_key asks two fares for a
    destination other than the Outpost).
    """
    spare = snapshot.player.gold - _stockout_target(policy, snapshot, supplies, unlocked)
    if spare < 2 * TOWN_TELEPORT_COST:
        return None
    towns = [town for town in policy._cross_town_candidate_order(snapshot)
             if town != OUTPOST_TOWN_ID and not _searched(policy, town)]
    # Morivant last: the round ends at its Tower, whose visit looks at its shelf.
    return min(towns, key=lambda town: (town == MORIVANT_TOWN_ID, town), default=None)


def _next_search_leg(policy, snapshot, supplies: int, unlocked: bool) -> str:
    """The round's next town, else home to the Outpost, else the restock run."""
    town = _next_shelf(policy, snapshot, supplies, unlocked)
    if town is not None:
        return _travel(policy, snapshot, town,
                       "return-to-shop" if town == OUTPOST_TOWN_ID else "search-staff")
    if policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID:
        return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-to-shop")
    return _fundraise(policy, snapshot, _stockout_target(policy, snapshot, supplies, unlocked),
                      STOCKOUT_WHY)


def _give_up_town(policy, snapshot, supplies: int, unlocked: bool) -> str:
    """This town cannot serve the search: note it and take the next leg."""
    state(policy).searched_towns[policy._effective_town_id(snapshot)] = snapshot.turn
    return _next_search_leg(policy, snapshot, supplies, unlocked)


def _attempt(policy, step: str, sval: int) -> bool:
    """Whether one more posted attempt stays within ATTEMPT_LIMIT.

    The count itself grows only when the key reaches the game (_stage,
    confirm_posted).
    """
    return state(policy).attempts.get((step, sval), 0) < ATTEMPT_LIMIT


def _stage(policy, key: str, attempts, pending=None) -> str:
    """Count ``attempts`` and arm ``pending`` only once ``key`` is posted.

    A later rung of choose_key may replace the sequence's key (the
    spectator's Magic-Eater list refresh, the periodic save or dump) and the
    owner retirement may hold it; that key never reaches the game, so it is
    no attempt and its board settles nothing.  n1-b life-320 2026-11-06
    01:38 and life-329 20:30: the absorb's G under bA, bB and bC counted
    three absorbs that did not happen and stopped the sequence as
    absorb-no-progress.
    """
    state(policy).staged = (policy._decision_sequence, key, tuple(attempts), pending)
    return key


def confirm_posted(policy, key: str) -> None:
    """The CLI posted ``key`` (policy.confirm_key_posted): commit its stage."""
    record = getattr(policy, "_me_staff_sequence", None)
    staged = getattr(record, "staged", None)
    if staged is None:
        return
    record.staged = None
    sequence, staged_key, attempts, pending = staged
    if sequence != policy._decision_sequence or staged_key != key:
        return
    for attempt in attempts:
        record.attempts[attempt] = record.attempts.get(attempt, 0) + 1
    if pending is not None:
        record.pending = pending


def _settle_pending(policy, snapshot) -> None:
    """Read the previous recharge/absorb from this board."""
    record = state(policy)
    if record.pending is None:
        return
    step, before = record.pending
    record.pending = None
    for key, charges, *copies in before:
        item = (staple_food(snapshot) if key == STAPLE
                else dict(_absorbable(policy, snapshot)).get(key))
        if step == "recharge" and item is not None and item.charges > charges:
            record.attempts.pop(("recharge", key), None)
        # 'G' takes the whole stack (vary_item -999): no carried copy is left,
        # or fewer than before when another stack of the kind is carried
        # (owner 2026-11-07: every copy of an absorb_after_charge kind).
        if step == "absorb" and (item is None or (
                copies and _copies(policy, snapshot, key) < copies[0])):
            # ATTEMPT_LIMIT counts absorptions that did not happen, not every
            # staff of the kind a life takes in (n1-c life-128 2026-11-04 12:18:
            # the fourth Staff of Speed, 17919 gold, stopped the bot).
            record.attempts.pop(("absorb", key), None)
            stage = current_stage(policy)
            record.absorbed = {**record.absorbed,
                               key: max(charges, record.absorbed.get(key, 0))}
            if stage is not None and stage_complete(policy, stage):
                # The next stage gets its own fundraising run budget.
                record.completed_stages = {**record.completed_stages,
                                           stage.number: snapshot.turn}
                record.fundraise_runs = record.reached_runs = record.expedition_runs = 0


def _quest_holds_town(policy, snapshot) -> bool:
    """The fixed-quest head is an approved quest of this town, not yet done.

    Its own errand travels here and back (FIXED_QUEST_TOWNS, _fixed_quest_key
    / _telmora_q2_travel_key): the sequence's leg out of the town would undo
    its trip (D47 n1-c life-065: Q2 TAKEN, five Outpost <-> Telmora fares
    under fixedquest:q2-travel and me-staff:return-outpost, 5772 -> 272 gold).
    """
    head = policy._fixed_quest_head(snapshot)
    return (head is not None
            and head.status not in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}
            and FIXED_QUEST_TOWNS.get(head.id) == policy._effective_town_id(snapshot)
            and policy.approved_quest_strategy(head.id) is not None)


def _travel(policy, snapshot, destination: int, step: str) -> str | None:
    """The inn teleport leg, or None while a quest errand holds this town."""
    if (destination != policy._effective_town_id(snapshot) and _quest_holds_town(policy, snapshot)
            # 「減ったら塔でチャージする」: no departure, the quest's included,
            # has its food until the Tower recharged the staple (n1-c life-120
            # 2026-11-03: Q31 held the Outpost with the staple at 0 of 15, 55k
            # gold, food_ready unmet until owner-retired-burst).  Every other
            # leg keeps the hold.
            and not (destination == MORIVANT_TOWN_ID and staple_needs_recharge(snapshot))):
        return None
    key = policy._town_teleport_key(
        snapshot, destination, producer=PRODUCER, reason=f"{REASON}{step}")
    if key is None:
        return _stop(policy, f"{step}-unavailable:{policy.last_reason}")
    return key


_building_step = morivant_tower.building_step


def _recharge_key(policy, snapshot) -> str:
    """Recharge every rechargeable pack item with the Tower's 'a' command.

    market/building-recharger.cpp building_recharge_all totals the price over
    the whole pack, asks input_check once and fills every staff and wand to
    its base pval (rod timeouts reset).  The bot needs that total plus the
    reserved fare home; the executor answers 'y' only at the observed
    question and leaves the Tower with ESC (observed_input).
    """
    if snapshot.player.gold < recharge_cost(snapshot) + TOWN_TELEPORT_COST:
        # Return with the reserved fare; the Outpost travel gate funds
        # the recharge with one explicit-target run.
        return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-for-funds")
    step, enters = _building_step(policy, snapshot, TOWER_OF_SORCERY, family=PRODUCER)
    if step is None:
        return _stop(policy, "tower-of-sorcery-route-unavailable")
    if not enters:
        return morivant_tower.approach_key(
            policy, snapshot, TOWER_OF_SORCERY, step, f"{REASON}approach-tower")
    before = [(key, item.charges) for key, item in _absorbable(policy, snapshot)
              if _short_of_max(item)]
    if staple_needs_recharge(snapshot):
        before.append((STAPLE, staple_food(snapshot).charges))
    for key, _charges in before:
        if not _attempt(policy, "recharge", key):
            return _stop(policy, f"recharge-no-progress:{key}")
    policy.last_reason = RECHARGE_ALL_REASON
    key = policy._step_toward(snapshot, step, tail=RECHARGE_ALL_TAIL)
    if key:
        _stage(policy, key, (("recharge", record_key) for record_key, _ in before),
               ("recharge", tuple(before)))
    return key


def _absorbable(policy, snapshot) -> list:
    """(record key, item) to absorb: the stage's staffs by sval, then the extras."""
    return [*((me_capability.record_key("staff", sval), item)
              for sval, item in sorted(carried_staffs(policy, snapshot).items())),
            *carried_extras(policy, snapshot).items()]


def _absorb_key(policy, snapshot) -> str:
    player = snapshot.player
    if (player.hp < player.max_hp or player.blind or player.confused
            or player.poisoned or player.cut or player.stunned or player.hallucinated):
        policy.last_reason = f"{REASON}recover"
        return REST_MACRO
    key, item = _absorbable(policy, snapshot)[0]
    if not _attempt(policy, "absorb", key):
        return _stop(policy, f"absorb-no-progress:{key}")
    policy.last_reason = ABSORB_REASON
    return _stage(policy, "G" + item.slot, (("absorb", key),),
                  ("absorb", ((key, item.charges, _copies(policy, snapshot, key)),)))


def _copies(policy, snapshot, key: str) -> int:
    """Carried known devices of the record key's kind (every stack)."""
    return sum(item.count for item in snapshot.inventory
               if item.aware and item.known and _kind_record_key(item) == key)


def _kind_record_key(item) -> str | None:
    from hengbot import me_device_policy

    row = me_device_policy.device(item)
    return me_capability.record_key(row.kind, row.sval) if row is not None else None


def _no_progress(policy, snapshot, phase) -> bool:
    record = state(policy)
    progress = (phase, snapshot.player.gold,
                tuple((it.slot, it.name, it.count, it.charges) for it in snapshot.inventory))
    if record.progress != progress:
        record.progress = progress
        record.positions = {}
    position = snapshot.player.position
    record.positions[position] = record.positions.get(position, 0) + 1
    return record.positions[position] >= STORE_STUCK_LIMIT


def town_key(policy, snapshot, hostiles) -> str | None:
    """Sole non-emergency town owner while the sequence is unfinished."""
    if not snapshot.in_town or snapshot.store is not None or not applies(policy, snapshot):
        return None
    session = policy._equipment_transaction_session
    equipping = session is not None and not session.complete
    if equipping and session.required_context == "home":
        # The Home equipment session owns the route to Home and refuses
        # every other shop's (policy_shop _shopping_approach_key ->
        # equipment_route_handoff WAIT): the sequence waits for it (#47 n1-c
        # life-054 072115: 82 x shop:approach '5', then no-progress:buy).
        return None
    record = state(policy)
    if not read_powers(policy, snapshot):
        # Read what the game has absorbed before buying, selling or
        # absorbing anything (``read_powers``); browsing takes no game time.
        # A hostile in view keeps the board for fight/flee (survival first),
        # an equipment session in flight for its own next action.
        if equipping or policy._physical_hostiles(snapshot):
            return None
        if not _attempt(policy, "read-powers", 0):
            return _stop(policy, "power-list-unavailable")
        policy.last_reason = SEQUENCE_READ_REASON
        return _stage(policy, "b" + KIND_LETTER["staff"], (("read-powers", 0),))
    announced = set(record.completed_stages)
    _settle_pending(policy, snapshot)
    stage = current_stage(policy)
    record.stage = stage.number if stage is not None else len(STAGES) + 1
    record.remaining = remaining_svals(policy)
    finished = sorted(set(record.completed_stages) - announced)
    if finished:
        # One observable decision per completed stage.
        policy.last_reason = f"{REASON}stage{finished[-1]}-complete"
        return WAIT_KEY
    if record.failure:
        return _stop(policy, record.failure)
    _note_searched(policy, snapshot)
    phase = _phase(policy, snapshot)
    if phase == "done":
        return None
    gold = snapshot.player.gold
    if _fundraising_owns(policy):
        # The existing fundraising owners carry out the run.
        record.target_reached = record.target_reached or gold >= record.fundraise_target
        return None
    if record.fundraise_target is not None:
        if (record.fundraise_why != STOCKOUT_WHY
                and (record.target_reached or gold >= record.fundraise_target)):
            record.reached_runs += 1
            # An expedition run counts only once it met its target, as a met
            # run in both counts (_fundraise): the drift stop sees it, the
            # staff purchase's failure count does not.
            record.fundraise_runs += 1 if record.fundraise_why in EXPEDITION_WHYS else 0
        record.fundraise_target = None
        record.target_reached = False
    if (policy._physical_adjacent_hostiles(snapshot)
            or policy._random_teleport_inscription_comes_first(snapshot)):
        return None
    # Owner 2026-10-31: town is cleared before errands resume
    # (policy._decide's global ``_town_kill_mob_key`` rung, which sits below
    # this sequence's rung).  Without asking it here the sequence travelled
    # past a visible town monster, the hunt walked back to where it was last
    # seen once out of sight, and the sequence's position count stopped it
    # (n1-b life-338 2026-11-07 17:34, quest:blocked:me-staff
    # no-progress:return, a drunk near the Outpost inn).
    hunt = policy._town_producer_entry(
        "_town_kill_mob_key", lambda: policy._town_kill_mob_key(snapshot))
    if hunt is not None:
        return hunt
    key = _phase_key(policy, snapshot, phase, stage)
    if key is None:
        # Another owner takes the board (a quest errand holding the town
        # keeps the travel leg, _travel): its boards are not the sequence's
        # standstill.  n1-c life-112 (2026-11-03 01:12): the travel phase
        # yielded to the recall to Angband and the eight waits on its cell
        # stopped the bot as no-progress:travel.
        return None
    if key and _no_progress(policy, snapshot, phase):
        return _stop(policy, f"no-progress:{phase}")
    return key


def _phase_key(policy, snapshot, phase: str, stage) -> str | None:
    """This board's step of the phase: a key, a named stop (''), or None."""
    record = state(policy)
    gold = snapshot.player.gold
    supplies = supply_cost(policy, snapshot)
    carried = frozenset(carried_staffs(policy, snapshot))
    if stage is not None and stage.partial_buy and carried - record.bought:
        # Each staff bought is progress: the run budget starts again.
        record.fundraise_runs = record.reached_runs = 0
    record.bought = record.bought | carried
    visited = snapshot.visited_town_ids
    unlocked = visited is not None and MORIVANT_TOWN_ID in visited
    if phase == "buy":
        away = policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID
        if away and not stage.partial_buy:
            return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-to-shop")
        target = buy_target(policy, snapshot)
        if target is None:
            if not _shelf_done(policy, snapshot) and STORE_MAGIC not in _fresh_pages(policy, snapshot):
                # The round looks at this town's shelf first (#47 D52).
                step = policy._shopping_approach_step(
                    snapshot, store_type=STORE_MAGIC, requester="quest-request")
                if step is None and away:
                    return _give_up_town(policy, snapshot, supplies, unlocked)
                if step is None:
                    return _stop(policy, "magic-shop-route-unavailable")
                policy.last_reason = "shop:approach"
                key = policy._shopping_approach_key(snapshot, step, "shop:travel")
                return key if key is not None else _stop(policy, "magic-shop-operation-unavailable")
            # Observed shelf without one of the staffs: the other towns'
            # shelves when the spare gold pays the trip, else one ordinary
            # mining run passes the restock time (mines_floor_out).
            return _next_search_leg(policy, snapshot, supplies, unlocked)
        if gold < target + supplies:
            if away:
                return _give_up_town(policy, snapshot, supplies, unlocked)
            return _fundraise(policy, snapshot, target + supplies, "staffs")
        offer = next(offer for sval, offer in sorted(offers(policy, snapshot).items()))
        step = policy._shopping_approach_step(snapshot, store_type=offer[0], requester="quest-request")
        if step is None:
            return _stop(policy, f"store-{offer[0]}-route-unavailable")
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(snapshot, step, "shop:travel")
        return key if key is not None else _stop(policy, "shop-operation-unavailable")
    if phase in {"rumor", "travel", "recharge"} and _stow_pending(policy, snapshot):
        # The staffs ``stows`` names go to Home first, by Home's own deposit
        # flow; the expedition is priced without them (owner 2026-11-08).
        policy.last_reason = f"{REASON}stow-staffs"
        return None
    expedition = _expedition_cost(snapshot, supplies)
    if phase == "rumor":
        needed = _rumor_expedition_cost(snapshot, supplies)
        if gold < needed:
            return _fundraise(policy, snapshot, needed, "rumor-travel-recharge")
        if record.rumor_batches >= RUMOR_BATCH_LIMIT:
            return _stop(policy, "morivant-rumor-exhausted")
        key, batched = morivant_tower.rumor_key(policy, snapshot)
        if batched:
            record.rumor_batches += 1
        return key
    if phase == "travel":
        if policy._effective_town_id(snapshot) == OUTPOST_TOWN_ID and gold < expedition:
            return _fundraise(policy, snapshot, expedition, "travel-recharge")
        return _travel(policy, snapshot, MORIVANT_TOWN_ID, "travel-morivant")
    if phase == "recharge":
        return _recharge_key(policy, snapshot)
    if phase == "absorb":
        return _absorb_key(policy, snapshot)
    return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-outpost")
