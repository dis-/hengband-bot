"""Recharge the carried Stone to Mud wands at Morivant's Tower when gold allows (owner 2026-11-10).

Owner 2026-11-10, verbatim (the Anaguma stock answer, docs/anaguma-design.md section 9):
「資金に余裕があるとき魔法棒を塔でチャージする」.  The pocket (anaguma) spends one charge per
cell, four to eight against an animal pack; no wand is bought for it.

Who: a character that is not a Magic-Eater (its staff sequence already charges a carried
Stone to Mud wand to its maximum and absorbs it, me_staff_sequence "Extras"), carrying an
identified Stone to Mud wand that the Tower's recharge-all would fill (``short``:
morivant_tower.charges_after_recharge above the shown charges).  The Q2 Tower trip
(q2_tower_recharge) keeps its own errand while it applies.

「資金に余裕」: after the trip -- the inn's fares to Morivant and back and the Tower's
whole-pack price (morivant_tower.expedition_cost) -- the gold still covers the same reserve
as the other optional spending (armor_smith.gold_line's: the full departure resupply and an
open gold target).  It never starts a fundraising run, and it never reads rumours: Morivant
must already be listed (the Q2 trip and the Magic-Eater sequence unlock it).

When and how, as the armour smith's errand (armor_smith): it starts at the recall read
(policy_town ``_town_special_key``), once per stay in town; while the trip is under way it is
the town's owner (``trip_key``, policy_quest).  The legs are the inn's teleport
(``_town_teleport_key``); at Morivant the Tower of Sorcery's 'a' recharges the whole pack
(lib/edit/towns/03_Morivant.jsonc building 8, market/building-recharger.cpp
building_recharge_all; observed_input answers its question, morivant_tower.RECHARGE_ALL_REASONS),
then the inn takes the player back to the town the trip started from.  Any leg that cannot go
on ends the errand for the stay and the read goes on: never a stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import armor_smith, morivant_tower
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND
from hengbot.policy_constants import MORIVANT_TOWN_ID, TOWN_TELEPORT_COST
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY

REASON = "town:wand-recharge:"
RECHARGE_REASON = REASON + "recharge-all"
APPROACH_REASON = REASON + "approach"
TRAVEL_REASON = REASON + "travel"
RETURN_REASON = REASON + "return"
PRODUCER = "cross-town"  # the claim family of every key of this owner
ATTEMPT_LIMIT = 2


@dataclass
class WandRechargeStay:
    """This stay in town's facts: the inn's hops stay in it, a dungeon floor ends it."""
    origin: int | None = None   # the town the trip started from: the trip is under way
    away: bool = False          # the trip has left ``origin``
    travelled: bool = False     # the stay's one trip has started
    recharged: bool = False     # the Tower's 'a' filled the wands
    closed: bool = False        # a leg failed: the read goes on
    attempts: int = 0
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)


def state(policy) -> WandRechargeStay:
    record = getattr(policy, "_wand_recharge_stay", None)
    if record is None:
        record = policy._wand_recharge_stay = WandRechargeStay()
    return record


def observe(policy, snapshot) -> None:
    """Every decision: a dungeon floor ends the stay."""
    if snapshot.floor_key[1] > 0:
        policy._wand_recharge_stay = None


def short(snapshot) -> list:
    """The identified Stone to Mud wands the Tower's recharge-all would fill."""
    return [item for item in snapshot.inventory
            if item.tval == TVAL_WAND and item.sval == SV_WAND_STONE_TO_MUD and item.aware
            and item.known and morivant_tower.charges_after_recharge(item) > item.charges]


def applies(policy, snapshot) -> bool:
    if (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            or getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
            or not morivant_tower.morivant_unlocked(snapshot) or not short(snapshot)):
        return False
    from hengbot import q2_tower_recharge
    return not q2_tower_recharge.applies(policy, snapshot)


def spare(policy, snapshot, fares: int) -> bool:
    """「資金に余裕」: the trip leaves the optional-spending reserve in hand."""
    reserve = policy._full_departure_resupply_reserve(snapshot)
    if reserve is None:
        return False
    target = getattr(policy, "_supply_stockout_gold_target", None) or 0
    cost = morivant_tower.recharge_cost(snapshot) + fares * TOWN_TELEPORT_COST
    return snapshot.player.gold - cost >= max(reserve, target)


def _close(record) -> None:
    record.closed = True
    record.origin = None


def _leg_key(policy, snapshot, record, destination: int, reason: str) -> str | None:
    if armor_smith.no_progress(record, snapshot):
        return _close(record)
    key = policy._town_teleport_key(snapshot, destination, producer=PRODUCER, reason=reason)
    return key if key is not None else _close(record)


def _recharge_key(policy, snapshot, record) -> str | None:
    if not short(snapshot):
        record.recharged = True
        return None
    if record.attempts >= ATTEMPT_LIMIT or armor_smith.no_progress(record, snapshot):
        return _close(record)
    step, enters = morivant_tower.building_step(
        policy, snapshot, morivant_tower.TOWER_OF_SORCERY, family=PRODUCER)
    if step is None:
        return _close(record)
    if not enters:
        key = morivant_tower.approach_key(
            policy, snapshot, morivant_tower.TOWER_OF_SORCERY, step, APPROACH_REASON)
        return key if key is not None else _close(record)
    record.attempts += 1
    policy.last_reason = RECHARGE_REASON
    return policy._step_toward(snapshot, step, tail=morivant_tower.RECHARGE_ALL_TAIL)


def _errand_key(policy, snapshot, record) -> str | None:
    town = policy._effective_town_id(snapshot)
    if record.origin is not None:
        if town != record.origin:
            record.away = True
        if town == MORIVANT_TOWN_ID and not record.recharged:
            key = _recharge_key(policy, snapshot, record)
            if key is not None or record.closed:
                return key
        if town == MORIVANT_TOWN_ID and record.origin != MORIVANT_TOWN_ID:
            return _leg_key(policy, snapshot, record, record.origin, RETURN_REASON)
        if town == record.origin and (record.away or record.recharged):
            record.origin = None  # back where the trip started
            return None
        # The walk to the inn takes many boards; each asks the leg again.
        return _leg_key(policy, snapshot, record, MORIVANT_TOWN_ID, TRAVEL_REASON)
    if record.travelled or not applies(policy, snapshot):
        return None
    if town == MORIVANT_TOWN_ID:
        if not spare(policy, snapshot, 0):
            return None
        record.origin, record.travelled = town, True
        return _recharge_key(policy, snapshot, record)
    if not spare(policy, snapshot, 2):
        return None
    key = _leg_key(policy, snapshot, record, MORIVANT_TOWN_ID, TRAVEL_REASON)
    if key is not None:
        record.origin, record.travelled = town, True
    return key


def trip_key(policy, snapshot) -> str | None:
    """While the trip is under way this owner holds the town's board."""
    record = state(policy)
    if record.origin is None or record.closed or not armor_smith.board_allows(policy, snapshot):
        return None
    return _errand_key(policy, snapshot, record)


def town_key(policy, snapshot) -> str | None:
    """At the recall read: the next key of the errand, or None for the read."""
    record = state(policy)
    if record.closed or not armor_smith.board_allows(policy, snapshot):
        return None
    return _errand_key(policy, snapshot, record)
