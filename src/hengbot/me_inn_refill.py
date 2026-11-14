"""A night at the inn before a quest whose acceptance counted the absorbed powers full.

Owner 2026-11-14 (n1-b's Q25 evaluation): 「ドラゴンの火炎の魔法棒ならもっと威力があるし成功率も
担保できている。比較方法が怠惰ではないか？」.  A quest's ranged requirement
(quest_ranged_force) counts a Magic-Eater's absorbed attack powers at their capacity, the
charges the inn gives back: cmd-building/cmd-inn.cpp stay_inn -> charge_magic_eating_energy
sets every absorbed staff and wand to ``count * EATER_CHARGE`` (full) and every rod's charge
to 0 (ready), and back_to_health ends a stun.  So before the character enters such a quest
with a counted power short of that capacity, it walks to the town's inn and stays the night
('r', "Rest for the night", BACT_REST in every inn of lib/edit/towns 01-04), as the owner's
Q25 rule 「休んで充填を待つ」 (2026-11-13) has it inside the quest.

The inn refuses a poisoned or cut character (is_healthy_stay) and one without the price
(cmd-building.cpp); the walk waits for neither: the character enters as it is, the powers
regenerate on their own (hpmp/hp-mp-regenerator.cpp regenmagic) and Q25's own recharge
rest (quest25_battle) fills them inside.  One stay per stay in town: the key is posted once,
a dungeon floor (the quest's floor included) starts a new stay.  The fight does not count
a refill it has not seen: the displayed lists are browsed again afterwards
(me_powers_refresh, and quest25_battle's own read of a stale list on entry).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import armor_smith, me_powers_refresh, morivant_tower, quest_ranged_force
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.policy_constants import LEAVE_STORE_KEY, TOWN_TELEPORT_BUILDING_TYPES

REST_KEY = "r"
# lib/edit/towns: the inn's "Rest for the night" price by town (01 Outpost, 02 Telmora,
# 03 Morivant: 20; 04 Angwil: 25); the inn building is TOWN_TELEPORT_BUILDING_TYPES'.
REST_PRICE = {0: 20, 1: 20, 2: 20, 3: 25}
PRODUCER = "quest-request"  # the claim family (town_arbiter: "fixedquest:")
REASON = "fixedquest:inn-refill:"
APPROACH_REASON = REASON + "approach"
REST_REASON = REASON + "rest"
REST_KEY_PATTERN = rf"[1-9]{REST_KEY}{LEAVE_STORE_KEY}"


@dataclass
class InnRefillStay:
    """This stay in town's facts: a dungeon floor ends it."""
    posted_turn: int | None = None  # the stay's key went out on this turn
    closed: bool = False  # the walk could not go on: enter as it is
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)


def state(policy) -> InnRefillStay:
    record = getattr(policy, "_me_inn_refill_stay", None)
    if record is None:
        record = policy._me_inn_refill_stay = InnRefillStay()
    return record


def observe(policy, snapshot) -> None:
    """Every decision: a dungeon floor ends the stay."""
    if snapshot.floor_key[1] > 0 or snapshot.floor_key[2] > 0:
        policy._me_inn_refill_stay = None


def _ranged(policy, snapshot, quest_id: int) -> dict | None:
    profile = policy.approved_quest_strategy(quest_id)
    if profile is None:
        return None
    return policy._strategy_force_for_snapshot(snapshot, profile).get("ranged")


def due(policy, snapshot, quest_id: int) -> bool:
    """The character should stay at this town's inn before it enters ``quest_id``."""
    player = snapshot.player
    if getattr(player, "class_id", None) != PLAYER_CLASS_MAGIC_EATER or not snapshot.in_town:
        return False
    town = policy._effective_town_id(snapshot)
    if (town not in TOWN_TELEPORT_BUILDING_TYPES or player.gold < REST_PRICE[town]
            or player.poisoned or player.cut):
        return False
    record = state(policy)
    if record.posted_turn is not None or record.closed:
        return False
    ranged = _ranged(policy, snapshot, quest_id)
    return ranged is not None and quest_ranged_force.absorbed_short(policy, snapshot, ranged)


def _entry_admitted(policy, snapshot, quest_id: int) -> bool:
    """The quest would be entered now (the entry's own conditions, read without its commits):
    a night bought for an entry that waits on something else is spent for nothing."""
    from hengbot import quest_force_rows
    from hengbot.town_terminal import gather_quest_entry, verdict_quest_entry

    return (not quest_force_rows.departure_speed_short(policy, snapshot, quest_id)
            and verdict_quest_entry(gather_quest_entry(policy, snapshot, quest_id)).admitted)


def _close(record) -> None:
    record.closed = True


def entry_key(policy, snapshot, quest_id: int) -> str | None:
    """The next key of the walk to the inn and the stay, or None to enter as it is."""
    if (not due(policy, snapshot, quest_id) or not armor_smith.board_allows(policy, snapshot)
            or not _entry_admitted(policy, snapshot, quest_id)):
        return None
    record = state(policy)
    if armor_smith.no_progress(record, snapshot):
        return _close(record)
    building = TOWN_TELEPORT_BUILDING_TYPES[policy._effective_town_id(snapshot)]
    step, enters = morivant_tower.building_step(policy, snapshot, building, family=PRODUCER)
    if step is None:
        return _close(record)
    if not enters:
        key = morivant_tower.approach_key(policy, snapshot, building, step, APPROACH_REASON)
        return key if key is not None else _close(record)
    policy.last_reason = REST_REASON
    key = policy._step_toward(snapshot, step, tail=REST_KEY + LEAVE_STORE_KEY)
    if key is None:
        return _close(record)
    record.posted_turn = snapshot.turn
    # The lists the fight reads show the refill only once displayed again.
    me_powers_refresh.request_refresh(policy)
    return key
