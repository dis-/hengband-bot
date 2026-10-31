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
(all Magic-shop stock, store/articles-on-sale.cpp) are bought as the shelf
offers them, one each, and every carried staff of the stage is recharged
and absorbed on whichever Tower visit comes first: a trip's fares are paid
per visit and the Tower's 'a' recharges the whole pack at once.  A staff the
observed Magic shelf does not sell (owner 2026-10-31 「持っている分を先に取り
込む」) does not hold the carried ones back: they go to the Tower now, and the
missing one is bought when it is stocked; the mining runs that wait for its
restock are not counted against the run limit.  Completing
a stage is decided once as ``me-staff:stage<N>-complete`` (WAIT; owner
2026-10-31 「次の目標は3キャラ連続で第二段階のクリアとする」).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hengbot import morivant_tower
from hengbot.magic_eater import ABSORB_REASON
from hengbot.magic_eater_devices import (
    PLAYER_CLASS_MAGIC_EATER, staple_food, staple_needs_recharge,
)
from hengbot.me_powers_refresh import KIND_LETTER, SEQUENCE_READ_REASON
from hengbot.model import STORE_BLACK, STORE_MAGIC, SV_STAFF_IDENTIFY, TVAL_STAFF
from hengbot.morivant_tower import RECHARGE_ALL_TAIL, TOWER_OF_SORCERY
from hengbot.policy_constants import (
    MORIVANT_TOWN_ID, OUTPOST_TOWN_ID, QUEST_STATUS_FINISHED,
    QUEST_STATUS_REWARDED, REST_MACRO, STORE_STUCK_LIMIT, TOWN_TELEPORT_COST,
    WAIT_KEY,
)
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY


# sv-definition/sv-staff-types.h
SV_STAFF_LITE = 8
SV_STAFF_MAPPING = 9
SV_STAFF_DETECT_GOLD = 10
SV_STAFF_DETECT_TRAP = 12
SV_STAFF_DETECT_DOOR = 13
SV_STAFF_DETECT_EVIL = 15


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
# The power list prints the baseitem name (BaseitemDefinitions ids 326, 301,
# 300, 316, 318, 328, 306).
POWER_NAMES = {SV_STAFF_IDENTIFY: ("鑑定", "Perception"),
               SV_STAFF_DETECT_GOLD: ("財宝感知", "Treasure Location"),
               SV_STAFF_DETECT_TRAP: ("トラップ感知", "Trap Location"),
               SV_STAFF_DETECT_DOOR: ("ドア/階段感知", "Door/Stair Location"),
               SV_STAFF_DETECT_EVIL: ("邪悪存在感知", "Detect Evil"),
               SV_STAFF_MAPPING: ("周辺感知", "Enlightenment"),
               SV_STAFF_LITE: ("光", "Light")}
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
ATTEMPT_LIMIT = 3

REASON = "me-staff:"
STOP_REASON = "quest:blocked:me-staff"
IDENTIFY_POWER_KEY = "mA" + POWER_LETTER[SV_STAFF_IDENTIFY]
DETECT_POWER_KEY = "mA" + POWER_LETTER[SV_STAFF_DETECT_GOLD]
DETECT_REASON = "fundraise:me-detect-treasure"
BUY_RUNG = "me-staff:buy"
STAPLE = "staple"  # the Wand of Wonder's key in attempts / pending
STOCKOUT_WHY = "staff-stockout"


@dataclass
class MeStaffSequence:
    """The sequence's own facts; the board supplies everything else."""
    absorbed: dict = field(default_factory=dict)   # sval -> absorbed count
    bought: frozenset = frozenset()
    fundraise_runs: int = 0
    fundraise_target: int | None = None
    fundraise_why: str | None = None               # the current run's objective
    target_reached: bool = False                   # the current run met its target
    reached_runs: int = 0                          # runs that met their target
    shelf_after_turn: int = -1
    rumor_batches: int = 0
    attempts: dict = field(default_factory=dict)   # (step, sval) -> count
    pending: tuple | None = None                   # (step, ((sval, charges), ...))
    empty_turn: dict = field(default_factory=dict)  # sval -> turn seen empty
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
    return record


def applies(policy, snapshot) -> bool:
    """Class 16 after Q1 was rewarded, on protocol-3 boards."""
    if (snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER
            or getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
            or not getattr(snapshot, "quests", None)):
        return False
    q1 = policy._known_fixed_quests(snapshot).get(1)
    return q1 is not None and q1.status in {QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED}


def read_powers(policy, snapshot) -> bool:
    """Whether the game's staff power list was read in this process.

    The record lives in the policy's memory only, so a restart forgot every
    absorption: the new process sold the carried stage-2 staffs and bought
    the absorbed Identify and Treasure staffs again (#47 n1-c life-054,
    owner 「2本目は買わない」).  The power list (cmd-magiceat.cpp, read by
    the turn-free browse ``b A``) is the game's own record: every sequence
    power it lists is absorbed.
    """
    record = state(policy)
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") == "staff":
        names = {name: sval for sval, pair in POWER_NAMES.items() for name in pair}
        for row in listed.get("rows", ()):
            sval = names.get(row.get("name"))
            if sval is not None and sval not in record.absorbed:
                record.absorbed = {**record.absorbed,
                                   sval: max(1, int(row.get("max") or row.get("current") or 0))}
        record.powers_read = True
    return record.powers_read


def absorbed(policy, sval: int) -> bool:
    record = getattr(policy, "_me_staff_sequence", None)
    return record is not None and sval in record.absorbed


def stage_complete(policy, stage: Stage) -> bool:
    """「1本取り込めたら次の段階に進む」: one absorption of each, any charges."""
    return all(absorbed(policy, sval) for sval in stage.svals)


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
        sval for sval in stage.svals if not absorbed(policy, sval))


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


def absorbed_charges(policy, snapshot, sval: int) -> int:
    """Charges the absorbed power serves, as last read from its own list.

    The power list is observed only when it is cast (executor answers). A
    power seen empty on this board serves nothing until game time passes
    (it regenerates, and an inn rest refills it); otherwise its count does.
    """
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER or not absorbed(policy, sval):
        return 0
    record = state(policy)
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") == "staff":
        for row in listed.get("rows", ()):
            if row.get("name") in POWER_NAMES[sval] and row.get("current") == 0:
                record.empty_turn[sval] = snapshot.turn
    if record.empty_turn.get(sval) == snapshot.turn:
        return 0
    return record.absorbed[sval]


def power_key(policy, snapshot, sval: int) -> str | None:
    """``m A <letter>`` for an absorbed power that may serve this board."""
    player = snapshot.player
    if (absorbed_charges(policy, snapshot, sval) <= 0 or snapshot.store is not None
            or player.blind or player.confused or player.hallucinated or player.paralyzed):
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


def retains(policy, snapshot, item) -> bool:
    """A bought staff stays carried until it is recharged and absorbed."""
    return applies(policy, snapshot) and (
        _unread_sequence_staff(policy, snapshot, item)
        or (is_sequence_staff(item, policy) and not absorbed(policy, item.sval)))


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
    missing = _needed(policy, snapshot)
    if (stage is not None and (not missing or (carried and _stocked_out(policy, snapshot)))) or (
            unlocked and town == MORIVANT_TOWN_ID and carried):
        # Every staff of the stage in hand (or every one the shelf sells:
        # 「持っている分を先に取り込む」), or some already at Morivant.
        if not unlocked:
            return "rumor"
        if town != MORIVANT_TOWN_ID:
            return "travel"
        if (any(item.charges < max_charges(sval) for sval, item in carried.items())
                or staple_needs_recharge(snapshot)):
            return "recharge"
        return "absorb"
    # 「減ったら塔でチャージする」 (from stage 1's completion on): the staple
    # Wand of Wonder goes back to the Tower through the same steps.
    if stage_complete(policy, STAGES[0]) and staple_needs_recharge(snapshot) and unlocked:
        return "recharge" if town == MORIVANT_TOWN_ID else "travel"
    if stage is not None:
        return "buy"
    return "return" if town != OUTPOST_TOWN_ID else "done"


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
    """
    record = state(policy)
    stockout = why == STOCKOUT_WHY
    if not stockout and record.fundraise_runs - record.reached_runs >= FUNDRAISE_RUN_LIMIT:
        return _stop(policy, f"fundraise-limit:{why}:{target}")
    if not stockout and record.reached_runs >= FUNDRAISE_RUN_LIMIT:
        return _stop(policy, f"fundraise-target-drift:{why}:{target}")
    record.fundraise_runs += 0 if stockout else 1
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


def _attempt(policy, step: str, sval: int) -> bool:
    record = state(policy)
    count = record.attempts.get((step, sval), 0) + 1
    record.attempts[(step, sval)] = count
    return count <= ATTEMPT_LIMIT


def _settle_pending(policy, snapshot) -> None:
    """Read the previous recharge/absorb from this board."""
    record = state(policy)
    if record.pending is None:
        return
    step, before = record.pending
    record.pending = None
    for sval, charges in before:
        item = (staple_food(snapshot) if sval == STAPLE
                else carried_staffs(policy, snapshot).get(sval))
        if step == "recharge" and item is not None and item.charges > charges:
            record.attempts.pop(("recharge", sval), None)
        if step == "absorb" and item is None:
            stage = current_stage(policy)
            record.absorbed = {**record.absorbed, sval: charges}
            if stage is not None and stage_complete(policy, stage):
                # The next stage gets its own fundraising run budget.
                record.completed_stages = {**record.completed_stages,
                                           stage.number: snapshot.turn}
                record.fundraise_runs = record.reached_runs = 0


def _travel(policy, snapshot, destination: int, step: str) -> str:
    key = policy._town_teleport_key(
        snapshot, destination, producer="quest-request", reason=f"{REASON}{step}")
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
    step, enters = _building_step(policy, snapshot, TOWER_OF_SORCERY)
    if step is None:
        return _stop(policy, "tower-of-sorcery-route-unavailable")
    if not enters:
        policy.last_reason = f"{REASON}approach-tower"
        return policy._step_toward(snapshot, step)
    before = [(sval, item.charges) for sval, item in sorted(carried_staffs(policy, snapshot).items())
              if item.charges < max_charges(sval)]
    if staple_needs_recharge(snapshot):
        before.append((STAPLE, staple_food(snapshot).charges))
    for sval, _charges in before:
        if not _attempt(policy, "recharge", sval):
            return _stop(policy, f"recharge-no-progress:{sval}")
    state(policy).pending = ("recharge", tuple(before))
    policy.last_reason = RECHARGE_ALL_REASON
    return policy._step_toward(snapshot, step, tail=RECHARGE_ALL_TAIL)


def _absorb_key(policy, snapshot) -> str:
    player = snapshot.player
    if (player.hp < player.max_hp or player.blind or player.confused
            or player.poisoned or player.cut or player.stunned or player.hallucinated):
        policy.last_reason = f"{REASON}recover"
        return REST_MACRO
    sval, item = sorted(carried_staffs(policy, snapshot).items())[0]
    if not _attempt(policy, "absorb", sval):
        return _stop(policy, f"absorb-no-progress:{sval}")
    state(policy).pending = ("absorb", ((sval, item.charges),))
    policy.last_reason = ABSORB_REASON
    return "G" + item.slot


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
        return "b" + KIND_LETTER["staff"]
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
        record.fundraise_target = None
        record.target_reached = False
    if policy._physical_adjacent_hostiles(snapshot):
        return None
    if _no_progress(policy, snapshot, phase):
        return _stop(policy, f"no-progress:{phase}")
    supplies = supply_cost(policy, snapshot)
    carried = frozenset(carried_staffs(policy, snapshot))
    if stage is not None and stage.partial_buy and carried - record.bought:
        # Each staff bought is progress: the run budget starts again.
        record.fundraise_runs = record.reached_runs = 0
    record.bought = record.bought | carried
    visited = snapshot.visited_town_ids
    unlocked = visited is not None and MORIVANT_TOWN_ID in visited
    if phase == "buy":
        if policy._effective_town_id(snapshot) != OUTPOST_TOWN_ID:
            return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-to-shop")
        target = buy_target(policy, snapshot)
        if target is None:
            if STORE_MAGIC not in _fresh_pages(policy, snapshot):
                step = policy._shopping_approach_step(
                    snapshot, store_type=STORE_MAGIC, requester="quest-request")
                if step is None:
                    return _stop(policy, "magic-shop-route-unavailable")
                policy.last_reason = "shop:approach"
                key = policy._shopping_approach_key(snapshot, step, "shop:travel")
                return key if key is not None else _stop(policy, "magic-shop-operation-unavailable")
            # Observed shelf without one of the staffs: one ordinary mining
            # run passes the restock time (mines_floor_out).  Its target is
            # what the sequence still needs anyway: the staffs' base estimate
            # and the rumor/travel/recharge expedition (D35: never gold + 1).
            estimate = sum(_base_definitions()[sval][1] * 2
                           for sval in _needed(policy, snapshot))
            expedition = (_expedition_cost(snapshot, supplies) if unlocked
                          else _rumor_expedition_cost(snapshot, supplies))
            return _fundraise(policy, snapshot, estimate + expedition, STOCKOUT_WHY)
        if gold < target + supplies:
            return _fundraise(policy, snapshot, target + supplies, "staffs")
        offer = next(offer for sval, offer in sorted(offers(policy, snapshot).items()))
        step = policy._shopping_approach_step(snapshot, store_type=offer[0], requester="quest-request")
        if step is None:
            return _stop(policy, f"store-{offer[0]}-route-unavailable")
        policy.last_reason = "shop:approach"
        key = policy._shopping_approach_key(snapshot, step, "shop:travel")
        return key if key is not None else _stop(policy, "shop-operation-unavailable")
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
