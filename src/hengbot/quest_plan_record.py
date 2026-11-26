"""The floor plans' state, carried across a bot restart (owner 2026-11-23, review K1 (b)-4).

Whole-bot maintainability review 2026-11-23, K1 「再起動で作戦の状態が消える」: a restarted process
builds a fresh policy, so every plan's floor state held in the process was gone -- the room sweep's
stage and round, the FIND_EXIT choke wait, the summon answer, the lure, the wait cells (all of the
QuestFloorNavigator), the 99F/100F battle (angband_finale_battle: a fresh battle reads a quest killed
on this floor as done on arrival, so the success recall is never read), Q2's phase walk, the
generic quest strategy's holds and sweeps, the kill quest's target search.  Only the Q25 phase
battle (quest25_battle_record) and the room sweep's kills (quest_sweep_record) had records.

Owner 2026-11-23 (verbatim): 「再起動でクエストの作戦の状態を「保存して続きから始める」（保存した階と今の
階が違えば捨てる）」.

``CARRIED`` names every plan state a restart keeps; ``NOT_CARRIED`` every other plan state, with the
reason (scripts/quest_plan_record_lint.py: a plan module's registry row, or a quest floor row of
any module, is in exactly one of them, so a new plan state cannot be left out unnoticed).  The
navigators carried are the ones bound to the floor (``floor_key``), without the fields another
record carries with its own rule for a game reloaded from an older save (``NAVIGATOR_NOT_CARRIED``).

The record beside the decision log (``quest-plan.pkl``) is the pickled state every decision left,
written at the ``choose_key`` exit when it changed (with the turn of the first board that left it);
in town it holds nothing.  The first ``_observe`` of a process
restores it right after the floor change it reads (the first board is one: the floor change clears
the floor's memories, floor_visit_memory and the Q2 rows, which the restore then sets), and only

- on the same floor (``floor_key``: dungeon, level, quest) as the record's: another floor discards
  it (the owner's 「保存した階と今の階が違えば捨てる」);
- at the same or a later game turn: a game reloaded from an older save of the floor is not the
  floor the record saw (the kill records keep their kills read before the save; quest25_battle_record,
  quest_sweep_record), so the plan state is discarded too.

Every decision the previous process made off this floor rewrote the record (in town without state),
so a later visit to the same quest floor starts clean.  Nothing is invented: what is restored is
what the previous process held, by value; a record that does not load is discarded.
"""
from __future__ import annotations

import copy
import hashlib
import pickle
from pathlib import Path

VERSION = 1
FILE_NAME = "quest-plan.pkl"
NAVIGATORS = "_quest_navigators"

# The plan states a restart keeps on the same floor (policy attributes, state_registry rows).
CARRIED = (
    # The fixed-quest floor plans' state (quest_plan_base: 「the floor's state is the
    # QuestFloorNavigator's」): quest_find_exit, quest_room_sweep, quest_summon_answer,
    # quest_lure_approach, quest_wait_placement, quest_mixed_assault, quest_detect_remaining.
    NAVIGATORS,
    # The 99F/100F battle (phase, the stand, done_on_arrival).
    "_angband_finale_battle",
    # The kill quest's target search (its coverage, laps, the pending detection).
    "_quest_target_search",
    # Q2's kill lines (with the board read, so the same board is not counted twice).
    "_q2_kill_credit",
    # Q2's phase walk (policy_quest).
    "_q2_blue_recovery_perceived", "_q2_blue_recovery_complete", "_q2_breach_attempts",
    "_q2_breach_complete", "_q2_breeder_last_seen", "_q2_breeder_last_seen_floor",
    "_q2_cleared_races", "_q2_final_patrol_target", "_q2_final_patrol_visited",
    "_q2_phase_blocked_steps", "_q2_phase_last_move", "_q2_phase_light_attempted",
    "_q2_phase_route_targets", "_q2_phase_step_failures", "_q2_phase_visited_goals",
    "_q2_residual_surveyed_races", "_q2_speed_attempted", "_q2_surveyed_placements",
    # The generic quest strategy's floor (policy_quest, cleared by the floor change).
    "_quest_strategy_visible_targets", "_quest_strategy_cleared_targets",
    "_quest_strategy_pending_recovery", "_quest_strategy_initial_hold_turns",
    "_quest_strategy_surveyed_placements", "_quest_strategy_sweep_rounds",
    "_quest_strategy_opening_phase", "_quest_strategy_hold_positions",
    "_quest_strategy_post_wave_light_attempted",
    # The generic quest strategy's never-moving targets seen and defeated, and the targets' names, by
    # quest (policy_quest: a defeat is read from a target gone since the previous board).
    "_quest_strategy_visible_never_move", "_quest_strategy_defeated_never_move",
    "_quest_strategy_visible_target_names",
    # The quest floor's own judgements and reads.
    "_quest_sweep_engage_commit", "_quest_hold_threats", "_fixed_quest_speed_floor", "_quest_light_areas_read",
    "_quest_light_attempted", "_unviable_quest_floor", "_quest_regen_exhausted_floor",
)

# The plan states a restart does not keep, with the reason.
NOT_CARRIED = {
    "_q2_reconnect_recovery_floor": "set by the first board of every process itself (a reconnection)",
    "_quest_strategy_recovery_claims": "claims of the process that made them (the town hold's register)",
    "_quest_strategy_recovery_pickup_prepared": "a pickup prepared for the process's own posted key",
    "_quest_strategy_recovery_pickup_prepared_key": "a pickup prepared for the process's own posted key",
    "_quest_strategy_recovery_pickup_posted": "the process's own posted key",
    "_quest_strategy_throw_exp": "the experience expected after the process's own posted throw",
    "_q2_tower_recharge": "a town trip, not a floor's plan",
    "_q34_recharge_attempted": "the Magic-Eater's recharge, not a floor's plan",
    "_q34_recharge_pending": "the Magic-Eater's recharge, not a floor's plan",
    "_q34_opening_released": "the town's Q34-first opening, not a floor's plan (rebuilt: the "
                             "next opening decision releases again)",
    "_quest_supply_admitted": "the town visit's quest admissions, not a floor's plan",
    "_q25_battle_record": "quest25_battle_record's own write cache",
    "_q25_battle_record_read": "quest25_battle_record's own once-per-process mark",
    "_q25_battle_restored": "quest25_battle_record's own pending restore",
    "_sweep_kill_record": "quest_sweep_record's own write cache",
    "_sweep_kill_record_read": "quest_sweep_record's own once-per-process mark",
    "_sweep_kills_restored": "quest_sweep_record's own pending restore",
    "_quest_plan_record": "this record's own write cache",
    "_quest_plan_record_read": "this record's own once-per-process mark",
}

# The navigator fields left out: another record carries them, with its own rule for a game reloaded
# from an older save and for the board the previous process last read (the field's empty value here).
NAVIGATOR_NOT_CARRIED = {
    "phase_battle": ("quest25_battle_record", None),
    "split_kills": ("quest_sweep_record", {}),
    "split_kill_turns": ("quest_sweep_record", ()),
    "split_board": ("quest_sweep_record", None),
}

_MISSING = object()


def _carried_navigator(navigator):
    kept = copy.copy(navigator)
    for name, (_owner, empty) in NAVIGATOR_NOT_CARRIED.items():
        if name in kept.__dict__:
            setattr(kept, name, copy.copy(empty))
    return kept


def entry(policy, snapshot) -> dict | None:
    """The plan state this board leaves on its floor, or None in town."""
    if getattr(snapshot, "in_town", False):
        return None
    floor = tuple(snapshot.floor_key)
    states = {}
    for name in CARRIED:
        if name == NAVIGATORS:
            continue
        value = policy.__dict__.get(name, _MISSING)
        if value is not _MISSING:
            states[name] = value
    navigators = {
        quest_id: _carried_navigator(navigator)
        for quest_id, navigator in (policy.__dict__.get(NAVIGATORS) or {}).items()
        if getattr(navigator, "floor_key", None) == floor}
    return {"version": VERSION, "floor": floor, "turn": int(snapshot.turn), "states": states,
            "navigators": navigators}


def record(policy, snapshot) -> None:
    """The ``choose_key`` exit: write the plan state this decision left (nothing in town)."""
    path = getattr(policy, "_quest_plan_record_path", None)
    if path is None:
        return
    left = entry(policy, snapshot)
    # The turn is the first board that left this state: the state was the same on every later
    # board, so a game saved on any of them holds it (``restorable``).  It is not compared.
    try:
        state = None if left is None else {name: value for name, value in left.items() if name != "turn"}
        digest = hashlib.sha256(pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()
        payload = pickle.dumps(left, protocol=pickle.HIGHEST_PROTOCOL)
    except (pickle.PicklingError, TypeError, AttributeError):
        left, digest, payload = None, None, pickle.dumps(None)
    if getattr(policy, "_quest_plan_record", None) == digest and digest is not None:
        return
    try:
        temporary = Path(path).with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
    except OSError:
        return
    policy._quest_plan_record = digest


def load(path) -> dict | None:
    """The record at ``path``, or None when there is none or it does not load."""
    try:
        held = pickle.loads(Path(path).read_bytes())
    except Exception:  # noqa: BLE001 -- an unreadable record restores nothing (a restart as before)
        return None
    if not isinstance(held, dict) or held.get("version") != VERSION:
        return None
    return held


def restorable(held: dict | None, snapshot) -> bool:
    """The record is of this floor and not of a later game turn than this board's."""
    return (held is not None and not getattr(snapshot, "in_town", False)
            and tuple(held["floor"]) == tuple(snapshot.floor_key)
            and int(snapshot.turn) >= int(held["turn"]))


def restore(policy, snapshot) -> bool:
    """The first ``_observe`` of a process, after its floor change: restore the record once.

    True when the plan state was restored."""
    path = getattr(policy, "_quest_plan_record_path", None)
    if path is None or getattr(policy, "_quest_plan_record_read", False):
        return False
    policy._quest_plan_record_read = True
    held = load(path)
    if not restorable(held, snapshot):
        return False
    for name, value in held["states"].items():
        if name in CARRIED:
            setattr(policy, name, value)
    navigators = policy.__dict__.setdefault(NAVIGATORS, {})
    for quest_id, navigator in held["navigators"].items():
        navigators[quest_id] = navigator
    # The target search's first board was observed before the floor change on the fresh memory
    # (policy.choose_key); the restored memory reads it now, once.
    if "_quest_target_search" in held["states"]:
        from hengbot import quest_target_search
        quest_target_search.observe(policy, snapshot)
    return True
