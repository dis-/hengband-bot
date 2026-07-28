import tempfile
import unittest
from collections import deque
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.exploration_ledger import (
    EXPLORATION_SAVE_CADENCE,
    ExplorationLedger,
)
from hengbot.model import Position, Snapshot, SV_DIGGING_SHOVEL, TVAL_DIGGING
from hengbot.policy import (
    EXTENDED_STUCK_WINDOW,
    FRUITLESS_DISENGAGE_LIMIT,
    HengbotPolicy,
    WAIT_KEY,
)
from tests.test_policy import grid, item, player


FLOOR = (2, 1, 0)


def floor_snapshot(
    position,
    cells,
    *,
    floor_key=FLOOR,
    turn=1,
    equipment=(),
):
    return Snapshot(
        player(position.y, position.x),
        {cell.position: cell for cell in cells},
        [],
        turn=turn,
        floor_key=floor_key,
        width=30,
        height=20,
        equipment=list(equipment),
    )


def observed_floor(*positions, terrain_offset=0):
    return [
        grid(
            position.y,
            position.x,
            terrain_id=terrain_offset + index + 1,
            marked=True,
        )
        for index, position in enumerate(positions)
    ]


class ExplorationLedgerTest(unittest.TestCase):
    def test_non_object_json_is_discarded(self):
        snapshot = floor_snapshot(
            Position(10, 5), observed_floor(Position(10, 5))
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            for literal in ("null", "42", '"x"', "[1,2,3]"):
                with self.subTest(literal=literal):
                    path.write_text(literal, encoding="utf-8")
                    ledger = ExplorationLedger(path)
                    self.assertFalse(ledger.bind(snapshot))
                    self.assertEqual(ledger.floor_key, snapshot.floor_key)

    def test_cadence_save_refreshes_sample_to_latest_window(self):
        entry_positions = [Position(10, x) for x in range(5, 10)]
        latest_positions = [Position(10, x) for x in range(100, 105)]
        entry = floor_snapshot(
            entry_positions[0],
            observed_floor(*entry_positions),
        )
        latest = floor_snapshot(
            latest_positions[0],
            observed_floor(*latest_positions, terrain_offset=100),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            ledger = ExplorationLedger(path)
            self.assertFalse(ledger.bind(entry))
            ledger.visit_counts[entry_positions[0]] = 3
            for _ in range(EXPLORATION_SAVE_CADENCE):
                ledger.note_decision(latest)

            resumed = ExplorationLedger(path)
            self.assertTrue(resumed.bind(latest))
            self.assertEqual(resumed.visit_counts[entry_positions[0]], 3)

    def test_matching_instance_loads_and_mismatch_or_floor_change_discards(self):
        positions = [Position(10, x) for x in range(5, 10)]
        matching = floor_snapshot(positions[0], observed_floor(*positions))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            ledger = ExplorationLedger(path)
            self.assertFalse(ledger.bind(matching))
            ledger.visit_counts[positions[1]] = 7
            ledger.save(force=True)

            accepted = ExplorationLedger(path)
            self.assertTrue(accepted.bind(matching))
            self.assertEqual(accepted.visit_counts[positions[1]], 7)

            changed = floor_snapshot(
                positions[0], observed_floor(*positions, terrain_offset=100)
            )
            rejected = ExplorationLedger(path)
            self.assertFalse(rejected.bind(changed))
            self.assertFalse(rejected.visit_counts)

            other_floor = replace(matching, floor_key=(2, 2, 0))
            changed_key = ExplorationLedger(path)
            self.assertFalse(changed_key.bind(other_floor))
            self.assertEqual(changed_key.floor_key, other_floor.floor_key)

    def test_restart_continues_visits_and_avoids_exhausted_frontier(self):
        positions = [Position(10, x) for x in range(5, 10)]
        snapshot = floor_snapshot(positions[2], observed_floor(*positions))
        exhausted = positions[1]
        fresh = positions[3]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            first = HengbotPolicy(exploration_ledger_path=path)
            first.prime(snapshot)
            first._visit_counts[exhausted] = 20
            first._probed_frontiers.add(exhausted)
            first._exploration_ledger.save(force=True)

            resumed = HengbotPolicy(exploration_ledger_path=path)
            resumed.prime(snapshot)
            resumed._build_grid_index(snapshot)
            self.assertEqual(resumed._visit_counts[exhausted], 20)
            self.assertIn(exhausted, resumed._probed_frontiers)
            self.assertEqual(resumed._least_visited_neighbor(snapshot), fresh)
            self.assertNotEqual(resumed._explore_step(snapshot), exhausted)


class GlobalFrontierTest(unittest.TestCase):
    def test_oscillation_selects_far_large_frontier_and_digs_route(self):
        start = Position(10, 5)
        wall = Position(10, 6)
        far = Position(10, 9)
        near = Position(9, 5)
        cells = observed_floor(start, near, Position(10, 7), Position(10, 8), far)
        cells.append(
            grid(
                wall.y,
                wall.x,
                passable=False,
                can_dig=True,
                tunnel=True,
                terrain_id=90,
                marked=True,
            )
        )
        # Surround the near pocket so it exposes only one unknown; the far end
        # retains the broad unknown edge and wins the global score.
        cells.extend(
            grid(y, x, passable=False, terrain_id=100 + y + x)
            for y, x in ((8, 4), (8, 5), (8, 6), (9, 4), (9, 6))
        )
        digger = item(
            "main_hand",
            TVAL_DIGGING,
            SV_DIGGING_SHOVEL,
            is_equipment=True,
        )
        snapshot = floor_snapshot(start, cells, equipment=(digger,))
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._build_grid_index(snapshot)
        policy._visit_counts[near] = 10
        policy._recent = deque(
            [start, near] * (EXTENDED_STUCK_WINDOW // 2),
            maxlen=EXTENDED_STUCK_WINDOW,
        )

        step = policy._explore_step(snapshot)

        self.assertEqual(step, wall)
        policy.last_reason = "explore"
        self.assertTrue(policy._step_toward(snapshot, step).startswith("T"))
        self.assertEqual(policy._explore_path[-1], far)


class ProgressBudgetTest(unittest.TestCase):
    def test_persistent_growth_preserves_budget(self):
        position = Position(10, 5)
        base_cells = observed_floor(position)
        base = floor_snapshot(position, base_cells)
        policy = HengbotPolicy()
        policy.prime(base)
        # Model a floor larger than the moving emitter window: the persistent
        # accumulator already contains corridors no longer in snapshot.grids.
        policy._remembered_known_t.update((10, x) for x in range(5, 15))
        policy._fruitless_disengage_floor = FLOOR
        policy._fruitless_disengage_decisions = FRUITLESS_DISENGAGE_LIMIT
        policy._fruitless_disengage_marked_high = len(
            policy._remembered_known_t
        )
        policy.last_reason = "combat:disengage-explore"
        policy._remembered_known_t.add((10, 15))
        with (
            patch.object(policy, "_fruitless_fight_is_winnable", return_value=False),
            patch.object(policy, "_return_to_town_key", return_value="6"),
        ):
            self.assertEqual(policy._fruitless_disengage_key(base, []), "6")
            self.assertEqual(
                policy._fruitless_disengage_decisions,
                FRUITLESS_DISENGAGE_LIMIT,
            )

    def test_window_growth_without_persistent_growth_consumes_budget(self):
        position = Position(10, 5)
        base_cells = observed_floor(position)
        base = floor_snapshot(position, base_cells)
        policy = HengbotPolicy()
        policy.prime(base)
        policy._remembered_known_t.update((10, x) for x in range(5, 15))
        policy._fruitless_disengage_floor = FLOOR
        policy._fruitless_disengage_decisions = FRUITLESS_DISENGAGE_LIMIT
        policy._fruitless_disengage_marked_high = len(
            policy._remembered_known_t
        )
        policy.last_reason = "combat:disengage-explore"
        larger_window = floor_snapshot(
            position,
            base_cells + observed_floor(Position(10, 6), terrain_offset=10),
            turn=2,
        )
        with patch.object(
            policy, "_fruitless_fight_is_winnable", return_value=False
        ):
            self.assertEqual(
                policy._fruitless_disengage_key(larger_window, []), WAIT_KEY
            )
            self.assertEqual(policy.last_reason, "combat:fruitless")

    def test_zero_growth_stops_at_same_limit_after_productive_step(self):
        position = Position(10, 5)
        base = floor_snapshot(position, observed_floor(position))
        policy = HengbotPolicy()
        policy.prime(base)
        policy._fruitless_disengage_floor = FLOOR
        policy._fruitless_disengage_decisions = FRUITLESS_DISENGAGE_LIMIT
        policy._fruitless_disengage_marked_high = len(
            policy._remembered_known_t
        )
        policy._remembered_known_t.add((10, 6))
        policy.last_reason = "combat:disengage-explore"
        with (
            patch.object(policy, "_fruitless_fight_is_winnable", return_value=False),
            patch.object(policy, "_return_to_town_key", return_value="6"),
        ):
            self.assertEqual(policy._fruitless_disengage_key(base, []), "6")
            policy.last_reason = "combat:disengage-explore"
            self.assertEqual(policy._fruitless_disengage_key(base, []), WAIT_KEY)
            self.assertEqual(policy.last_reason, "combat:fruitless")


if __name__ == "__main__":
    unittest.main()
