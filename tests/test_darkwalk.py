from __future__ import annotations

import base64
import gzip
import json
import pickle
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.cli import POLICY_FINAL_STOP_REASONS, _policy_final_stop_banner
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import (
    InventoryItem,
    Position,
    SV_FLASK_OIL,
    TVAL_FLASK,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy, PROBE_LIMIT, READ_KEY, WAIT_KEY
from hengbot.policy_types import OWNER_EXPECTATION_MAX_TURNS


FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot_fixture():
    path = FIXTURES / "incident-darkread-guard-miss-turn-1029477.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return parse_snapshot(json.loads(next(stream)), {})


DIRECTIONS = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


class DarkwalkIncidentTest(unittest.TestCase):
    def test_dark_route_yields_on_remembered_upstairs_for_return_handoff(self):
        snapshot = _snapshot_fixture()
        origin = Position(10, 10)
        template = next(iter(snapshot.grids.values()))
        upstairs = replace(
            snapshot,
            player=replace(snapshot.player, position=origin),
            grids={
                origin: replace(
                    template, position=origin, passable=True, wall=False,
                    lit=False, known=True, has_up_stairs=True,
                )
            },
        )
        policy = HengbotPolicy()
        policy._floor_key = upstairs.floor_key
        policy._remembered_upstairs.add(origin)
        policy._returning_to_town = True

        self.assertEqual(policy.choose_key(upstairs), "<")
        self.assertEqual(policy.last_reason, "return:ascend")

    def test_committed_dark_route_reaches_far_remembered_end(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        cells = [Position(10, x) for x in range(10, 31)]
        start, goal = cells[0], cells[-1]
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._visit_counts.update({cell: 1 for cell in cells})
        current = start

        for decision_count in range(25):
            decision = replace(
                snapshot,
                player=replace(snapshot.player, position=current),
                grids={
                    goal: replace(
                        template, position=goal, passable=True, wall=False,
                        lit=False, known=True,
                    )
                },
            )
            key = policy.choose_key(decision)
            if current == goal:
                break
            self.assertEqual(policy.last_reason, "dark:backtrack")
            dy, dx = DIRECTIONS[key]
            current = Position(current.y + dy, current.x + dx)

        self.assertEqual(current, goal)
        self.assertLessEqual(decision_count, len(cells))
        self.assertEqual(policy._probe_counts[(10, 11)], 0)

    def test_dark_goal_ranking_prefers_upstairs_then_downstairs(self):
        snapshot = _snapshot_fixture()
        start = Position(10, 10)
        upstairs = Position(10, 13)
        downstairs = Position(11, 10)
        trail = {start, Position(10, 11), Position(10, 12), upstairs, downstairs}
        dark = replace(
            snapshot,
            player=replace(snapshot.player, position=start),
            grids={},
        )
        policy = HengbotPolicy()
        policy._floor_key = dark.floor_key
        policy._visit_counts.update({position: 1 for position in trail})
        policy._remembered_upstairs.add(upstairs)
        policy._remembered_downstairs.add(downstairs)

        key = policy.choose_key(dark)

        self.assertEqual(key, "6")
        self.assertEqual(policy._dark_route_goal, upstairs)

    def test_isolated_generic_dead_end_retires_after_arrival_budget(self):
        snapshot = _snapshot_fixture()
        start = Position(10, 10)
        goal = Position(10, 11)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._visit_counts.update({start: 1, goal: 1})
        policy._remembered_floor_t.update(
            {(start.y, start.x), (goal.y, goal.x)}
        )
        for dy, dx in DIRECTIONS.values():
            neighbor = Position(goal.y + dy, goal.x + dx)
            policy._known_t.add((neighbor.y, neighbor.x))

        current = start
        arrivals = 0
        retirement_window_arrivals = 0
        for _ in range(4 * PROBE_LIMIT + 4):
            dark = replace(
                snapshot,
                player=replace(snapshot.player, position=current),
                grids={},
            )
            key = policy.choose_key(dark)
            if key in DIRECTIONS:
                dy, dx = DIRECTIONS[key]
                next_position = Position(current.y + dy, current.x + dx)
                if next_position == goal:
                    arrivals += 1
                    if policy._dark_goal_counts[(goal.y, goal.x)] >= PROBE_LIMIT:
                        retirement_window_arrivals += 1
                current = next_position

        self.assertEqual(arrivals, PROBE_LIMIT)
        self.assertEqual(policy._dark_goal_counts[(goal.y, goal.x)], PROBE_LIMIT)
        self.assertEqual(retirement_window_arrivals, 0)
        self.assertNotEqual(policy._dark_route_goal, goal)

    def test_dark_probe_tiebreak_reduces_stairs_distance(self):
        snapshot = _snapshot_fixture()
        current = Position(10, 10)
        stairs = Position(5, 15)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._remembered_upstairs.add(stairs)
        distances = [max(abs(current.y - stairs.y), abs(current.x - stairs.x))]

        for _ in range(4):
            dark = replace(
                snapshot,
                player=replace(snapshot.player, position=current),
                grids={},
            )
            key = policy.choose_key(dark)
            self.assertEqual(policy.last_reason, "dark:probe")
            dy, dx = DIRECTIONS[key]
            current = Position(current.y + dy, current.x + dx)
            distances.append(
                max(abs(current.y - stairs.y), abs(current.x - stairs.x))
            )

        self.assertLess(distances[-1], distances[0])

    def test_occupied_dark_cells_are_removed_from_blocked_unknown(self):
        snapshot = _snapshot_fixture()
        origin = snapshot.player.position
        occupied = Position(origin.y - 1, origin.x)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._visit_counts[occupied] = 1
        policy._blocked_unknown.add((occupied.y, occupied.x))

        policy.choose_key(snapshot)

        self.assertNotIn((occupied.y, occupied.x), policy._blocked_unknown)

    def test_revealed_door_and_rubble_leave_probe_budget_for_dedicated_actions(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        origin = Position(10, 10)
        door = Position(10, 11)
        rubble = Position(11, 10)
        revealed = replace(
            snapshot,
            player=replace(snapshot.player, position=origin),
            grids={
                door: replace(
                    template, position=door, known=True, passable=False,
                    wall=False, is_closed_door=True, is_door=True,
                ),
                rubble: replace(
                    template, position=rubble, known=True, passable=False,
                    wall=False, can_dig=True,
                ),
            },
        )
        policy = HengbotPolicy()
        for target in (door, rubble):
            yx = (target.y, target.x)
            policy._probe_counts[yx] = PROBE_LIMIT
            policy._blocked_unknown.add(yx)

        policy._build_grid_index(revealed)

        for target in (door, rubble):
            yx = (target.y, target.x)
            self.assertNotIn(yx, policy._probe_counts)
            self.assertNotIn(yx, policy._blocked_unknown)
        self.assertEqual(policy._step_toward(revealed, door), "o6")
        self.assertEqual(policy._step_toward(revealed, rubble), "T2")

    def test_dark_route_obstacles_use_dedicated_budgets_without_retiring_stairs(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        origin = Position(10, 10)
        target = Position(10, 12)

        def run(obstacle, **grid_changes):
            policy = HengbotPolicy()
            policy._floor_key = snapshot.floor_key
            policy._visit_counts.update({origin: 1, obstacle: 1, target: 1})
            policy._remembered_upstairs.add(target)
            keys = []
            for decision in range(30):
                dark = replace(
                    snapshot,
                    turn=snapshot.turn + decision,
                    player=replace(snapshot.player, position=origin),
                    grids={
                        obstacle: replace(
                            template, position=obstacle, known=True,
                            passable=False, wall=False, lit=False, **grid_changes,
                        ),
                        target: replace(
                            template, position=target, known=True,
                            passable=True, wall=False, lit=False,
                            has_up_stairs=True,
                        ),
                    },
                )
                keys.append(policy.choose_key(dark))
            return policy, keys

        door_policy, door_keys = run(
            Position(10, 11), is_closed_door=True, is_door=True
        )
        self.assertEqual(door_keys[:3], ["o6", "o6", "o6"])
        self.assertEqual(door_policy._dark_goal_counts[(target.y, target.x)], 0)

        rubble_policy, rubble_keys = run(
            Position(10, 11), can_dig=True
        )
        self.assertEqual(rubble_keys, ["T6"] * 30)
        self.assertEqual(rubble_policy._dig_attempts[(10, 11)], 30)
        self.assertEqual(rubble_policy._dark_goal_counts[(target.y, target.x)], 0)

    def test_old_checkpoint_without_dark_route_fields_remains_selectable(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()
        state = pickle.loads(base64.b64decode(checkpoint(policy)))
        for name in (
            "_dark_goal_counts", "_dark_route", "_dark_route_goal",
            "_dark_route_expected",
        ):
            state.pop(name)
        encoded = base64.b64encode(pickle.dumps(state, protocol=5)).decode("ascii")

        restored = restore_checkpoint(HengbotPolicy, encoded)

        self.assertIsInstance(restored.choose_key(snapshot), str)

    def test_frozen_darkwalk_capture_pins_the_live_attractor(self):
        path = FIXTURES / "incident-darkwalk-attractor-20260825.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        live_escape = [
            row for row in rows
            if 37 <= row.get("decision_sequence", -1) <= 236
        ]
        reasons = [row["reason"] for row in live_escape]

        self.assertEqual(len(rows), 220)
        self.assertEqual(len(live_escape), 200)
        self.assertEqual(reasons.count("return:wait"), 198)
        self.assertEqual(reasons.count("return:probe"), 1)
        self.assertEqual(reasons.count("dark:backtrack"), 1)
        self.assertEqual(live_escape[-1]["position"], {"y": 8, "x": 56})

    def test_dark_route_crosses_a_nonremembered_occupied_trail_cell(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        start = Position(8, 56)
        trail = Position(7, 56)
        goal = Position(6, 56)
        routed = replace(
            snapshot,
            player=replace(snapshot.player, position=start),
            grids={
                start: replace(template, position=start, passable=True, wall=False,
                               lit=False, known=True),
                goal: replace(template, position=goal, passable=True, wall=False,
                              lit=False, known=True),
            },
        )
        policy = HengbotPolicy()
        policy._floor_key = routed.floor_key
        policy._visit_counts.update({start: 1, trail: 1, goal: 1})

        key = policy.choose_key(routed)

        self.assertEqual(key, "8")
        self.assertEqual(policy.last_reason, "dark:backtrack")
        self.assertNotIn(trail, routed.grids)
        self.assertNotIn((trail.y, trail.x), policy._remembered_floor_t)

    def test_dark_backtrack_entries_share_the_probe_budget(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        upper = Position(8, 56)
        lower = Position(9, 56)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._visit_counts.update({upper: 1, lower: 1})
        current = upper
        reasons = []

        for _ in range(4 * PROBE_LIMIT + 2):
            decision = replace(
                snapshot,
                player=replace(snapshot.player, position=current),
                grids={
                    upper: replace(template, position=upper, passable=True,
                                   wall=False, lit=False, known=True),
                    lower: replace(template, position=lower, passable=True,
                                   wall=False, lit=False, known=True),
                },
            )
            for dy, dx in DIRECTIONS.values():
                candidate = Position(current.y + dy, current.x + dx)
                if candidate not in {upper, lower}:
                    policy._probe_counts[(candidate.y, candidate.x)] = PROBE_LIMIT
            key = policy.choose_key(decision)
            reasons.append(policy.last_reason)
            if policy.last_reason == "dark:locomotion-exhausted":
                break
            if key in DIRECTIONS:
                dy, dx = DIRECTIONS[key]
                current = Position(current.y + dy, current.x + dx)

        self.assertLessEqual(reasons.count("dark:backtrack"), 2 * PROBE_LIMIT)
        self.assertEqual(reasons[-1], "dark:locomotion-exhausted")

    def test_remembered_own_cell_exhaustion_never_falls_to_return_wait(self):
        snapshot = _snapshot_fixture()
        template = next(iter(snapshot.grids.values()))
        origin = Position(8, 56)
        dark = replace(
            snapshot,
            player=replace(snapshot.player, position=origin),
            grids={
                origin: replace(template, position=origin, passable=True,
                                wall=False, lit=False, known=True),
            },
        )
        policy = HengbotPolicy()
        policy._floor_key = dark.floor_key
        for dy, dx in DIRECTIONS.values():
            policy._probe_counts[(origin.y + dy, origin.x + dx)] = PROBE_LIMIT

        key = policy.choose_key(dark)

        self.assertEqual((key, policy.last_reason),
                         (WAIT_KEY, "dark:locomotion-exhausted"))
        self.assertNotEqual(policy.last_reason, "return:wait")
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_missing_own_cell_is_dark_and_public_choice_does_not_read(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()

        self.assertTrue(snapshot.grids_observed)
        self.assertNotIn(snapshot.player.position, snapshot.grids)
        self.assertTrue(policy._is_dark(snapshot))
        self.assertFalse(policy._can_read_scrolls(snapshot))
        self.assertFalse(policy.choose_key(snapshot).startswith(READ_KEY))
        self.assertEqual(policy.last_reason, "dark:probe")

    def test_frozen_decisions_pin_the_historical_read_refusal_cadence(self):
        path = FIXTURES / "incident-darkread-guard-miss-20260824.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        decisions = [row for row in rows if "inventory" in row]
        reads = [
            (index, row)
            for index, row in enumerate(decisions)
            if row.get("key") == "rd"
        ]
        self.assertEqual(len(rows), 420)
        self.assertEqual(len(reads), 107)
        self.assertEqual(
            {second[0] - first[0] for first, second in zip(reads, reads[1:])},
            {3, 4},
        )
        self.assertGreaterEqual(
            min(
                second[1]["turn"] - first[1]["turn"]
                for first, second in zip(reads, reads[1:])
            ),
            OWNER_EXPECTATION_MAX_TURNS,
        )
        self.assertEqual(
            {tuple(sorted(row["inventory"].items())) for row in decisions},
            {(('free', 11), ('used', 12))},
        )

    def test_dark_probe_is_bounded_and_ends_at_visible_terminal(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()
        actions = []

        for _ in range(8 * PROBE_LIMIT + 2):
            key = policy.choose_key(snapshot)
            actions.append((key, policy.last_reason))
            if policy.last_reason == "dark:locomotion-exhausted":
                break

        self.assertTrue(any(reason == "dark:probe" for _, reason in actions))
        self.assertEqual(actions[-1], (WAIT_KEY, "dark:locomotion-exhausted"))
        self.assertIn("dark:locomotion-exhausted", POLICY_FINAL_STOP_REASONS)
        self.assertIn(
            "stopping the bot for investigation",
            _policy_final_stop_banner("dark:locomotion-exhausted"),
        )

    def test_dark_backtrack_uses_the_existing_remembered_graph(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()
        origin = snapshot.player.position
        target = Position(origin.y + 1, origin.x)
        template = next(iter(snapshot.grids.values()))
        routed = replace(
            snapshot,
            grids={
                **snapshot.grids,
                target: replace(template, position=target, passable=True, wall=False),
            },
        )
        policy._build_grid_index(routed)
        policy._visit_counts[target] = 1
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                       (-1, 1), (1, -1), (1, 1)):
            candidate = (origin.y + dy, origin.x + dx)
            if candidate != (target.y, target.x):
                policy._probe_counts[candidate] = PROBE_LIMIT

        key = policy._dark_locomotion_key(routed)

        self.assertEqual(key, "2")
        self.assertEqual(policy.last_reason, "dark:backtrack")

    def test_darkwalk_enters_adjacent_remembered_floor_before_probing(self):
        snapshot = _snapshot_fixture()
        origin = Position(5, 43)
        remembered = Position(5, 42)
        routed = replace(
            snapshot,
            player=replace(snapshot.player, position=origin),
        )
        policy = HengbotPolicy()
        policy._visit_counts[remembered] = 1
        positions = []
        reasons = []
        current = origin
        directions = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        for _ in range(4):
            decision = replace(
                routed,
                player=replace(routed.player, position=current),
                grids={
                    position: grid
                    for position, grid in snapshot.grids.items()
                    if position != current
                },
            )
            key = policy.choose_key(decision)
            reasons.append(policy.last_reason)
            dy, dx = directions[key]
            current = Position(current.y + dy, current.x + dx)
            positions.append(current)

        self.assertEqual(positions[0], remembered)
        self.assertTrue(all(position in snapshot.grids for position in positions))
        self.assertEqual(reasons[0], "dark:backtrack")

    def test_unidentified_lantern_preserves_dark_terminal_reason(self):
        snapshot = _snapshot_fixture()
        lantern = next(item for item in snapshot.equipment if item.is_lantern)
        unknown = replace(
            snapshot,
            equipment=[
                replace(item, known=False, fully_known=False)
                if item is lantern else item
                for item in snapshot.equipment
            ],
        )
        policy = HengbotPolicy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                       (-1, 1), (1, -1), (1, 1)):
            policy._probe_counts[
                (unknown.player.position.y + dy, unknown.player.position.x + dx)
            ] = PROBE_LIMIT

        key = None
        for _ in range(8 * PROBE_LIMIT + 2):
            key = policy.choose_key(unknown)
            if policy.last_reason == "dark:locomotion-exhausted":
                break

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "dark:locomotion-exhausted")
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertIn(
            "stopping the bot for investigation",
            _policy_final_stop_banner(policy.last_reason),
        )

    def test_unknown_lantern_uses_missing_cell_as_the_empty_signal(self):
        snapshot = _snapshot_fixture()
        lantern = next(item for item in snapshot.equipment if item.is_lantern)
        oil = InventoryItem(
            "z", "oil", 1, TVAL_FLASK, SV_FLASK_OIL, True, True, fuel=7500
        )
        unknown = replace(
            snapshot,
            equipment=[
                replace(item, known=False, fully_known=False)
                if item is lantern else item
                for item in snapshot.equipment
            ],
            inventory=[*snapshot.inventory, oil],
        )

        self.assertEqual(HengbotPolicy()._light_refill_item(unknown), oil)
        template = next(iter(snapshot.grids.values()))
        lit = replace(
            unknown,
            grids={
                **unknown.grids,
                unknown.player.position: replace(
                    template,
                    position=unknown.player.position,
                    passable=True,
                    wall=False,
                    lit=True,
                ),
            },
        )
        self.assertIsNone(HengbotPolicy()._light_refill_item(lit))

    def test_legacy_snapshot_without_grid_observation_remains_readable(self):
        snapshot = _snapshot_fixture()
        legacy = replace(snapshot, grids_observed=False)

        self.assertFalse(HengbotPolicy()._is_dark(legacy))


if __name__ == "__main__":
    unittest.main()
