"""The armour smith: spare gold above a line raises worn armour (owner 2026-11-04).

Owner 2026-11-04 「防具鍛冶の利用について。資金が潤沢なとき、防具鍛冶を利用してACを
強化できる」: with 30,000 gold or more, the worn armour is raised, lowest shown
modifier first, until the gold falls below the line.  After shopping and Home,
before departure; never a departure condition.

The errand starts at the recall read (policy_town ``_town_special_key``), after
the spare *Identify* and before the read: every departure condition already
holds there, so every survival need, quest reward, Tower errand, purchase and
Home need of the visit has had the board.  An active recall, a monster beside
the player or a hit taken leaves the board to the others (the town hunt is ahead
of every errand); the raises wait for the next visit.

The Outpost the bots play (TownDefinitionList "normal", 01_Outpost_Full) has only
the inn, the mayor and building 13: no smith (01_Outpost_Lite's belongs to the
lite_town birth option).  From a town without a smith the errand takes the inn's
teleport (500 gold a leg) to the cheapest listed town with one, and back to where
it started; on the way it is the town's owner (``trip_key``, as the Tower trips),
so the fresh visit of the smith's town does not go shopping.  One trip per stay
in town; a stay ends on a dungeon floor (``observe``).  Any leg that cannot go on
ends the errand and the read goes on: never a stop.

Game facts (lib/edit/towns, BACT_ENCHANT_ARMOR = 24, letter 'a', open to all):
``SMITHS`` below.  cmd-building.cpp charges the member price to an owner of the
building (market/building-service.cpp is_owner: class only, these buildings set
no race or realm), the other price to everyone else.

market/building-enchanter.cpp enchant_item: the chooser takes USE_INVEN |
USE_EQUIP with ItemEntity::is_protector.  It opens on the pack when the pack
holds any armour and on the equipment otherwise; a letter of the equipment page
is the slot's own (label_to_equipment).  ``to_a < lev / 5`` guards the raise and
ENCH_FORCE skips both of enchant_equipment's rolls, so below the cap a raise
always lands for one price; at the cap the game prints 「改良に失敗した。」 and
charges nothing.  A curse does not refuse it (at to_a >= 0 a raise breaks a curse
that is not heavy or permanent one time in four).

Fair play: flavor-describer.cpp shows a known protector as ``[ac,+to_a]`` and an
unknown one as ``[ac]``.  The modifier is read from that shown name only, so an
unknown item has no modifier and is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from hengbot import morivant_tower
from hengbot.policy_constants import (
    EQUIPMENT_SLOT_KEY, LEAVE_STORE_KEY, STORE_STUCK_LIMIT, TOWN_TELEPORT_COST,
)
from hengbot.warrior_defense_evaluator import PROTECTOR_TVALS

GOLD_LINE = 30000  # owner 2026-11-04: at or above it raise, below it stop
LEVELS_PER_ENCHANT = 5  # enchant_item: maxenchant = lev / 5
# ENCH_FORCE always lands below the cap, so a raise that left the shown name as
# it was is a misread of the board, not bad luck: never address that state again.
ATTEMPTS_WITHOUT_EFFECT = 1
ENCHANT_ARMOR_KEY = "a"
RAISE_REASON = "town:armor-smith:raise"
APPROACH_REASON = "town:armor-smith:approach"
TRAVEL_REASON = "town:armor-smith:travel"
RETURN_REASON = "town:armor-smith:return"
PRODUCER = "curse-enchant"  # the claim family of every key of this owner
RAISE_KEY_PATTERN = rf"[1-9](?:{ENCHANT_ARMOR_KEY}/[a-z])+\x1b"
_SHOWN_MODIFIER = re.compile(r"\[\d+,([+-]\d+)\]")
# BACT_ENCHANT_ARMOR's owners: Fighters Hall (Warrior, Samurai, Cavalry,
# Berserker, Weaponsmith), Paladins Guild (Paladin).
_FIGHTERS = frozenset({0, 19, 22, 23, 24})
_PALADINS = frozenset({5})


@dataclass(frozen=True)
class Smith:
    building: int
    member_price: int
    other_price: int
    owners: frozenset[int]

    def price(self, class_id: int) -> int:
        return self.member_price if class_id in self.owners else self.other_price


# town id -> its armour smiths (lib/edit/towns 02..04; the Outpost and Zul have none).
SMITHS = {
    1: (Smith(7, 300, 600, _FIGHTERS), Smith(12, 300, 600, _PALADINS)),
    2: (Smith(7, 300, 600, _FIGHTERS), Smith(12, 400, 1000, _PALADINS)),
    3: (Smith(7, 200, 500, _FIGHTERS), Smith(12, 240, 440, _PALADINS)),
}


@dataclass
class ArmorSmithStay:
    """This stay in town's facts: the inn's hops stay in it, a dungeon floor ends it."""
    attempts: dict = field(default_factory=dict)  # (slot, shown name) -> raises posted
    origin: int | None = None  # the town the trip starts from: the trip is under way
    destination: int | None = None  # the smith's town of the trip
    away: bool = False  # the trip has left ``origin`` (its walk to the inn is still in it)
    travelled: bool = False  # the stay's one trip has started
    closed: bool = False  # a leg failed: the read goes on
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)


def state(policy) -> ArmorSmithStay:
    record = getattr(policy, "_armor_smith_stay", None)
    if record is None:
        record = policy._armor_smith_stay = ArmorSmithStay()
    return record


def observe(policy, snapshot) -> None:
    """Every decision: a dungeon floor ends the stay."""
    if snapshot.floor_key[1] > 0:
        policy._armor_smith_stay = None


def shown_modifier(item) -> int | None:
    """The modifier the player reads in the item's name; None when not shown."""
    if not item.known:
        return None
    found = _SHOWN_MODIFIER.search(item.name)
    return int(found.group(1)) if found else None


def gold_line(policy, snapshot) -> int | None:
    """The line, or an existing reserve above it; None when a price is unknown.

    The same reserve as the other optional spending (the Black Market's,
    ``_black_market_optional_reserve_cap``), and an open gold target.
    """
    reserve = policy._full_departure_resupply_reserve(snapshot)
    if reserve is None:
        return None
    target = getattr(policy, "_supply_stockout_gold_target", None) or 0
    return max(GOLD_LINE, reserve, target)


def raises(policy, snapshot, price: int, fare: int = 0) -> list:
    """The worn armour to raise on one entry, lowest shown modifier first.

    ``fare`` is the gold the trip spends before the first raise.
    """
    line = gold_line(policy, snapshot)
    if line is None:
        return []
    cap = snapshot.player.level // LEVELS_PER_ENCHANT
    attempts = state(policy).attempts
    order = list(EQUIPMENT_SLOT_KEY)
    shown = {}
    for item in snapshot.equipment:
        modifier = shown_modifier(item) if item.tval in PROTECTOR_TVALS else None
        if (modifier is not None and modifier < cap
                and attempts.get((item.slot, item.name), 0) < ATTEMPTS_WITHOUT_EFFECT):
            shown[item.slot] = [modifier, item]
    gold = snapshot.player.gold - fare
    plan = []
    while gold >= line and shown:
        slot = min(shown, key=lambda name: (shown[name][0], order.index(name)))
        plan.append(shown[slot][1])
        gold -= price
        shown[slot][0] += 1
        if shown[slot][0] >= cap:
            del shown[slot]
    return plan


def _board_allows(policy, snapshot) -> bool:
    """Survival first: no hit, no monster beside the player, no state that would refuse."""
    player = snapshot.player
    return (snapshot.in_town and snapshot.store is None and not player.recalling
            and not getattr(policy, "_took_damage", False)
            and not policy._physical_adjacent_hostiles(snapshot)
            and not (player.blind or player.confused or player.hallucinated or player.paralyzed))


def _town_smith(town_id: int, class_id: int) -> Smith | None:
    """The town's cheaper smith for this class (the table's first of equals)."""
    return min(SMITHS.get(town_id, ()), key=lambda smith: smith.price(class_id), default=None)


def _trip_destination(snapshot) -> int | None:
    """The listed town whose smith is the cheapest; None when none is listed."""
    class_id = snapshot.player.class_id
    listed = [town for town in SMITHS if town in (snapshot.visited_town_ids or ())]
    return min(listed, key=lambda town: _town_smith(town, class_id).price(class_id), default=None)


def _no_progress(record, snapshot) -> bool:
    """The walk came back to one cell with nothing changed."""
    progress = (snapshot.player.gold, tuple(item.name for item in snapshot.equipment))
    if record.progress != progress:
        record.progress = progress
        record.positions = {}
    position = snapshot.player.position
    record.positions[position] = record.positions.get(position, 0) + 1
    return record.positions[position] >= STORE_STUCK_LIMIT


def _close(record) -> None:
    """A leg cannot go on: the stay does without the smith; the read goes on."""
    record.closed = True
    record.origin = None


def _raise_key(policy, snapshot, record, smith: Smith, plan: list) -> str | None:
    if _no_progress(record, snapshot):
        return _close(record)
    step, enters = morivant_tower.building_step(
        policy, snapshot, smith.building, family=PRODUCER)
    if step is None:
        return _close(record)
    if not enters:
        key = morivant_tower.approach_key(policy, snapshot, smith.building, step, APPROACH_REASON)
        return key if key is not None else _close(record)
    tail = "".join(f"{ENCHANT_ARMOR_KEY}/{EQUIPMENT_SLOT_KEY[item.slot]}" for item in plan)
    policy.last_reason = RAISE_REASON
    key = policy._step_toward(snapshot, step, tail=tail + LEAVE_STORE_KEY)
    if key is None:
        return _close(record)
    for address in {(item.slot, item.name) for item in plan}:
        record.attempts[address] = record.attempts.get(address, 0) + 1
    return key


def _leg_key(policy, snapshot, record, destination: int, reason: str) -> str | None:
    if _no_progress(record, snapshot):
        return _close(record)
    key = policy._town_teleport_key(snapshot, destination, producer=PRODUCER, reason=reason)
    return key if key is not None else _close(record)


def _errand_key(policy, snapshot, record) -> str | None:
    town = policy._effective_town_id(snapshot)
    class_id = snapshot.player.class_id
    if record.origin is not None:
        if town != record.origin:
            record.away = True
        elif record.away:
            record.origin = None  # back where the trip started
            return None
        else:
            # The walk to the inn takes many boards; each asks the leg again.
            return _leg_key(policy, snapshot, record, record.destination, TRAVEL_REASON)
    smith = _town_smith(town, class_id)
    if smith is not None:
        plan = raises(policy, snapshot, smith.price(class_id))
        if plan:
            return _raise_key(policy, snapshot, record, smith, plan)
        if record.origin is None:
            return None
        return _leg_key(policy, snapshot, record, record.origin, RETURN_REASON)
    if record.origin is not None or record.travelled:
        return None
    destination = _trip_destination(snapshot)
    if destination is None:
        return None
    price = _town_smith(destination, class_id).price(class_id)
    if not raises(policy, snapshot, price, TOWN_TELEPORT_COST):
        return None
    key = _leg_key(policy, snapshot, record, destination, TRAVEL_REASON)
    if key is not None:
        record.origin, record.destination, record.travelled = town, destination, True
    return key


def trip_key(policy, snapshot) -> str | None:
    """While the trip is under way this owner holds the town's board."""
    record = state(policy)
    if record.origin is None or record.closed or not _board_allows(policy, snapshot):
        return None
    return _errand_key(policy, snapshot, record)


def town_key(policy, snapshot) -> str | None:
    """At the recall read: the next key of the errand, or None for the read."""
    record = state(policy)
    if record.closed or not _board_allows(policy, snapshot):
        return None
    return _errand_key(policy, snapshot, record)
