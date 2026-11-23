"""Every 50F+ admission gate asked over one table (deep_admission, review 2026-11-23 K2).

The cells: dungeon (Angband, the Castle, the Mountain) x depth 44-52 x the *Destruction* means
held or not x the Castle climb held on that dungeon or not.  No climb can be held on Angband
(dive_floor.DIVE_FLOOR_DUNGEONS), so Angband's climbing cells are absent.

Each gate is asked through its own entry point on the recorded n1-a life-535 policy (its town
departure board, row 122, and a Castle 48F board of the capture) with only the leaf facts named:

DECLARED CONSTRUCTED:
* the means: destruction_means.Means.depth_gate (holds_means) and .carried answer the cell's
  means; the optimizer's ``destruction_means`` answers it for the loadout;
* the kit: ability_sources.missing_abilities answers no gap (every resistance and telepathy
  worn), so the *Destruction* label is the only 50F+ gap;
* the climb: dive_floor's switch state (``_alternate_dungeon``, its reason, ``STATE``) set on the
  cell's dungeon when climbing, cleared otherwise;
* the recall: the target dungeon is the cell's, its entry depth the cell's depth; the guardian
  landing block answers no (another gate);
* the floor: the board's ``floor_key`` and ``dungeon_level`` the cell's (a quest floor's third
  part 1); the tiers act and the floor is one *Destruction* touches (means_spent's scene);
* the departure loop: its streak at ``STREAK_STOP``;
* the loadout: no flags, every depth-table ability intrinsic, the base speed.

``answers`` returns {gate: {cell: answer}}, an answer True where the gate admits the character
on that floor by that route (for ``me_inn_refill.dive_reaches_deep``: the refill applies).
"""
from __future__ import annotations

import contextlib
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from hengbot import (
    deep_climb, deep_fall_guard, destruction_means, destruction_use, dive_floor,
    equipment_optimizer, means_spent_loop, me_inn_refill, policy_constants,
)
from hengbot.policy_constants import DEPTH_ABILITY_REQUIREMENTS, DESTRUCTION_GATE_LABEL

ANGBAND, CASTLE, MOUNTAIN = 1, 12, 14
DUNGEONS = {ANGBAND: "angband", CASTLE: "castle", MOUNTAIN: "mountain"}
DEPTHS = tuple(range(44, 53))

# gate -> route (deep_admission.ROUTES).  The depth of a cell is the floor the route lands on,
# except the "fall" gates: the floor stood on, from which a trap door or a Teleport Level falls.
GATES = {
    "policy_constants.destruction_dive_permitted": "intent",
    "policy_constants.permitted_dive_depth": "intent",
    "policy_observation._missing_required_abilities": "intent",
    "policy_supply._intended_dive_depth": "intent",
    "destruction_means.departure_carried": "recall",
    "deep_climb.departure_gaps": "recall",
    "policy._destination_depth_allowed": "recall",
    "policy._recall_destination_safe": "recall",
    "policy_helpers._fallback_landing_allowed": "fallback-landing",
    "policy._deep_stair_refused": "stairs",
    "deep_fall_guard.descent_refused": "stairs",
    "deep_fall_guard.sanctioned": "trapdoor",
    "deep_climb.observe": "trapdoor",
    "deep_fall_guard.at_risk": "fall",
    "deep_fall_guard.teleport_level_refused": "fall",
    "deep_climb._standing_without_means": "stand",
    "destruction_use.means_spent": "stand",
    "deep_climb._standing_without_means@quest": "quest",
    "destruction_use.means_spent@quest": "quest",
    "deep_climb.observe@quest": "quest",
    "me_inn_refill.dive_reaches_deep": "deep-descent",
    "means_spent_loop.looping": "departure-loop",
    "equipment_optimizer.divable_depth": "loadout",
    "equipment_optimizer._meets_static_requirements": "loadout",
}

_CLIMB_STATE = ("_alternate_dungeon", "_alternate_dungeon_reason", dive_floor.STATE,
                "_target_dungeon_id", "_target_dungeon_reason", "_conquest_committed",
                deep_climb.MEMORY, means_spent_loop.MEMORY)
_MISSING = object()


FIXTURE_535 = "n1a-535-deep-arrival-1123"
TOWN_ROW = 122       # the 535 visit's departure board (town:recall-to-alt-dungeon)


def load_recorded(fixtures, scratch):
    """(policy, town board, a Castle 48F board) of n1-a life-535's checkpoint, not replayed."""
    import io
    import lzma
    from pathlib import Path

    from hengbot.model import parse_snapshot
    from support.town_arrival_fixture import load

    fixture = Path(fixtures) / FIXTURE_535
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        policy, _journal, steps = load(fixture, Path(scratch))
        town = steps[TOWN_ROW][1]()
    for line in lzma.decompress((fixture / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines():
        raw = json.loads(line)
        if raw.get("type") == "player_turn":
            return policy, town, parse_snapshot(raw, policy._monrace_knowledge)
    raise AssertionError("no board in the capture")


def cells():
    for dungeon in DUNGEONS:
        for depth in DEPTHS:
            for means in (False, True):
                for climbing in ((False,) if dungeon == ANGBAND else (False, True)):
                    yield dungeon, depth, means, climbing


def cell_name(cell) -> str:
    dungeon, depth, means, climbing = cell
    return (f"{DUNGEONS[dungeon]}:{depth}:{'means' if means else 'no-means'}:"
            f"{'climbing' if climbing else 'no-climb'}")


def parse_cell(name: str):
    dungeon, depth, means, climbing = name.split(":")
    return ({v: k for k, v in DUNGEONS.items()}[dungeon], int(depth), means == "means",
            climbing == "climbing")


@contextlib.contextmanager
def _cell(policy, cell):
    dungeon, depth, means, climbing = cell
    saved = {name: getattr(policy, name, _MISSING) for name in _CLIMB_STATE}
    if climbing:
        policy._alternate_dungeon = dungeon
        policy._alternate_dungeon_reason = dive_floor.SAFE_FALLBACK_REASON
        setattr(policy, dive_floor.STATE, (dungeon, 38))
    else:
        policy._alternate_dungeon = None
        policy._alternate_dungeon_reason = None
        setattr(policy, dive_floor.STATE, None)
    policy._target_dungeon_id = dungeon
    answer = lambda *_args, **_kwargs: means
    try:
        with mock.patch.object(destruction_means.Means, "depth_gate", answer), \
                mock.patch.object(destruction_means.Means, "carried", answer), \
                mock.patch("hengbot.ability_sources.missing_abilities",
                           lambda *_args, **_kwargs: set()), \
                mock.patch("hengbot.equipment_optimizer.destruction_means", answer), \
                mock.patch("hengbot.threat_tiers.acts_here", lambda *_args: True), \
                mock.patch("hengbot.destruction_use._floor_destroyed", lambda *_args: True), \
                mock.patch.object(policy, "_dungeon_entry_depth",
                                  lambda *_args, **_kwargs: depth), \
                mock.patch.object(policy, "_recall_landing_guardian_blocked",
                                  lambda *_args, **_kwargs: False):
            yield
    finally:
        for name, value in saved.items():
            if value is _MISSING:
                if hasattr(policy, name):
                    delattr(policy, name)
            else:
                setattr(policy, name, value)


def _board(board, dungeon, depth, quest=0):
    return replace(board, floor_key=(dungeon, depth, quest))


def _observe_acts(policy, board, dungeon, depth, quest=0) -> bool:
    """deep_climb.observe of an arrival on ``depth`` from the floor above: whether it holds the
    climb or stops (the standing branch asked apart)."""
    calls = []
    setattr(policy, deep_climb.MEMORY, ((dungeon, depth - 1, quest), None))
    with mock.patch.object(deep_climb, "_standing_without_means", lambda *_args: False), \
            mock.patch.object(deep_climb, "_hold_climb",
                              lambda *_args: calls.append(True) or True):
        deep_climb.observe(policy, _board(board, dungeon, depth, quest))
    return bool(calls)


def _loadout():
    return SimpleNamespace(flags=frozenset(), item_at=lambda _slot: None)


def _abilities():
    return frozenset().union(*(adds for _floor, adds in DEPTH_ABILITY_REQUIREMENTS))


def ask(policy, town, board, gate, cell):
    dungeon, depth, means, _climbing = cell
    holds = lambda: means
    here = _board(board, dungeon, depth)
    quest = _board(board, dungeon, depth, 1)
    if gate == "policy_constants.destruction_dive_permitted":
        return policy_constants.destruction_dive_permitted(depth, holds)
    if gate == "policy_constants.permitted_dive_depth":
        return policy_constants.permitted_dive_depth(depth, holds) == depth
    if gate == "policy_observation._missing_required_abilities":
        return DESTRUCTION_GATE_LABEL not in policy._missing_required_abilities(here, depth)
    if gate == "policy_supply._intended_dive_depth":
        return policy._intended_dive_depth(town) == depth
    if gate == "destruction_means.departure_carried":
        return destruction_means.departure_carried(policy, town, depth)
    if gate == "deep_climb.departure_gaps":
        return DESTRUCTION_GATE_LABEL not in deep_climb.departure_gaps(policy, town, depth)
    if gate == "policy._destination_depth_allowed":
        return policy._destination_depth_allowed(town, depth)
    if gate == "policy._recall_destination_safe":
        return policy._recall_destination_safe(town, dungeon)
    if gate == "policy_helpers._fallback_landing_allowed":
        return policy._fallback_landing_allowed(town, dungeon, depth, depth_floor=False,
                                                climb_landing=_climbing)
    if gate == "policy._deep_stair_refused":
        return not policy._deep_stair_refused(_board(board, dungeon, depth - 1), depth)
    if gate == "deep_fall_guard.descent_refused":
        return not deep_fall_guard.descent_refused(policy, _board(board, dungeon, depth - 1),
                                                   depth)
    if gate == "deep_fall_guard.sanctioned":
        return deep_fall_guard.sanctioned(policy, dungeon, depth)
    if gate == "deep_climb.observe":
        return not _observe_acts(policy, board, dungeon, depth)
    if gate == "deep_fall_guard.at_risk":
        return not deep_fall_guard.at_risk(policy, here)
    if gate == "deep_fall_guard.teleport_level_refused":
        return not deep_fall_guard.teleport_level_refused(policy, here)
    if gate == "deep_climb._standing_without_means":
        return not deep_climb._standing_without_means(policy, here, here.floor_key)
    if gate == "destruction_use.means_spent":
        return not destruction_use.means_spent(policy, here)
    if gate == "deep_climb._standing_without_means@quest":
        return not deep_climb._standing_without_means(policy, quest, quest.floor_key)
    if gate == "destruction_use.means_spent@quest":
        return not destruction_use.means_spent(policy, quest)
    if gate == "deep_climb.observe@quest":
        return not _observe_acts(policy, board, dungeon, depth, 1)
    if gate == "me_inn_refill.dive_reaches_deep":
        with mock.patch.object(policy, "_intended_dive_depth", lambda *_args: depth):
            return me_inn_refill.dive_reaches_deep(policy, town)
    if gate == "means_spent_loop.looping":
        setattr(policy, means_spent_loop.MEMORY,
                means_spent_loop.Loop(streak=means_spent_loop.STREAK_STOP))
        return not means_spent_loop.looping(policy, depth)
    if gate == "equipment_optimizer.divable_depth":
        return equipment_optimizer.divable_depth(
            _loadout(), intrinsic_abilities=_abilities(), has_destruction=means) >= depth
    if gate == "equipment_optimizer._meets_static_requirements":
        return equipment_optimizer._meets_static_requirements(
            _loadout(), depth=depth, intrinsic_abilities=_abilities(), has_destruction=means,
            require_light=False)
    raise KeyError(gate)


def answers(policy, town, board) -> dict:
    table = {gate: {} for gate in GATES}
    for cell in cells():
        for gate in GATES:
            with _cell(policy, cell):
                table[gate][cell_name(cell)] = bool(ask(policy, town, board, gate, cell))
    return table


def dumps(table) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# The gates whose depth is the floor the route lands on (the "fall" gates read the floor stood
# on; the inn's refill reads whether a dive reaches 50F+, not an admission).
LANDING_ROUTES = ("intent", "recall", "fallback-landing", "stairs", "trapdoor", "stand",
                  "quest", "departure-loop", "loadout")


def disagreements(table) -> dict:
    """{cell: {route-and-answer groups}} where the landing gates answer differently."""
    found = {}
    for cell in cells():
        name = cell_name(cell)
        by_answer = {}
        for gate, route in GATES.items():
            if route in LANDING_ROUTES:
                by_answer.setdefault(table[gate][name], []).append(gate)
        if len(by_answer) > 1:
            found[name] = {"admit": sorted(by_answer[True]), "refuse": sorted(by_answer[False])}
    return found
