"""The lending of an equipment slot to a temporary swap: one owner for every swap's end.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E5, behaviour-changing).
Owner Q6 (verbatim): 「一時的な付け替え（採掘・クエスト・ズル等）の後はいつも目指す装備の武器に戻す。
各系統で元の武器を覚えるのをやめる」.  Before E5 each temporary swap remembered what it displaced
and put that back: the mining swap's seven ``_normal_*`` attributes (written by the swap, the Q2
breach, the equipment transaction's deposit and the digger wield's second post, read by six
re-arm rungs), the Zul trip's ``_zul_replaced_ring`` and the Q25 druj piece's ``displaced``
signature.  A remembered piece is no target: it was whatever happened to be worn when the swap
began, and the rungs that read it disagreed with the visit's swap, which wears the target.

Now a swap *borrows* a slot and its end *returns* the slot to the target loadout's piece for it
(:func:`return_item`): the loadout search's target (equipment_target ``loadout_target``; in town
the visit's fixed target of stage E3, in the dungeon the last one decided; when none is stored --
a destination switch or the mining trip's return clears it -- the loadout the last visit fixed).  Nothing of the
displaced piece is remembered.  Without a target piece the slot falls back as every re-arm did
before: the main hand takes the first usable melee weapon carried, an off hand a carried shield
only when no target decided the hands at all.

The borrowers, each with the slots it borrows and where its lending ends:

- ``mining-digger``: the mining fundraise and the dig-to-stairs / walk-out / enclosure digs
  (policy_equipment ``_wield_digging_tool_key``) lend the combat hands to a digger.  The lending
  is read from the board -- a digger in a hand -- and held in town by mining_loadout
  ``hands_lent``; it ends by the swap's abort (mining_loadout ``finish_swap_key``), the dungeon's
  re-arm (``rollback_key``, the contact re-arm ``_restore_mining_combat_hand_key``), the
  breakout's restore (policy ``_breakout_restore_weapon_key``), and in town the re-arm
  (``_town_restore_weapon_key``), the Home's withdrawal (``_home_rearm_key``) or the visit's swap.
- ``q2-breach-digger``: Q2's breach wields a strong digger in the main hand
  (policy_quest ``q2-breach-loadout``); a digger in a hand, so the ``mining-digger`` ends serve it.
- ``zul-levitation``: the Zul trip puts a Ring of Levitation on a ring slot (zul_trip
  ``_wear_key``); the record of :func:`lend` names the slot, the target's ring for it stays
  carried through the trip (:func:`retains`) and zul_trip ``rewear_key`` returns it after the trip.

The weapon hand came first (owner Q6 names the weapon); the Q25 druj piece still remembers what
it displaced until the next step moves it here.

Not borrowers: the 99F/100F preparation (finale_prep) swaps to its own loadout by deciding the
target itself (equipment_target ``finale-phase``), so its end is the target's; the light slot's
rungs (refill, a fresher torch, the lantern) maintain the light and remember nothing; the
anti-teleport take-off before a relocation read (policy ``_anti_teleport_takeoff_key``) gives up
the piece for the escape.

The return exits (:func:`wield_back`, :func:`take_back`) are the only wear calls a swap's end
makes (scripts/equipment_writer_lint.py pins them here).
"""

from __future__ import annotations

from hengbot import equipment_target
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import TVAL_SHIELD
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY

MAIN_HAND = "main_hand"
SUB_HAND = "sub_hand"
HANDS = (MAIN_HAND, SUB_HAND)

# The recorded borrowers (``lend``) and the slots each may borrow: a board does not tell which
# slot they lent (a digger in a hand does: the hands' lending is read from the board).
ZUL_LEVITATION = "zul-levitation"
RECORDED_BORROWERS = {ZUL_LEVITATION: ("main_ring", "sub_ring")}
# The policy attribute of the recorded lendings: {slot: borrower} (a row of state_registry).
LENDING_STATE = "_slot_lending"

# --- the target the slot returns to -----------------------------------------------------

def target_loadout(policy):
    """The target loadout: the stored search's winner, else the loadout the last town visit fixed
    (equipment_target ``last_visit_loadout``: the stored target is cleared by a destination switch
    or the mining trip's return), or None (no search has chosen one)."""
    preparation = equipment_target.loadout_target(policy)
    best = getattr(getattr(preparation, "result", None), "best", None)
    loadout = getattr(best, "loadout", None)
    if loadout is not None and hasattr(loadout, "item_at"):
        return loadout
    return equipment_target.last_visit_loadout(policy)


def target_piece(policy, slot: str):
    """The target's item for ``slot``, or None (no target, or the target leaves it empty)."""
    loadout = target_loadout(policy)
    piece = loadout.item_at(slot) if loadout is not None else None
    return piece.item if piece is not None else None


def returns_empty(policy, slot: str) -> bool:
    """The target decided ``slot`` empty: its lending returns it empty."""
    loadout = target_loadout(policy)
    return loadout is not None and loadout.item_at(slot) is None


def _returnable(policy, item) -> bool:
    """A carried item a returned slot may take (never a digger; the re-arms' common filter)."""
    return (item.is_equipment and not item.is_digging_tool
            and not policy._equip_blocked_by_identification(item)
            and not item.is_broken and not policy._blocks_teleport(item))


def _fallback(policy, slot: str):
    """What a slot without a target piece matches: the main hand any melee weapon; an off hand
    a shield, only while no target decided the hands (a second weapon goes on only as the
    target's choice: #47, the Magic-Eater's unskilled dual wield missed)."""
    if slot == MAIN_HAND:
        return lambda item: item.is_melee_weapon
    if slot == SUB_HAND and target_loadout(policy) is None:
        return lambda item: item.tval == TVAL_SHIELD
    return None


def return_item(policy, snapshot, slot: str):
    """The carried item a lent ``slot`` goes back to, or None.

    The target's piece for the slot (by the identity a move keeps), else the fallback
    (``_fallback``): the first usable melee weapon for the main hand (owner 2026-10-31
    「最適化の結果→最初の近接武器」 「これでよい」)."""
    piece = target_piece(policy, slot)
    if piece is not None:
        identity = equipment_identity(piece)
        item = policy._first_item(
            snapshot, lambda item: _returnable(policy, item)
            and equipment_identity(item) == identity)
        if item is not None:
            return item
    matches = _fallback(policy, slot)
    if matches is None:
        return None
    return policy._first_item(snapshot, lambda item: _returnable(policy, item) and matches(item))


def return_home_item(policy, items, slot: str):
    """The target's piece for ``slot`` among ``items`` (a Home page), or None."""
    piece = target_piece(policy, slot)
    if piece is None:
        return None
    identity = equipment_identity(piece)
    return next((item for item in items if equipment_identity(item) == identity), None)


def is_target_piece(policy, item, slot: str) -> bool:
    """``item`` is the target's piece for ``slot`` (the identity a move keeps)."""
    piece = target_piece(policy, slot)
    return piece is not None and equipment_identity(item) == equipment_identity(piece)


# --- the recorded lendings ----------------------------------------------------------------

def _record(policy) -> dict:
    record = getattr(policy, LENDING_STATE, None)
    return record if isinstance(record, dict) else {}


def lend(policy, slot: str, borrower: str) -> None:
    """``borrower`` took ``slot`` for its temporary piece; nothing it displaced is remembered."""
    assert slot in RECORDED_BORROWERS[borrower], (borrower, slot)
    record = dict(_record(policy))
    record[slot] = borrower
    setattr(policy, LENDING_STATE, record)


def lent_slots(policy, borrower: str) -> tuple:
    """The slots ``borrower`` holds, in slot order."""
    record = _record(policy)
    return tuple(slot for slot in EQUIPMENT_SLOT_KEY if record.get(slot) == borrower)


def end(policy, slot: str) -> None:
    """The lending of ``slot`` ended: the slot is the target's again."""
    record = dict(_record(policy))
    if record.pop(slot, None) is not None:
        setattr(policy, LENDING_STATE, record)


def retains(policy, item, borrower: str) -> bool:
    """While ``borrower`` holds a slot, the target's piece for it stays carried (no sale, deposit
    or destruction): the slot's return wears it."""
    return any(is_target_piece(policy, item, slot) for slot in lent_slots(policy, borrower))


# --- the return exits -------------------------------------------------------------------

def wield_back(policy, snapshot, goal: str, item, slot: str, **options) -> str | None:
    """The lent slot's return: ``item`` (``return_item``) wielded into it."""
    return policy._equipment_wield(snapshot, goal, item, slot, **options)


def take_back(policy, snapshot, goal: str, slot: str) -> str | None:
    """The lent slot's return when the target leaves it empty: its occupant taken off."""
    return policy._equipment_takeoff(snapshot, goal, EQUIPMENT_SLOT_KEY[slot])
