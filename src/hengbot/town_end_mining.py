"""The town end's mining cycle: unmet departure conditions are retried.

Owner 2026-11-02 「満たせなければ採掘を1サイクル行い再度トライ。条件未達の
出発は拒否する。」: a town visit that no owner can continue, with departure
conditions unmet, neither departs with them unmet nor stops.  It starts one
mining (fundraising) cycle through the existing fundraising owners and
retries the conditions when the run is back in town.  The mining departure
keeps its own gates (owner 2026-11-01 「採掘の要求品が優先」,
policy_fundraising._mining_departure_ready); only when the cycle itself cannot
leave does the town end stop by name (town_terminal.town_end_key).

The cycle is an ordinary one-run mining set opened in preparation mode (the
shape of the identify-staff and recall stockout runs).  Like those runs it
mines its floor out instead of returning on the gold target
(``_restock_time_pass_run``): the conditions it retries wait on shop restocks
as much as on gold.  The run's return to town ends the set; the next
unanswered board then retries the conditions, and starts the next cycle when
they are still unmet (no cap: the owner gave none).

The record (the conditions unmet when the cycle started, how many cycles in
a row met the same conditions and the cycle's stage) is kept beside the
decision log, so a restart neither forgets an open cycle nor starts a second
one for the same attempt.  Like the other restart records (breeder_floor_
record, the town visit's purchases) the first board of a process restores it
only at the same or a later game turn.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Any

from hengbot.home_identification import rearmed_home_route_key
from hengbot.model import DUNGEON_YEEK_CAVE, STORE_HOME
from hengbot.policy_constants import WAIT_KEY

MINING_MODES = frozenset({"prepare", "mine", "scavenge"})
START_REASON = "town:end-mining-cycle"
# Stages: prepared in town, on the run's floor, back in town (cycle done),
# or departed ordinarily because the retried conditions held in town.
STAGE_TOWN = "town"
STAGE_RUN = "run"
STAGE_RETURNED = "returned"
STAGE_DEPARTED = "departed"
OPEN_STAGES = frozenset({STAGE_TOWN, STAGE_RUN})


@dataclass(frozen=True)
class TownEndMiningCycle:
    """One mining cycle the town end started for unmet departure conditions."""

    unmet: tuple[str, ...]
    cycles: int
    started_turn: int
    stage: str
    visit_epoch: int | None = None


def cycle(policy: Any) -> TownEndMiningCycle | None:
    return getattr(policy, "_town_end_mining_cycle", None)


def outstanding(policy: Any) -> bool:
    """Whether the town end's cycle still owns the open mining set."""
    record = cycle(policy)
    return (record is not None and record.stage in OPEN_STAGES
            and policy._fundraising_mode in MINING_MODES)


def mining_set_open(policy: Any) -> bool:
    """Whether any mining set (this cycle's or another owner's) is open."""
    return policy._fundraising_mode in MINING_MODES


def closed_in_town(policy: Any) -> bool:
    """Whether this visit's cycle was closed before it left town.

    Another owner (the opening Q34's torch purchase, a conquest departure)
    closing the set in town means the cycle cannot leave on this visit; a new
    cycle would only be closed again.
    """
    record = cycle(policy)
    return (record is not None and record.stage == STAGE_TOWN
            and record.visit_epoch == policy._town_visit_epoch
            and not mining_set_open(policy))


def home_kit_route_key(policy: Any, board: Any) -> str | None:
    """Route a tried Home for the kit an open mining set can still take there.

    Owner 2026-11-01 「採掘の要求品が優先」: the set's kit comes before the town
    end judges anything.  n1-b life-306 (2026-11-03 21:33, 22:11): a Home pass
    that took an identification candidate latched Home as tried with the
    digger and the detection on its shelf (and no room for them until the
    candidate was sold).  No owner answered, the open set made the verdict a
    stop, and the visit stopped under town:blocked:survival:cure_critical_ready.
    Each state of the visit re-arms Home once, so a take that still cannot be
    made ends in that named stop.
    """
    if (not mining_set_open(policy)
            or STORE_HOME not in policy._town_store_attempted
            or policy._fundraising_kit_secured(board)
            or not policy._has_withdrawable_digging_tool(board)
            or not policy._has_withdrawable_treasure_detection(board)):
        return None
    signature = ("home-mining-kit", policy._town_observable_effect_state(board))
    rearmed = policy._town_visit_ledger.rearmed_work_signatures
    if signature in rearmed:
        return None
    rearmed.add(signature)
    return rearmed_home_route_key(policy, board)


def start(policy: Any, board: Any, unmet: tuple[str, ...]) -> str:
    """Open one mining cycle for ``unmet`` through the fundraising owners."""
    previous = cycle(policy)
    repeated = previous is not None and previous.unmet == unmet
    _set(policy, board, TownEndMiningCycle(
        unmet=unmet, cycles=previous.cycles + 1 if repeated else 1,
        started_turn=board.turn, stage=STAGE_TOWN,
        visit_epoch=policy._town_visit_epoch))
    policy._open_one_mining_run()
    policy.last_reason = START_REASON
    policy._offer_execution(
        WAIT_KEY, producer="fundraising", work_id="fundraise:town-end-mining",
        next_step="fundraising.prepare-one-mining-run",
        expected_effect="town-end-conditions-retried")
    return WAIT_KEY


def finish_run(policy: Any, snapshot: Any) -> None:
    """The cycle's run is back in town: end its set so the conditions retry."""
    record = cycle(policy)
    if not outstanding(policy):
        return
    policy._end_mining_set()
    _set(policy, snapshot, replace(record, stage=STAGE_RETURNED))


def _on_run_floor(snapshot: Any) -> bool:
    floor = tuple(snapshot.floor_key)
    return not snapshot.in_town and floor[:2] == (DUNGEON_YEEK_CAVE, 1)


def carry(policy: Any, snapshot: Any, first_board: bool) -> None:
    """Observation: restore on the process's first board, then record."""
    if first_board:
        _restore(policy, snapshot)
    record = cycle(policy)
    if record is None or record.stage != STAGE_TOWN or not outstanding(policy):
        return
    if _on_run_floor(snapshot):
        _set(policy, snapshot, replace(record, stage=STAGE_RUN))
    elif snapshot.dungeon_level > 0:
        # The retried conditions held in town and the visit departed by the
        # ordinary departure: the cycle is moot and its set ends.
        policy._end_mining_set()
        _set(policy, snapshot, replace(record, stage=STAGE_DEPARTED))


def _restore(policy: Any, snapshot: Any) -> None:
    path = getattr(policy, "_town_end_mining_path", None)
    if path is None or cycle(policy) is not None:
        return
    try:
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        turn = int(stored["turn"])
        record = TownEndMiningCycle(
            unmet=tuple(str(name) for name in stored["unmet"]),
            cycles=int(stored["cycles"]), started_turn=int(stored["started_turn"]),
            stage=str(stored["stage"]), visit_epoch=stored.get("visit_epoch"))
    except (OSError, ValueError, KeyError, TypeError):
        return
    if snapshot.turn < turn:
        return
    policy._town_end_mining_cycle = record
    if record.stage not in OPEN_STAGES or mining_set_open(policy):
        return
    if record.stage == STAGE_TOWN and snapshot.in_town:
        # The cycle was opened in town and had not left: open it again.
        policy._open_one_mining_run()
    elif record.stage == STAGE_RUN and _on_run_floor(snapshot):
        # The restart came during the run: it continues as the mining run.
        policy._open_one_mining_run()
        policy._fundraising_mode = "mine"
    elif record.stage == STAGE_RUN and snapshot.in_town:
        # The run returned while no process watched: the cycle is done.
        _set(policy, snapshot, replace(record, stage=STAGE_RETURNED))


def _set(policy: Any, board: Any, record: TownEndMiningCycle) -> None:
    policy._town_end_mining_cycle = record
    path = getattr(policy, "_town_end_mining_path", None)
    if path is None:
        return
    stored = {**asdict(record), "unmet": list(record.unmet), "turn": board.turn}
    try:
        Path(path).write_text(json.dumps(stored) + "\n", encoding="utf-8")
    except OSError:
        pass
