import gzip
import hashlib
import json
import os
import unittest
from collections import deque
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from pathlib import Path

from hengbot.model import (
    STORE_HOME,
    GridState,
    PlayerState,
    Position,
    Snapshot,
    parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, _persistent_grid_signature
from hengbot.town_maps import TownMap


ROOT = Path(__file__).resolve().parents[1]
TRANSIENT_DEFAULTS = {
    "has_monster": False,
    "monster_index": 0,
    "object_count": 0,
    "object_tvals": (),
    "lit": False,
    "in_view": False,
    "currently_observed": False,
}


def structural_value(value, active=None):
    """Canonicalize policy state without relying on object identity equality."""
    if active is None:
        active = set()
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if isinstance(value, Path):
        return ("Path", str(value))
    if isinstance(value, Enum):
        return (type(value).__qualname__, value.value)
    identity = id(value)
    if identity in active:
        return ("cycle", type(value).__qualname__)
    active.add(identity)
    try:
        if is_dataclass(value):
            return (
                type(value).__qualname__,
                tuple((field.name, structural_value(getattr(value, field.name), active))
                      for field in fields(value)),
            )
        if isinstance(value, dict):
            items = [
                (structural_value(key, active), structural_value(item, active))
                for key, item in value.items()
            ]
            return (type(value).__qualname__, tuple(sorted(items, key=repr)))
        if isinstance(value, (set, frozenset)):
            return (type(value).__qualname__, tuple(sorted(
                (structural_value(item, active) for item in value), key=repr,
            )))
        if isinstance(value, (list, tuple, deque)):
            return (type(value).__qualname__, tuple(
                structural_value(item, active) for item in value
            ))
        if callable(value):
            return ("callable", getattr(value, "__qualname__", repr(value)))
        if hasattr(value, "__dict__"):
            return (type(value).__qualname__, structural_value(value.__dict__, active))
        return (type(value).__qualname__, repr(value))
    finally:
        active.remove(identity)


def structural_digest(value):
    return hashlib.sha256(repr(structural_value(value)).encode()).hexdigest()


def player(position=Position(2, 2)):
    return PlayerState(position, 20, 20, 0, 0, 1)


def grid(position, **changes):
    base = GridState(
        position=position,
        known=True,
        passable=True,
        wall=False,
        has_monster=False,
        has_down_stairs=False,
        has_up_stairs=False,
        unsafe=False,
    )
    return replace(base, **changes)


def snapshot(grids, *, floor_key=(0, 0, 0), town=True, width=7, height=5, town_id=0):
    return Snapshot(
        player(), grids, [], floor_key=floor_key, town_flag=town,
        width=width, height=height, town_id=town_id,
    )


class TownLatencyCacheTest(unittest.TestCase):
    def test_fixed_quest_offer_scan_is_shared_with_original_decision_snapshot(self):
        class CountingGrids(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.calls = 0

            def values(self):
                self.calls += 1
                return super().values()

        policy = HengbotPolicy()
        offer = Position(2, 4)
        grids = CountingGrids({offer: grid(offer, building_special=34)})
        original = snapshot(grids)
        enriched = replace(original)
        policy._decision_sequence = 17
        policy._decision_input_snapshot = original
        policy._begin_map_predicate_cache(enriched)

        policy._fixed_quest_is_offered(original, 34)
        policy._fixed_quest_is_offered(original, 14)

        self.assertEqual(grids.calls, 1)
    def test_fixed_quest_offer_scan_runs_once_per_merged_decision(self):
        class CountingGrids(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.values_calls = 0

            def values(self):
                self.values_calls += 1
                return super().values()

        offer = Position(2, 4)
        first_grids = CountingGrids({offer: grid(offer, building_special=34)})
        first = snapshot(first_grids)
        policy = HengbotPolicy()

        policy._begin_map_predicate_cache(first)
        self.assertEqual(first_grids.values_calls, 1)
        for _ in range(20):
            self.assertTrue(policy._fixed_quest_is_offered(first, 34))
            self.assertFalse(policy._fixed_quest_is_offered(first, 14))
        self.assertEqual(first_grids.values_calls, 1)

        second_grids = CountingGrids({offer: grid(offer, building_special=14)})
        second = snapshot(second_grids)
        policy._begin_map_predicate_cache(second)
        self.assertEqual(second_grids.values_calls, 1)
        self.assertFalse(policy._fixed_quest_is_offered(second, 34))
        self.assertTrue(policy._fixed_quest_is_offered(second, 14))
        self.assertEqual(second_grids.values_calls, 1)

    def test_fixed_quest_offer_cache_preserves_gridless_fallback(self):
        quest = Position(2, 4)
        town_map = TownMap(
            name="quest-town", width=7, height=5,
            walkable=frozenset({quest}), quest_buildings={34: frozenset({quest})},
        )
        policy = HengbotPolicy(town_maps={0: town_map})
        board = snapshot({})

        policy._begin_map_predicate_cache(board)

        self.assertTrue(policy._fixed_quest_is_offered(board, 34))
        self.assertFalse(policy._fixed_quest_is_offered(board, 14))

    def test_persistent_signature_covers_every_non_transient_grid_field(self):
        pos = Position(2, 3)
        original = grid(pos)
        transient = set(TRANSIENT_DEFAULTS)
        for name in GridState.__dataclass_fields__:
            if name in transient:
                continue
            value = getattr(original, name)
            if isinstance(value, bool):
                changed = not value
            elif isinstance(value, int):
                changed = value + 1
            elif isinstance(value, Position):
                changed = Position(value.y + 1, value.x)
            else:
                self.fail(f"add a signature mutation for GridState.{name}")
            self.assertNotEqual(
                _persistent_grid_signature(original),
                _persistent_grid_signature(replace(original, **{name: changed})),
                name,
            )

    def test_grid_memory_reuses_terrain_and_clears_every_transient_field(self):
        pos = Position(2, 3)
        observed = grid(
            pos, has_monster=True, monster_index=17, object_count=2,
            object_tvals=(70,), lit=True, in_view=True, currently_observed=True,
        )
        policy = HengbotPolicy()
        first = policy._with_grid_memory(snapshot({pos: observed}))
        remembered = policy._remembered_grids[pos]

        self.assertIs(first.grids[pos], observed)
        for name, value in TRANSIENT_DEFAULTS.items():
            self.assertEqual(getattr(remembered, name), value)

        second = policy._with_grid_memory(snapshot({}))
        self.assertIs(second.grids[pos], remembered)
        third = policy._with_grid_memory(snapshot({pos: observed}))
        self.assertIs(policy._remembered_grids[pos], remembered)
        self.assertIs(third.grids[pos], observed)

    def test_grid_memory_discards_cached_terrain_on_region_change(self):
        pos = Position(2, 3)
        policy = HengbotPolicy()
        policy._with_grid_memory(snapshot({pos: grid(pos)}))

        changed = policy._with_grid_memory(
            snapshot({}, floor_key=(2, 1, 0), town=False, town_id=-1)
        )

        self.assertNotIn(pos, changed.grids)
        self.assertFalse(policy._remembered_grids)

    def test_home_fact_survives_unlit_snapshot_then_invalidates_when_emitted(self):
        home = Position(2, 4)
        policy = HengbotPolicy()
        lit = snapshot({home: grid(home, store_number=STORE_HOME)})
        policy._emitted_t = {(home.y, home.x)}
        merged = policy._with_grid_memory(lit)
        policy._begin_map_predicate_cache(merged)
        self.assertTrue(policy._home_available(merged))

        night = snapshot({})
        policy._emitted_t = set()
        merged_night = policy._with_grid_memory(night)
        policy._begin_map_predicate_cache(merged_night)
        self.assertTrue(policy._home_available(merged_night))

        removed = snapshot({home: grid(home, store_number=-1)})
        policy._emitted_t = {(home.y, home.x)}
        merged_removed = policy._with_grid_memory(removed)
        policy._begin_map_predicate_cache(merged_removed)
        self.assertFalse(policy._home_available(merged_removed))

    def test_town_facts_clear_on_floor_change(self):
        home = Position(2, 4)
        policy = HengbotPolicy()
        first = snapshot({home: grid(home, store_number=STORE_HOME)})
        policy._emitted_t = {(home.y, home.x)}
        merged = policy._with_grid_memory(first)
        policy._begin_map_predicate_cache(merged)
        self.assertTrue(policy._home_available(merged))

        dungeon = snapshot({}, floor_key=(2, 1, 0), town=False, town_id=-1)
        policy._emitted_t = set()
        merged_dungeon = policy._with_grid_memory(dungeon)
        policy._begin_map_predicate_cache(merged_dungeon)
        self.assertFalse(policy._home_available(merged_dungeon))

    def test_snapshot_hazard_cache_invalidates_when_trap_appears(self):
        pos = Position(2, 3)
        policy = HengbotPolicy()
        safe = snapshot({pos: grid(pos)})
        policy._begin_map_predicate_cache(safe)
        self.assertFalse(policy._is_avoidable_hazard_grid(safe.grids[pos]))

        trapped = snapshot({pos: grid(pos, trap=True)})
        policy._begin_map_predicate_cache(trapped)
        self.assertTrue(policy._is_avoidable_hazard_grid(trapped.grids[pos]))

    def test_entrance_cache_rebuilds_for_new_town_and_keeps_routing(self):
        start = Position(2, 1)
        old_entrance = Position(2, 3)
        target = Position(2, 5)
        detour = frozenset(
            {start, old_entrance, Position(2, 4), target,
             Position(1, 1), Position(1, 2), Position(1, 3),
             Position(1, 4), Position(1, 5)}
        )
        first_map = TownMap(
            name="first", width=7, height=5, walkable=detour,
            buildings={1: old_entrance},
        )
        policy = HengbotPolicy(town_maps={0: first_map})
        first = replace(snapshot({start: grid(start)}), player=player(start))
        policy._emitted_t = {(start.y, start.x)}
        policy._begin_map_predicate_cache(first)
        policy._build_grid_index(first)

        self.assertIn(old_entrance, policy._town_entrance_cells(first))
        self.assertEqual(policy._town_map_goal_step(first, target), Position(1, 2))

        new_entrance = Position(1, 2)
        second_map = TownMap(
            name="second", width=7, height=5, walkable=detour,
            buildings={1: new_entrance},
        )
        policy._town_maps[1] = second_map
        second = replace(first, town_id=1)
        policy._emitted_t = {(start.y, start.x)}
        policy._begin_map_predicate_cache(second)
        policy._build_grid_index(second)

        entrances = policy._town_entrance_cells(second)
        self.assertIn(new_entrance, entrances)
        self.assertNotIn(old_entrance, entrances)


class LegacyPolicy(HengbotPolicy):
    """Pre-optimization implementation used as the replay oracle."""

    def _with_grid_memory(self, snapshot):
        region = (
            *snapshot.floor_key, snapshot.width, snapshot.height,
            snapshot.town_id, snapshot.in_town,
        )
        if self._remembered_grid_region != region:
            self._remembered_grid_region = region
            self._remembered_grids = {}
        remembered = {
            position: replace(grid, **TRANSIENT_DEFAULTS)
            for position, grid in self._remembered_grids.items()
        }
        remembered.update(snapshot.grids)
        self._remembered_grids = remembered
        return replace(snapshot, grids=dict(remembered))

    def _home_available(self, snapshot):
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        return any(grid.store_number == STORE_HOME for grid in snapshot.grids.values())

    def _town_entrance_cells(self, snapshot):
        if not snapshot.in_town:
            return set()
        entrances = {
            pos for pos, cell in snapshot.grids.items()
            if cell.store_number is not None or cell.building_special >= 0
        }
        if self._town_map_active(snapshot):
            entrances.update(self._town_map.stores.values())
            entrances.update(self._town_map.buildings.values())
            for positions in self._town_map.quest_buildings.values():
                entrances.update(positions)
            for positions in self._town_map.quest_entrances.values():
                entrances.update(positions)
        return entrances


@unittest.skipUnless(
    os.environ.get("HENGBOT_CAPTURE_REPLAY") == "1",
    "set HENGBOT_CAPTURE_REPLAY=1 for the slow incident replay",
)
class CapturedSequenceEquivalenceTest(unittest.TestCase):
    CAPTURES = (
        "20260731-063654-loop-detected",  # 51 town decisions
        "20260801-122227-loop-detected",  # 631 dungeon + 102 town decisions
    )

    def test_legacy_and_cached_policies_match_every_decision(self):
        monraces = load_monrace_knowledge(
            Path(r"C:\hengband\.worktrees\bot-json-output\lib\edit\MonraceDefinitions.jsonc")
        )
        for capture in self.CAPTURES:
            path = ROOT / "incident-captures" / capture / "snapshots" / "snapshots-current.jsonl.gz"
            legacy = LegacyPolicy()
            cached = HengbotPolicy()
            primed = False
            decisions = 0
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    row = json.loads(line)
                    if row.get("type") != "player_turn":
                        continue
                    snap = parse_snapshot(row, monraces)
                    if not primed:
                        legacy.prime(snap)
                        cached.prime(snap)
                        primed = True
                    legacy_key = legacy.choose_key(snap)
                    cached_key = cached.choose_key(snap)
                    self.assertEqual(
                        (cached_key, cached.last_reason),
                        (legacy_key, legacy.last_reason),
                        f"{capture}:{line_number}",
                    )
                    decisions += 1
            self.assertGreater(decisions, 0)

            excluded = {
                "_remembered_grids", "_remembered_grid_signatures",
                "_remembered_grid_sources", "_town_fact_region", "_town_store_positions",
                "_town_emitted_entrances", "_town_entrance_cache", "_town_fact_snapshot",
                "_map_predicate_snapshot", "_hazard_cache", "_town_border_cache",
                "_threat_prediction_memo", "_aggregate_ranged_cache",
            }
            state_keys = set(legacy.__dict__) | set(cached.__dict__)
            for key in state_keys - excluded:
                self.assertEqual(
                    structural_digest(cached.__dict__[key]),
                    structural_digest(legacy.__dict__[key]),
                    f"{capture} persistent state {key}",
                )
