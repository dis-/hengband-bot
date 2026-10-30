"""Recharge a short Stone to Mud wand at Morivant's Tower before Q2.

Owner 2026-10-31: 「Q2の岩石溶解 - 回数を数える」 (one charge per breach wall)
and 「モリバントの塔で充填」 (a short wand is recharged at the Tower, not by
Scrolls of Recharging).  For a character that is not a Magic-Eater (whose
staff sequence keeps its own Tower trips), when Q2 is the next fixed quest
and its wall_breach carry is short only because the carried wand lacks
charges that the Tower's recharge-all supplies:

 rumor    -- unlock Morivant through the inn rumors if it is not listed;
 travel   -- the inn teleport to Morivant;
 recharge -- the Tower's 'a' recharge-all (the whole pack, its game price);
 onward   -- the inn teleport from Morivant straight to Telmora (owner
             2026-10-31 「モリバントからテルモラへ直行」), where the ordinary Q2
             request takes over.

The gold target of each leg is the Tower total over the whole pack, the
fares to Morivant and on to Telmora plus the return fare that
``_town_teleport_key`` keeps in hand when leaving for a town other than the
Outpost, the rumor reads when Morivant is still locked, and the unmet
departure supplies; a short purse starts one run of the existing
fundraising owners (a purse short at the Tower returns to the Outpost).
Every step that cannot proceed ends in the named final stop
``quest:blocked:q2-tower-recharge`` (detail in the record).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import morivant_tower
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND
from hengbot.policy_constants import (
    FIXED_QUEST_TOWNS, MORIVANT_TOWN_ID, OUTPOST_TOWN_ID, Q2_BREACH_WALL_COUNT,
    QUEST_STATUS_UNTAKEN, STORE_STUCK_LIMIT, TOWN_TELEPORT_COST, WAIT_KEY,
)
from hengbot.protocol import PROTOCOL_LEGACY, PROTOCOL_SCREEN_PARITY

REASON = "fixedquest:q2-recharge:"
RECHARGE_ALL_REASON = REASON + "recharge-all"
STOP_REASON = "quest:blocked:q2-tower-recharge"
Q2_QUEST_ID = 2
TELMORA_TOWN_ID = FIXED_QUEST_TOWNS[Q2_QUEST_ID]
FUNDRAISE_RUN_LIMIT = 6
RUMOR_BATCH_LIMIT = 10
ATTEMPT_LIMIT = 3


@dataclass
class Q2TowerRecharge:
    """The trip's own facts; the board supplies everything else."""
    active: bool = False            # the trip started: finish it in Telmora
    fundraise_runs: int = 0
    fundraise_target: int | None = None
    rumor_batches: int = 0
    attempts: int = 0
    pending: int | None = None      # the wand's charges before a posted 'a'
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)
    failure: str | None = None


def state(policy) -> Q2TowerRecharge:
    record = getattr(policy, "_q2_tower_recharge", None)
    if record is None:
        record = policy._q2_tower_recharge = Q2TowerRecharge()
    return record


def _stone_to_mud(snapshot) -> list:
    return [item for item in snapshot.inventory
            if item.tval == TVAL_WAND and item.sval == SV_WAND_STONE_TO_MUD]


def _wands(snapshot) -> list:
    """The Stone to Mud wands whose charges the player sees."""
    return [item for item in _stone_to_mud(snapshot) if item.aware and item.known]


def recharge_meets_breach(policy, snapshot) -> bool:
    """The wall_breach carry is short and the Tower's recharge meets it."""
    profile = policy.approved_quest_strategy(Q2_QUEST_ID)
    if profile is None:
        return False
    tools = profile.required_force.get("utility_tools", {})
    required = int(tools.get("wall_breach", 0)) if isinstance(tools, dict) else 0
    if required <= 0:
        return False
    have = policy._quest_named_item_count(snapshot, "utility_tools", "wall_breach")
    wands = _wands(snapshot)
    if have >= required or not wands:
        return False
    # The count is diggers + charges // walls over the charged Stone to Mud
    # wands (_quest_named_item_count); the Tower fills each seen wand stack.
    counted = sum(item.charges for item in _stone_to_mud(snapshot) if item.charges > 0)
    diggers = have - counted // Q2_BREACH_WALL_COUNT
    seen = sum(item.charges for item in wands if item.charges > 0)
    filled = sum(morivant_tower.wand_charges_after_recharge(item) for item in wands)
    return diggers + (counted - seen + filled) // Q2_BREACH_WALL_COUNT >= required


def applies(policy, snapshot) -> bool:
    """A non-Magic-Eater whose next fixed quest is an untaken approved Q2."""
    if (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            or getattr(snapshot, "protocol_version", PROTOCOL_LEGACY) < PROTOCOL_SCREEN_PARITY
            or not getattr(snapshot, "quests", None)
            or policy.approved_quest_strategy(Q2_QUEST_ID) is None):
        return False
    head = policy._fixed_quest_head(snapshot)
    return (head is not None and head.id == Q2_QUEST_ID
            and head.status == QUEST_STATUS_UNTAKEN)


def _stop(policy, detail: str) -> str:
    state(policy).failure = detail
    policy.last_reason = STOP_REASON
    return WAIT_KEY


def _supplies(policy, snapshot) -> int:
    """Gold the departure plan's unmet survival supplies cost (bought first)."""
    return policy._required_departure_supply_reserve(snapshot, quest_carry=False) or 0


def onward_cost(snapshot) -> int:
    """Gold at the Tower: the recharge and the Telmora leg.

    _town_teleport_dispatch_key sends the inn to a town other than the
    Outpost only with two fares in hand (the leg and the way back).
    """
    return morivant_tower.recharge_cost(snapshot) + 2 * TOWN_TELEPORT_COST


def trip_cost(snapshot, supplies: int, rumors: bool) -> int:
    """The whole trip: the fare to Morivant, the Tower and the Telmora leg."""
    expedition = (morivant_tower.rumor_expedition_cost(snapshot, supplies) if rumors
                  else morivant_tower.expedition_cost(snapshot, supplies))
    # expedition_cost carries two fares (to Morivant, on to Telmora); the
    # third is the way back that the Telmora leg needs in hand.
    return expedition + TOWN_TELEPORT_COST


def _fundraising_owns(policy) -> bool:
    record = state(policy)
    return (policy._fundraising_mode in {"prepare", "mine", "scavenge"}
            and record.fundraise_target is not None
            and getattr(policy, "_supply_stockout_gold_target", None) == record.fundraise_target)


def _fundraise(policy, snapshot, target: int, why: str) -> str:
    record = state(policy)
    if record.fundraise_runs >= FUNDRAISE_RUN_LIMIT:
        return _stop(policy, f"fundraise-limit:{why}:{target}")
    record.fundraise_runs += 1
    record.fundraise_target = target
    morivant_tower.start_fundraising_run(policy, snapshot, target)
    policy.last_reason = f"{REASON}fundraise:{why}:{target}"
    return WAIT_KEY


def _travel(policy, snapshot, destination: int, step: str) -> str:
    key = policy._town_teleport_key(
        snapshot, destination, producer="quest-request", reason=f"{REASON}{step}")
    if key is None:
        return _stop(policy, f"{step}-unavailable:{policy.last_reason}")
    return key


def _settle_pending(policy, snapshot) -> None:
    record = state(policy)
    if record.pending is None:
        return
    before, record.pending = record.pending, None
    if sum(item.charges for item in _wands(snapshot)) > before:
        record.attempts = 0


def _no_progress(policy, snapshot, phase: str) -> bool:
    record = state(policy)
    progress = (phase, snapshot.player.gold, policy._effective_town_id(snapshot),
                tuple((it.slot, it.name, it.count, it.charges) for it in snapshot.inventory))
    if record.progress != progress:
        record.progress = progress
        record.positions = {}
    position = snapshot.player.position
    record.positions[position] = record.positions.get(position, 0) + 1
    return record.positions[position] >= STORE_STUCK_LIMIT


def _recharge_key(policy, snapshot) -> str:
    if snapshot.player.gold < onward_cost(snapshot):
        # Return with the reserved fare; the Outpost leg funds the recharge.
        return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-for-funds")
    step, enters = morivant_tower.building_step(
        policy, snapshot, morivant_tower.TOWER_OF_SORCERY)
    if step is None:
        return _stop(policy, "tower-of-sorcery-route-unavailable")
    if not enters:
        policy.last_reason = f"{REASON}approach-tower"
        return policy._step_toward(snapshot, step)
    record = state(policy)
    record.attempts += 1
    if record.attempts > ATTEMPT_LIMIT:
        return _stop(policy, "recharge-no-progress")
    record.pending = sum(item.charges for item in _wands(snapshot))
    policy.last_reason = RECHARGE_ALL_REASON
    return policy._step_toward(snapshot, step, tail=morivant_tower.RECHARGE_ALL_TAIL)


def town_key(policy, snapshot, hostiles) -> str | None:
    """Sole non-emergency town owner while the Q2 Tower trip is unfinished."""
    if not snapshot.in_town or snapshot.store is not None or not applies(policy, snapshot):
        return None
    record = state(policy)
    _settle_pending(policy, snapshot)
    if record.failure:
        return _stop(policy, record.failure)
    town = policy._effective_town_id(snapshot)
    short = recharge_meets_breach(policy, snapshot)
    if not short and not (record.active and town == MORIVANT_TOWN_ID):
        # Nothing to recharge, or the trip left Morivant.
        record.active = False
        return None
    gold = snapshot.player.gold
    if _fundraising_owns(policy):
        return None
    record.fundraise_target = None
    if policy._physical_adjacent_hostiles(snapshot):
        return None
    if not short:
        phase = "onward"
    elif not morivant_tower.morivant_unlocked(snapshot):
        phase = "rumor"
    elif town != MORIVANT_TOWN_ID:
        phase = "travel"
    else:
        phase = "recharge"
    if _no_progress(policy, snapshot, phase):
        return _stop(policy, f"no-progress:{phase}")
    supplies = _supplies(policy, snapshot)
    if phase == "rumor":
        needed = trip_cost(snapshot, supplies, rumors=True)
        if gold < needed:
            return _fundraise(policy, snapshot, needed, "rumor-travel-recharge")
        if record.rumor_batches >= RUMOR_BATCH_LIMIT:
            return _stop(policy, "morivant-rumor-exhausted")
        record.active = True
        key, batched = morivant_tower.rumor_key(policy, snapshot)
        if batched:
            record.rumor_batches += 1
        return key
    if phase == "travel":
        needed = trip_cost(snapshot, supplies, rumors=False)
        if gold < needed:
            if town != OUTPOST_TOWN_ID:
                return _travel(policy, snapshot, OUTPOST_TOWN_ID, "return-for-funds")
            return _fundraise(policy, snapshot, needed, "travel-recharge")
        record.active = True
        return _travel(policy, snapshot, MORIVANT_TOWN_ID, "travel-morivant")
    if phase == "recharge":
        record.active = True
        return _recharge_key(policy, snapshot)
    # Owner 2026-10-31 「モリバントからテルモラへ直行」: the same errand latch
    # as the ordinary Q2 inn travel, so the Telmora owners bring it home.
    key = _travel(policy, snapshot, TELMORA_TOWN_ID, "travel-telmora")
    if policy.last_reason != STOP_REASON:
        policy._telmora_q2_errand = True
    return key
