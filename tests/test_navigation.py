"""Tests for the R1 navigation redesign: the shared progress ledger, the
mode-independent no-progress invariant, and the survival gate.

The regression scenarios mirror the 2026-07-17 Yeek Cave 6F incident: a
remembered-but-unreachable downstairs kept three navigation modes
(seek-downstairs / approach-descent / breakout:descent) handing the same
doomed goal to each other for 1600+ decisions while the character ate its
last ration and reached food_state "weak" with an empty pack.
"""

import json
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.cli import (
    LOOP_WINDOW,
    PostingContract,
    STARVING_STOP_LIMIT,
    _advance_starving_streak,
    _objective_for_reason,
)
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.navigation import NAV_TARGET_STALL_LIMIT, NavigationLedger
from hengbot.policy import (
    BREEDER_CONTAINMENT_WINDOW,
    COMBAT_OUTCOME_WINDOW,
    EXTENDED_STUCK_WINDOW,
    FRUITLESS_DISENGAGE_LIMIT,
    NAV_NO_PROGRESS_LIMIT,
    RESUME_DESCENT_BLOCK_DECISIONS,
    WAIT_KEY,
    HengbotPolicy,
)
from test_policy import FOOD, SCROLL, grid, hostile, item, player

from hengbot.model import SV_SCROLL_TELEPORT, SV_SCROLL_WORD_OF_RECALL

DUNGEON_FLOOR = (2, 6, 0)

DESCENT_TRIAD_REASONS = {"seek-downstairs", "approach-descent", "breakout:descent"}


class NavigationLedgerTest(unittest.TestCase):
    def test_target_expiry_precedes_process_loop_detector(self):
        # The ledger is the recovery mechanism; the outer detector is only a
        # fail-safe.  If this ordering reverses, a two-cell descent oscillation
        # stops the bot before the policy can abandon its stale stair target.
        self.assertLess(NAV_TARGET_STALL_LIMIT, LOOP_WINDOW)

    def test_resume_descent_guard_precedes_process_loop_detector(self):
        self.assertLess(RESUME_DESCENT_BLOCK_DECISIONS, LOOP_WINDOW)

    def test_first_observation_counts_as_improvement(self):
        ledger = NavigationLedger()
        self.assertTrue(ledger.observe("descend", Position(1, 1), 10))
        self.assertTrue(ledger.improved_this_decision)

    def test_improvement_resets_stall(self):
        ledger = NavigationLedger(stall_limit=3)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        self.assertFalse(ledger.is_expired("descend", target))
        self.assertTrue(ledger.observe("descend", target, 9))
        ledger.observe("descend", target, 9)
        ledger.observe("descend", target, 9)
        self.assertFalse(ledger.is_expired("descend", target))

    def test_stalled_target_expires_for_its_kind_only(self):
        ledger = NavigationLedger(stall_limit=2)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 12)
        self.assertTrue(ledger.is_expired("descend", target))
        self.assertEqual(ledger.expired_targets("descend"), {target})
        self.assertFalse(ledger.is_expired("explore", target))

    def test_reaching_stalled_descent_target_clears_routing_expiry(self):
        ledger = NavigationLedger(stall_limit=2)
        target = Position(1, 1)
        ledger.commit_descent_route(target, [target])
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        self.assertTrue(ledger.is_expired("descend", target))

        ledger.observe("descend", target, 0)

        self.assertFalse(ledger.is_expired("descend", target))

    def test_begin_decision_clears_the_improvement_flag(self):
        ledger = NavigationLedger()
        ledger.observe("descend", Position(1, 1), 10)
        ledger.begin_decision()
        self.assertFalse(ledger.improved_this_decision)

    def test_reset_forgets_expiries(self):
        ledger = NavigationLedger(stall_limit=1)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        self.assertTrue(ledger.is_expired("descend", target))
        ledger.reset()
        self.assertFalse(ledger.is_expired("descend", target))

    def test_external_evidence_can_expire_a_target_immediately(self):
        ledger = NavigationLedger()
        target = Position(1, 1)
        ledger.expire("descend", target)
        self.assertTrue(ledger.is_expired("descend", target))

    def test_ledger_owns_committed_descent_route(self):
        ledger = NavigationLedger()
        target = Position(3, 3)
        path = [Position(2, 2), target]
        ledger.commit_descent_route(target, path)
        ledger.advance_descent_route(path[0])
        self.assertEqual(ledger.descent_target, target)
        self.assertEqual(ledger.descent_path, (target,))
        ledger.expire("descend", target)
        self.assertIsNone(ledger.descent_target)
        self.assertEqual(ledger.descent_path, ())


class DescentIncidentReplayTest(unittest.TestCase):
    """Reusable JSONL incident replay harness for committed descent routes."""

    FIXTURES = Path(__file__).with_name("fixtures")

    @classmethod
    def _load_jsonl(cls, name):
        with (cls.FIXTURES / name).open(encoding="utf-8-sig") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def test_2256_window_commits_one_stair_and_makes_monotonic_progress(self):
        incident = self._load_jsonl("descent-routing-2026-07-17-2256.jsonl")
        original_positions = [
            (row["position"]["y"], row["position"]["x"]) for row in incident
        ]
        self.assertGreaterEqual(max(Counter(original_positions).values()), 3)
        self.assertIn(("3", "7"), zip(
            (row["key"] for row in incident),
            (row["key"] for row in incident[1:]),
        ))

        snapshots = [
            parse_snapshot(row)
            for row in self._load_jsonl(
                "descent-routing-2026-07-17-2256-snapshots.jsonl"
            )
        ]
        self.assertEqual([snapshot.turn for snapshot in snapshots], [885296, 885302])

        policy = HengbotPolicy()
        policy._floor_key = snapshots[0].floor_key
        policy._remembered_downstairs.update(
            grid.position
            for grid in snapshots[0].grids.values()
            if grid.has_down_stairs
        )
        visited = [snapshots[0].player.position]
        keys = []
        targets = []
        for snapshot in snapshots:
            self.assertEqual(snapshot.player.position, visited[-1])
            policy._build_grid_index(snapshot)
            step = policy._descent_step(snapshot)
            self.assertIsNotNone(step)
            targets.append(policy._nav_ledger.descent_target)
            keys.append(policy._direction_key(snapshot.player.position, step))
            visited.append(step)

        self.assertEqual(visited, [Position(15, 58), Position(16, 59), Position(15, 60)])
        self.assertEqual(targets, [Position(15, 60), Position(15, 60)])
        self.assertEqual(keys, ["3", "9"])
        self.assertLess(max(Counter(visited).values()), 3)
        self.assertNotIn(("3", "7"), zip(keys, keys[1:]))

    def test_0124_live_state_replays_existing_guardian_return_path(self):
        incident = self._load_jsonl("descend-in-place-2026-07-18-0124.jsonl")
        self.assertEqual(incident[0]["turn"], 885977)
        self.assertEqual(incident[-1]["reason"], "loop-detected")
        self.assertGreaterEqual(
            max(Counter(
                (row["position"]["y"], row["position"]["x"])
                for row in incident
            ).values()),
            5,
        )

        snapshot = parse_snapshot(self._load_jsonl(
            "descend-in-place-2026-07-18-0124-snapshots.jsonl"
        )[0])
        # The live CLI loads static dungeon knowledge.  A bare policy has no
        # guardian/max-depth facts, so recreate the runtime knowledge that
        # made 8F the penultimate Yeek floor in the captured session.
        yeek = DungeonInfo(
            id=2,
            name="Yeek cave",
            min_depth=1,
            max_depth=9,
            min_player_level=1,
            guardian_id=237,
        )
        policy = HengbotPolicy(dungeon_knowledge={2: yeek})
        here = snapshot.grid_at(snapshot.player.position)
        self.assertIsNotNone(here)
        self.assertTrue(here.has_down_stairs)
        self.assertTrue(policy._guardian_descent_blocked(snapshot))
        self.assertFalse(policy._descent_is_blocked(snapshot))
        self.assertFalse(policy._is_descent_target(snapshot, here))

        # Regression coverage for the pre-existing guardian return owner: grid-
        # visible vetoed stairs cannot re-enter the remembered-only fallback.
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._remembered_downstairs.update(
            grid.position for grid in snapshot.grids.values() if grid.is_descent
        )
        self.assertIsNone(policy._descent_step(snapshot))
        self.assertIsNone(policy._nav_ledger.descent_target)
        key = policy.choose_key(snapshot)
        self.assertEqual(key, "rg")
        self.assertEqual(policy.last_reason, "return:recall")
        self.assertEqual(policy._last_return_trigger, "guardian-kit-insufficient")
        self.assertEqual(_objective_for_reason(policy.last_reason), "Return to town")

    def test_all_visible_next_depth_vetoes_keep_exploring_current_floor(self):
        snapshot = parse_snapshot(self._load_jsonl(
            "descend-in-place-2026-07-18-0124-snapshots.jsonl"
        )[0])
        snapshot = replace(snapshot, floor_key=(1, 19, 0))
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._remembered_downstairs.update(
            grid.position for grid in snapshot.grids.values() if grid.is_descent
        )
        # Isolate the prospective-depth owner from unrelated supply returns.
        policy._should_start_town_return = lambda _snapshot: False
        policy._recall_departure_shortage = lambda _snapshot: False

        self.assertTrue(all(
            not policy._is_descent_target(snapshot, grid)
            for grid in snapshot.grids.values() if grid.is_descent
        ))
        key = policy.choose_key(snapshot)

        self.assertFalse(key.startswith("r"))
        self.assertNotEqual(policy.last_reason, "return:recall")
        self.assertIsNone(policy._last_return_trigger)
        self.assertFalse(policy._returning_to_town)


class StairRejectionInvalidationTest(unittest.TestCase):
    def _stair_snapshot(self, *, downstairs=False, upstairs=False, turn=100):
        position = Position(6, 39)
        return Snapshot(
            player(position.y, position.x, food=12000),
            {position: grid(
                position.y, position.x,
                downstairs=downstairs, upstairs=upstairs,
            )},
            [],
            floor_key=(2, 5, 0),
            width=80,
            height=20,
            turn=turn,
        )

    @staticmethod
    def _fundraising_ascender(snapshot):
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._floor_key = snapshot.floor_key
        policy._breeder_breakthrough_floor = snapshot.floor_key
        return policy

    def test_same_observed_turn_posts_only_one_fundraising_ascend_character(self):
        snapshot = self._stair_snapshot(upstairs=True, turn=4519803)
        policy = self._fundraising_ascender(snapshot)

        posted = [
            key
            for key in (policy.choose_key(snapshot), policy.choose_key(snapshot))
            if key
        ]

        self.assertEqual(posted, ["<"])

    def test_message_clear_stale_board_does_not_repost_fundraising_ascend(self):
        first_board = replace(
            self._stair_snapshot(upstairs=True, turn=329416),
            messages=("The bell rings three times!",),
        )
        stale_board = replace(first_board, messages=())
        policy = self._fundraising_ascender(first_board)

        posted = [
            key for key in (
                policy.choose_key(first_board),
                policy.choose_key(stale_board),
            ) if key
        ]

        self.assertEqual(posted, ["<"])

    def test_floor_change_releases_stair_command_for_a_new_post(self):
        snapshot = self._stair_snapshot(upstairs=True, turn=4519803)
        policy = self._fundraising_ascender(snapshot)
        first = policy.choose_key(snapshot)
        changed_floor = replace(snapshot, floor_key=(2, 4, 0), turn=4519804)

        second = policy.choose_key(changed_floor)

        self.assertEqual([first, second], ["<", "<"])

    def test_new_unchanged_observation_retries_through_rejection_strikes(self):
        snapshot = self._stair_snapshot(upstairs=True, turn=4519803)
        policy = self._fundraising_ascender(snapshot)
        self.assertEqual(policy.choose_key(snapshot), "<")
        self.assertEqual(policy.choose_key(snapshot), "")

        retry = policy.choose_key(replace(snapshot))

        target = snapshot.player.position
        self.assertEqual(retry, "<")
        self.assertEqual(policy._stair_rejection_strikes[("<", target)], 1)

    def test_all_floor_command_shapes_share_pending_suppression(self):
        snapshot = self._stair_snapshot(downstairs=True)
        for key in ("<", ">", ">\ry", ">y"):
            with self.subTest(key=key):
                policy = HengbotPolicy()
                policy._remember_stair_command(snapshot, key)
                self.assertEqual(
                    policy._suppress_pending_stair_command(snapshot, key), ""
                )

    def test_refused_stair_recovery_reposts_instead_of_absorbing_empty_keys(self):
        snapshot = replace(
            self._stair_snapshot(downstairs=True, turn=334683),
            messages=("You see no relevant prompt.",),
        )
        policy = HengbotPolicy()

        first = policy.choose_key(snapshot)
        policy.refuse_key_posting("descend", first)
        probe = policy.choose_key(snapshot)
        # Capture batches 257-259 were one player_turn, then look+player_turn,
        # then one player_turn.  The latter boards cleared the message while
        # retaining turn 334683 and the owner progress core.
        recovered = policy.choose_key(replace(snapshot, messages=()))

        self.assertEqual(first, ">")
        self.assertEqual(probe, "l\x1b")
        self.assertEqual(recovered, ">")
        self.assertNotEqual(policy.last_reason, "stair:await-observation")

    def test_refused_stair_recovery_is_restart_immune_for_two_fresh_instances(self):
        snapshot = replace(
            self._stair_snapshot(downstairs=True, turn=334683),
            messages=("You see no relevant prompt.",),
        )
        delivered = []

        for _ in range(2):
            policy = HengbotPolicy()
            first = policy.choose_key(snapshot)
            policy.refuse_key_posting("descend", first)
            delivered.append(policy.choose_key(snapshot))
            delivered.append(policy.choose_key(replace(snapshot, messages=())))

        self.assertEqual(delivered, ["l\x1b", ">", "l\x1b", ">"])

    def test_interleaved_refusal_probe_releases_older_stair_watch(self):
        """The 04:38 capture refused ~9 after accepting the descent key."""
        snapshot = self._stair_snapshot(downstairs=True, turn=2128312)
        policy = HengbotPolicy()

        first = policy.choose_key(snapshot)
        policy.refuse_key_posting("home:request-knowledge-scan", "~9")
        probe = policy.choose_key(snapshot)
        recovered = policy.choose_key(snapshot)

        self.assertEqual(first, ">")
        self.assertEqual(probe, "l\x1b")
        self.assertEqual(recovered, ">")
        self.assertNotEqual(policy.last_reason, "stair:await-observation")

    def test_two_rejected_descents_expire_phantom_from_routing_only(self):
        snapshot = self._stair_snapshot(downstairs=True)
        policy = HengbotPolicy()

        self.assertEqual(policy.choose_key(snapshot), ">")
        self.assertEqual(policy.choose_key(replace(snapshot)), ">")
        self.assertIn(snapshot.player.position, policy._remembered_downstairs)
        key = policy.choose_key(replace(snapshot))

        target = snapshot.player.position
        self.assertEqual(key, ">")
        self.assertNotIn(target, policy._remembered_downstairs)
        self.assertTrue(policy._nav_ledger.is_expired("descend", target))
        self.assertIsNone(policy._descent_step(snapshot))
        self.assertEqual(policy._stair_rejection_strikes[(">", target)], 2)

    def test_real_descent_floor_change_is_never_struck(self):
        snapshot = self._stair_snapshot(downstairs=True)
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snapshot), ">")

        next_floor = replace(snapshot, floor_key=(2, 6, 0), turn=101)
        policy.choose_key(next_floor)

        self.assertFalse(policy._stair_rejection_strikes)

    def test_rejection_requires_same_turn_as_well_as_floor_and_position(self):
        snapshot = self._stair_snapshot(downstairs=True)
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snapshot), ">")

        policy.choose_key(replace(snapshot, turn=101))

        self.assertFalse(policy._stair_rejection_strikes)

    def test_upstairs_rejection_is_symmetric(self):
        snapshot = self._stair_snapshot(upstairs=True)
        target = snapshot.player.position
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._remembered_upstairs.add(target)

        for _ in range(2):
            policy._remember_stair_command(snapshot, "<")
            policy._observe_stair_command(replace(snapshot))

        self.assertNotIn(target, policy._remembered_upstairs)
        self.assertTrue(policy._nav_ledger.is_expired("ascend", target))

    def test_prime_marks_first_snapshot_stairs_unverified(self):
        snapshot = self._stair_snapshot(downstairs=True)
        policy = HengbotPolicy()
        policy.prime(snapshot)
        self.assertIn((">", snapshot.player.position), policy._unverified_stairs)

    def test_distant_launch_stair_stall_expires_normally(self):
        player_position = Position(6, 35)
        target = Position(6, 39)
        grids = {
            Position(6, x): grid(6, x, downstairs=x == target.x)
            for x in range(player_position.x, target.x + 1)
        }
        snapshot = Snapshot(
            player(player_position.y, player_position.x, food=12000),
            grids,
            [],
            floor_key=(2, 5, 0),
            width=80,
            height=20,
        )
        policy = HengbotPolicy()
        policy.prime(snapshot)

        self.assertNotIn((">", target), policy._unverified_stairs)
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            policy._descent_step(snapshot)

        self.assertTrue(policy._nav_ledger.is_expired("descend", target))
        self.assertIsNone(policy._descent_step(snapshot))

    def test_unverified_launch_stair_overrides_old_navigation_expiry(self):
        snapshot = self._stair_snapshot(downstairs=True)
        policy = HengbotPolicy()
        policy.prime(snapshot)
        target = snapshot.player.position
        policy._nav_ledger.expire("descend", target)
        policy._descent_block_countdown = 0

        self.assertEqual(policy.choose_key(snapshot), ">")
        self.assertEqual(policy.choose_key(replace(snapshot)), ">")
        key = policy.choose_key(replace(snapshot))

        self.assertEqual(key, ">")
        self.assertNotIn((">", target), policy._unverified_stairs)
        self.assertTrue(policy._nav_ledger.is_expired("descend", target))
        self.assertIsNone(policy._descent_step(snapshot))

    def test_2031_replay_removes_both_phantoms_then_explores(self):
        policy = HengbotPolicy()
        floor = (2, 5, 0)
        phantoms = (Position(6, 39), Position(2, 39))
        policy._floor_key = floor
        policy._remembered_downstairs.update(phantoms)

        for target in phantoms:
            snapshot = Snapshot(
                player(target.y, target.x, food=12000), {}, [],
                floor_key=floor, width=80, height=20, turn=651966,
            )
            for _ in range(2):
                policy._remember_stair_command(snapshot, ">")
                policy._observe_stair_command(replace(snapshot))

        self.assertFalse(policy._remembered_downstairs)
        self.assertEqual(
            policy._nav_ledger.expired_targets("descend"), set(phantoms)
        )
        room = Snapshot(
            player(6, 39, food=12000),
            {
                Position(6, 39): grid(6, 39),
                Position(6, 40): grid(6, 40),
            },
            [], floor_key=floor, width=80, height=20, turn=651966,
        )
        self.assertNotEqual(policy.choose_key(room), ">")
        self.assertNotIn(policy.last_reason, DESCENT_TRIAD_REASONS)


class DescentTargetExpiryTest(unittest.TestCase):
    """The incident regression: an unreachable remembered stair must expire."""

    def _incident_snapshot(self):
        # A tiny mapped pocket with an open (unknown) edge to the east — a
        # permanent frontier the pathfinder can approach but never reveal
        # (dark-floor flicker) — and a remembered downstairs far outside it.
        origin = Position(10, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(9, 10): grid(9, 10),
        }
        return Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )

    def test_unreachable_remembered_stair_expires_and_frees_navigation(self):
        snapshot = self._incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        target = Position(12, 30)
        policy._remembered_downstairs.add(target)

        reasons = []
        expired_at = None
        for step in range(NAV_TARGET_STALL_LIMIT * 3):
            policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            if policy._nav_ledger.is_expired("descend", target):
                expired_at = step
                break
        self.assertIsNotNone(
            expired_at,
            f"target never expired; last reasons: {reasons[-6:]}",
        )
        self.assertLessEqual(expired_at, NAV_TARGET_STALL_LIMIT * 2)

        # From now on the doomed stair must be dead to EVERY mode: no
        # seek/approach/breakout decision may target it again this visit.
        for _ in range(20):
            policy.choose_key(snapshot)
            self.assertNotIn(policy.last_reason, DESCENT_TRIAD_REASONS)

    def test_reachable_visible_stair_is_still_walked_to(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        snapshot = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "seek-downstairs")

    def test_floor_change_resets_expiries(self):
        snapshot = self._incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        target = Position(12, 30)
        policy._nav_ledger.observe("descend", target, 10)
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            policy._nav_ledger.observe("descend", target, 10)
        self.assertTrue(policy._nav_ledger.is_expired("descend", target))
        next_floor = Snapshot(
            player(10, 10, food=12000),
            dict(snapshot.grids),
            [],
            floor_key=(2, 7, 0),
            width=40,
            height=40,
        )
        policy.choose_key(next_floor)
        self.assertFalse(policy._nav_ledger.is_expired("descend", target))


class UnenterableExploreGoalTest(unittest.TestCase):
    CAPTURE = (
        Path(__file__).parents[1]
        / "incident-captures"
        / "20260730-0712-west-pocket-loop"
        / "pocket-turn457749.jsonl"
    )
    GOAL = Position(16, 3)
    RING = (
        Position(16, 2),
        Position(15, 3),
        Position(15, 4),
        Position(16, 4),
        Position(17, 3),
        Position(17, 2),
    )

    @classmethod
    def _capture_snapshot(cls):
        with cls.CAPTURE.open(encoding="utf-8-sig") as stream:
            return parse_snapshot(json.loads(next(stream)))

    @staticmethod
    def _seed_incident_ledger(policy):
        data = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "west-pocket-exploration-ledger.json"
            ).read_text(encoding="utf-8")
        )
        policy._visit_counts.update(
            {
                Position(y, x): visits
                for y, x, visits in data["visit_counts"]
            }
        )
        policy._probed_frontiers.update(
            Position(y, x) for y, x in data["probed_frontiers"]
        )

    def test_real_west_pocket_replay_retires_goal_and_plans_elsewhere(self):
        base = self._capture_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = base.floor_key
        self._seed_incident_ledger(policy)

        proposed = []
        for position in self.RING:
            snapshot = replace(
                base, player=replace(base.player, position=position)
            )
            key = policy.choose_key(snapshot)
            pending = getattr(policy, "_pending_one_step_explore", None)
            proposed.append(pending[1] if pending is not None else None)
            self.assertEqual(policy.last_reason, "explore")
            self.assertNotEqual(key, WAIT_KEY)

        self.assertEqual(proposed[:3], [self.GOAL] * 3)
        self.assertNotIn(self.GOAL, proposed[3:])
        self.assertIn(self.GOAL, policy._unenterable_explore_goals)
        self.assertTrue(
            any(goal is not None and goal != self.GOAL for goal in proposed[3:])
        )

    def _retired_synthetic_goal(self):
        goal = Position(10, 10)
        origins = (Position(9, 9), Position(9, 10), Position(9, 11))
        grids = {
            goal: replace(
                grid(goal.y, goal.x, terrain_id=1),
                has_monster=True,
                monster_index=47,
            )
        }
        grids.update(
            {origin: grid(origin.y, origin.x, terrain_id=1) for origin in origins}
        )
        policy = HengbotPolicy()
        snapshot = Snapshot(
            player(origins[0].y, origins[0].x, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )
        policy._floor_key = snapshot.floor_key
        policy._visit_counts.update({origin: 1 for origin in origins})
        for origin in origins:
            attempted = replace(
                snapshot, player=replace(snapshot.player, position=origin)
            )
            policy._remember_one_step_explore(attempted, origin, goal)
            policy._observe_one_step_explore(attempted)
        return policy, snapshot, goal

    def test_signature_change_revives_transiently_blocked_goal(self):
        policy, snapshot, goal = self._retired_synthetic_goal()
        self.assertIn(goal, policy._unenterable_explore_goals)

        changed_grid = replace(
            snapshot.grids[goal], has_monster=False, monster_index=0
        )
        changed = replace(
            snapshot, grids={**snapshot.grids, goal: changed_grid}
        )
        policy._observe_one_step_explore(changed)

        self.assertNotIn(goal, policy._unenterable_explore_goals)
        policy._build_grid_index(changed)
        self.assertEqual(policy._plan_explore_path(changed)[-1], goal)

    def test_retirement_does_not_synthesize_visit_count(self):
        policy, _snapshot, goal = self._retired_synthetic_goal()

        self.assertIn(goal, policy._unenterable_explore_goals)
        self.assertEqual(policy._visit_counts[goal], 0)


class NavigationInvariantTest(unittest.TestCase):
    GIVEUP_CAPTURE = (
        Path(__file__).parents[1]
        / "incident-captures"
        / "20260730-0257-exploration-giveup"
        / "giveup-turn437868.jsonl"
    )

    def _quiet_room(self, *, upstairs=False, inventory=()):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        if upstairs:
            grids[Position(10, 12)] = grid(10, 12, upstairs=True)
        return Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
            inventory=list(inventory),
        )

    def _scripted_policy(self, reasons):
        class ScriptedPolicy(HengbotPolicy):
            def __init__(self):
                super().__init__()
                self._reasons = iter(reasons)

            # TEST_FAKERY_LINT_ALLOW: public-path-replaced: scripted navigation reasons intentionally exercise choose_key routing through a policy subclass
            def _decide(self, snapshot):
                self.last_reason = next(self._reasons)
                return "6" if snapshot.player.position.x == 10 else "4"

        return ScriptedPolicy()

    @staticmethod
    def _recall_refusal_snapshot():
        position = Position(42, 20)
        upstairs = Position(42, 19)
        return Snapshot(
            player(position.y, position.x, level=23),
            {
                position: grid(position.y, position.x),
                upstairs: grid(upstairs.y, upstairs.x, upstairs=True),
            },
            [],
            floor_key=(3, 23, 0),
            width=80,
            height=50,
            inventory=[item(
                "d", SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9,
                name="Word of Recall",
            )],
        )

    def test_refused_return_recall_routes_to_upstairs_without_burning_a_turn(self):
        snapshot = self._recall_refusal_snapshot()
        policy = HengbotPolicy()
        policy._returning_to_town = True
        contract = PostingContract()
        contract.posted(snapshot, "rd", "return:recall")

        proposed = policy.choose_key(snapshot)
        self.assertEqual((proposed, policy.last_reason), ("rd", "return:recall"))
        self.assertFalse(contract.allow(
            snapshot, proposed, policy.last_reason
        ))
        incident = contract.last_incident
        self.assertEqual(
            incident["marker"],
            "posting-contract:identical-repost-unobserved",
        )
        policy.refuse_key_posting(incident["owner"], incident["key"])
        self.assertFalse(policy._owner_may_select(snapshot, "return:recall"))

        probe = policy.choose_key(snapshot)
        self.assertEqual((probe, policy.last_reason), ("l\x1b", "return:recall"))
        self.assertTrue(contract.allow(snapshot, probe, policy.last_reason))
        contract.posted(snapshot, probe, policy.last_reason)

        fallback = policy.choose_key(snapshot)
        self.assertEqual(
            (fallback, policy.last_reason), ("4", "return:seek-upstairs")
        )
        self.assertNotEqual(fallback, WAIT_KEY)

    def test_unrefused_return_recall_posts_exact_derived_characters(self):
        snapshot = self._recall_refusal_snapshot()
        policy = HengbotPolicy()
        policy._returning_to_town = True
        contract = PostingContract()

        key = policy.choose_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("rd", "return:recall"))
        self.assertTrue(contract.allow(snapshot, key, policy.last_reason))

    def test_combat_interspersed_two_cell_ping_pong_breaks_out(self):
        cells = {
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(11, 10): grid(11, 10),
        }
        reasons = [
            "melee" if decision % 3 == 1 else "seek-loot"
            for decision in range(EXTENDED_STUCK_WINDOW + 2)
        ]
        policy = self._scripted_policy(reasons)
        policy._floor_key = DUNGEON_FLOOR
        policy._visit_counts.update(
            {Position(10, 10): 2, Position(10, 11): 2}
        )
        policy._loot_target = Position(10, 9)
        policy._shopping_approach_goal = Position(11, 10)
        policy._shopping_approach_store_type = 1
        policy._descent_target_goal = Position(12, 10)
        policy._nav_ledger.commit_descent_route(
            policy._descent_target_goal, [policy._descent_target_goal]
        )
        policy._explore_path = [Position(11, 10)]
        keys = []
        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            x = 10 + decision % 2
            snapshot = Snapshot(
                player(10, x, food=12000),
                cells,
                [hostile(1, 20, 20, hp=50)],
                floor_key=DUNGEON_FLOOR,
                width=40,
                height=40,
            )
            keys.append(policy.choose_key(snapshot))
            if policy.last_reason == "nav:break-oscillation":
                break

        self.assertEqual(policy.last_reason, "nav:break-oscillation")
        self.assertIn(keys[-1], {"1", "2", "3", "4", "7", "8", "9"})
        self.assertIsNone(policy._loot_target)
        self.assertIsNone(policy._shopping_approach_goal)
        self.assertIsNone(policy._descent_target_goal)
        self.assertEqual(policy._explore_path, [])

    def test_live_six_cell_upstairs_cycle_breaks_outside_confinement(self):
        cycle = [
            Position(34, 72),
            Position(34, 73),
            Position(35, 71),
            Position(35, 73),
            Position(36, 71),
            Position(36, 72),
        ]
        cells = {
            Position(y, x): grid(y, x)
            for y in range(33, 38)
            for x in range(70, 75)
        }
        policy = self._scripted_policy(
            ["fundraise:seek-upstairs"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        policy._floor_key = DUNGEON_FLOOR
        policy._visit_counts.update({position: 2 for position in cycle})

        key = ""
        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            position = cycle[decision % len(cycle)]
            snapshot = Snapshot(
                player(position.y, position.x, food=12000),
                cells,
                [],
                floor_key=DUNGEON_FLOOR,
                width=80,
                height=80,
            )
            key = policy.choose_key(snapshot)
            if policy.last_reason == "nav:break-oscillation":
                break

        self.assertEqual(policy.last_reason, "nav:break-oscillation")
        self.assertEqual(key, "7")
        self.assertNotIn(Position(33, 71), cycle)

    def test_seven_cell_cycle_is_outside_confinement_bound(self):
        cycle = [
            Position(20, 20),
            Position(20, 21),
            Position(20, 22),
            Position(21, 22),
            Position(22, 22),
            Position(22, 21),
            Position(22, 20),
        ]
        cells = {
            Position(y, x): grid(y, x)
            for y in range(19, 24)
            for x in range(19, 24)
        }
        policy = self._scripted_policy(
            ["seek-upstairs"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        policy._floor_key = DUNGEON_FLOOR
        policy._visit_counts.update({position: 2 for position in cycle})

        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            position = cycle[decision % len(cycle)]
            snapshot = Snapshot(
                player(position.y, position.x, food=12000),
                cells,
                [],
                floor_key=DUNGEON_FLOOR,
                width=40,
                height=40,
            )
            policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "seek-upstairs")

    def test_six_cell_cycle_with_outcome_progress_is_exempt(self):
        cycle = [
            Position(34, 72),
            Position(34, 73),
            Position(35, 71),
            Position(35, 73),
            Position(36, 71),
            Position(36, 72),
        ]
        cells = {
            Position(y, x): grid(y, x)
            for y in range(33, 38)
            for x in range(70, 75)
        }
        cases = {
            "kill": lambda decision: {
                "player": replace(
                    player(0, 0, food=12000), exp=decision
                ),
                "monsters": [],
            },
            "hp": lambda decision: {
                "player": player(0, 0, food=12000),
                "monsters": [hostile(1, 35, 72, hp=100 - decision)],
            },
            "inventory": lambda decision: {
                "player": player(0, 0, food=12000, gold=1000 + decision),
                "monsters": [],
            },
        }
        for name, outcome in cases.items():
            with self.subTest(name=name):
                policy = self._scripted_policy(
                    ["seek-upstairs"] * (EXTENDED_STUCK_WINDOW + 2)
                )
                policy._floor_key = DUNGEON_FLOOR
                policy._visit_counts.update(
                    {position: 2 for position in cycle}
                )
                for decision in range(EXTENDED_STUCK_WINDOW + 2):
                    position = cycle[decision % len(cycle)]
                    state = outcome(decision)
                    snapshot = Snapshot(
                        replace(state["player"], position=position),
                        cells,
                        state["monsters"],
                        floor_key=DUNGEON_FLOOR,
                        width=80,
                        height=80,
                    )
                    policy.choose_key(snapshot)

                self.assertEqual(policy.last_reason, "seek-upstairs")

    def test_six_cell_stationary_by_design_cycle_is_exempt(self):
        cycle = [
            Position(34, 72),
            Position(34, 73),
            Position(35, 71),
            Position(35, 73),
            Position(36, 71),
            Position(36, 72),
        ]
        cells = {
            Position(y, x): grid(y, x)
            for y in range(33, 38)
            for x in range(70, 75)
        }
        policy = self._scripted_policy(
            ["quest-strategy:hold"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        policy._floor_key = DUNGEON_FLOOR
        policy._visit_counts.update({position: 2 for position in cycle})

        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            position = cycle[decision % len(cycle)]
            snapshot = Snapshot(
                player(position.y, position.x, food=12000),
                cells,
                [],
                floor_key=DUNGEON_FLOOR,
                width=80,
                height=80,
            )
            policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "quest-strategy:hold")

    def test_mining_dig_confinement_is_exempt(self):
        cells = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(11, 10): grid(11, 10),
        }
        policy = self._scripted_policy(
            ["fundraise:dig-to-treasure"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            snapshot = Snapshot(
                player(10, 10 + decision % 2, food=12000),
                cells,
                [],
                floor_key=DUNGEON_FLOOR,
                width=40,
                height=40,
            )
            policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "fundraise:dig-to-treasure")

    def test_quest_hold_wait_confinement_is_exempt(self):
        snapshot = self._quiet_room()
        policy = self._scripted_policy(
            ["quest-strategy:hold"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        for _ in range(EXTENDED_STUCK_WINDOW + 2):
            policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "quest-strategy:hold")

    def test_in_place_damaging_fight_is_exempt(self):
        base = self._quiet_room()
        policy = self._scripted_policy(
            ["melee"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            fighting = replace(
                base,
                visible_monsters=[
                    hostile(1, 10, 11, hp=100 - decision)
                ],
            )
            policy.choose_key(fighting)

        self.assertNotEqual(policy.last_reason, "nav:break-oscillation")

    def test_fresh_tile_exploration_is_not_confinement(self):
        cells = {
            Position(10, x): grid(10, x)
            for x in range(10, 10 + EXTENDED_STUCK_WINDOW + 2)
        }
        policy = self._scripted_policy(
            ["explore"] * (EXTENDED_STUCK_WINDOW + 2)
        )
        for decision in range(EXTENDED_STUCK_WINDOW + 2):
            snapshot = Snapshot(
                player(10, 10 + decision, food=12000),
                cells,
                [],
                floor_key=DUNGEON_FLOOR,
                width=80,
                height=40,
            )
            policy.choose_key(snapshot)

        self.assertEqual(policy.last_reason, "explore")
        expected = [
            Position(10, x)
            for x in range(12, 10 + EXTENDED_STUCK_WINDOW + 2)
        ]
        self.assertEqual(list(policy._recent), expected)

    def test_no_progress_counter_trips_the_invariant(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        # The first couple of calls legitimately count as progress (initial
        # coverage and economy-marker baselines); the invariant needs the
        # budget's worth of genuinely flat decisions after those.
        for _ in range(NAV_NO_PROGRESS_LIMIT + 2):
            policy._update_navigation_progress(snapshot)
        self.assertTrue(policy._nav_exhausted)

    def test_new_coverage_resets_the_counter(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        for _ in range(NAV_NO_PROGRESS_LIMIT - 1):
            policy._update_navigation_progress(snapshot)
        policy._remembered_known_t.add((20, 20))
        policy._update_navigation_progress(snapshot)
        self.assertEqual(policy._nav_stall_count, 0)
        self.assertFalse(policy._nav_exhausted)

    def test_combat_resets_the_counter(self):
        snapshot = self._quiet_room()
        fighting = Snapshot(
            snapshot.player,
            dict(snapshot.grids),
            [hostile(1, 10, 11)],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._nav_stall_count = NAV_NO_PROGRESS_LIMIT - 1
        policy._update_navigation_progress(fighting)
        self.assertEqual(policy._nav_stall_count, 0)

    def test_multiplier_swarm_with_no_kills_does_not_latch(self):
        base = self._quiet_room()
        lice = [
            hostile(index, 10, 11, can_multiply=True)
            for index in range(1, 55)
        ]
        fighting = replace(base, visible_monsters=lice)
        policy = HengbotPolicy()

        armed = False
        for _ in range(COMBAT_OUTCOME_WINDOW + 1):
            policy.last_reason = "melee"
            policy._update_combat_outcome(fighting)
            armed = armed or policy.last_reason == "combat:disengage-armed"

        self.assertFalse(armed)
        self.assertTrue(policy._combat_fruitful)
        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_five_breeder_kills_without_growth_do_not_latch(self):
        base = self._quiet_room()
        breeders = [
            hostile(
                index, 10, 11 + index,
                can_multiply=True, max_melee_damage=1,
            )
            for index in range(1, 3)
        ]
        policy = HengbotPolicy()

        for step in range(BREEDER_CONTAINMENT_WINDOW):
            policy.last_reason = "melee"
            fighting = replace(
                base,
                player=replace(base.player, exp=step),
                visible_monsters=breeders,
            )
            policy._update_combat_outcome(fighting)

        self.assertEqual(policy.last_reason, "melee")
        self.assertTrue(policy._combat_fruitful)
        self.assertIsNone(policy._breeder_breakthrough_floor)
        self.assertIsNone(policy._fruitless_disengage_floor)

    def test_breeder_verdict_does_not_rearm_existing_disengage(self):
        base = self._quiet_room()
        fighting = replace(
            base,
            visible_monsters=[hostile(1, 10, 11, can_multiply=True)],
        )
        policy = HengbotPolicy()
        policy._breeder_engagement_floor = base.floor_key
        policy._breeder_engagement_score = BREEDER_CONTAINMENT_WINDOW
        policy._fruitless_disengage_floor = base.floor_key
        policy._fruitless_disengage_decisions = 37
        policy._fruitless_disengage_spent_this_decision = True
        policy.last_reason = "combat:disengage-step"

        policy._update_combat_outcome(fighting)

        self.assertEqual(policy._fruitless_disengage_decisions, 37)
        self.assertEqual(policy.last_reason, "combat:disengage-step")

    def test_fruitless_swarm_disengages_then_leaves_floor(self):
        base = self._quiet_room(upstairs=True)
        louse = hostile(1, 10, 11, can_multiply=True, max_melee_damage=1)
        grids = dict(base.grids)
        grids[Position(10, 11)] = replace(grids[Position(10, 11)], has_monster=True)
        fighting = replace(base, grids=grids, visible_monsters=[louse])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key

        key = policy.choose_key(fighting)
        self.assertEqual(key, "6")
        self.assertIn(
            policy.last_reason,
            {"melee", "no-wait:melee", "combat:disengage-seek-upstairs"},
        )

        clear = replace(
            base,
            player=replace(base.player, position=Position(10, 12)),
            visible_monsters=[],
        )
        self.assertEqual(policy.choose_key(clear), "<")
        self.assertEqual(policy.last_reason, "combat:disengage-ascend")

    def test_fruitless_disengagement_starts_return_before_local_retreat(self):
        recall = item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL)
        base = self._quiet_room(inventory=(recall,))
        naga = hostile(1, 10, 11)
        fighting = replace(base, visible_monsters=[naga])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key
        policy._returning_to_town = True

        key = policy.choose_key(fighting)

        self.assertEqual(key, "rw")
        self.assertEqual(policy.last_reason, "combat:disengage-recall")

    def test_fruitless_disengagement_waits_while_recall_is_active(self):
        base = self._quiet_room()
        fighting = replace(
            base,
            player=replace(base.player, recalling=True),
            visible_monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key
        policy._returning_to_town = True

        key = policy.choose_key(fighting)

        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "combat:disengage-wait-recall")

    def test_fruitless_disengagement_does_not_reread_recall_on_stale_snapshot(self):
        # Live 2026-07-24 regression: the dungeon return latch alternated
        # disengage-recall and disengage-wait-recall at one position, issuing
        # four reads before the process loop detector stopped the bot.  Match
        # the town recall transaction semantics: same-turn redraws and a
        # consumed stack are confirmation states, never permission to reread.
        recall = replace(item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL), count=3)
        base = self._quiet_room(inventory=(recall,))
        fighting = replace(base, visible_monsters=[hostile(1, 10, 11)])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key
        policy._returning_to_town = True

        self.assertEqual(policy.choose_key(fighting), "rw")

        self.assertEqual(policy.choose_key(fighting), WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "combat:disengage-await-recall-confirmation",
        )

        consumed = replace(
            fighting,
            inventory=[replace(recall, count=2)],
            turn=fighting.turn + 8,
        )
        self.assertEqual(policy.choose_key(consumed), WAIT_KEY)
        self.assertEqual(
            policy.last_reason,
            "combat:disengage-await-recall-confirmation",
        )

    def test_fruitless_disengagement_retries_rejected_recall_once(self):
        recall = replace(item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL), count=3)
        base = self._quiet_room(inventory=(recall,))
        fighting = replace(base, visible_monsters=[hostile(1, 10, 11)])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key
        policy._returning_to_town = True

        self.assertEqual(policy.choose_key(fighting), "rw")

        rejected = replace(fighting, turn=fighting.turn + 1)
        self.assertEqual(policy.choose_key(rejected), "rw")
        self.assertEqual(policy.last_reason, "combat:disengage-recall")

    def test_blocked_fruitless_disengagement_reaches_visible_stop(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = snapshot.floor_key
        policy._fruitless_disengage_decisions = 100

        self.assertEqual(policy.choose_key(snapshot), "5")
        self.assertEqual(policy.last_reason, "combat:fruitless")

    def test_finished_swarm_allowance_decays_before_fresh_warg_fight(self):
        base = self._quiet_room()
        worms = [
            hostile(
                index,
                10,
                11,
                can_multiply=True,
                race_id=79,
            )
            for index in range(1, 91)
        ]
        swarm = replace(base, visible_monsters=worms)
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = base.floor_key

        for _ in range(FRUITLESS_DISENGAGE_LIMIT - 4):
            policy.choose_key(swarm)
            self.assertNotEqual(policy.last_reason, "combat:fruitless")

        for _ in range(4):
            policy.choose_key(base)
        self.assertLess(
            policy._fruitless_disengage_decisions,
            FRUITLESS_DISENGAGE_LIMIT - 4,
        )

        warg = replace(
            base,
            visible_monsters=[hostile(257, 10, 11, race_id=257)],
        )
        for _ in range(2):
            policy.choose_key(warg)
            self.assertNotEqual(policy.last_reason, "combat:fruitless")

    def test_brief_contact_break_does_not_forgive_nearly_overrun_swarm(self):
        base = self._quiet_room()
        worm = hostile(
            1, 10, 11, can_multiply=True, race_id=79, max_melee_damage=1
        )
        swarm = replace(base, visible_monsters=[worm])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = base.floor_key
        policy._fruitless_disengage_decisions = FRUITLESS_DISENGAGE_LIMIT - 1

        policy.choose_key(base)
        policy.choose_key(base)

        decisions = []
        for _ in range(
            BREEDER_CONTAINMENT_WINDOW + FRUITLESS_DISENGAGE_LIMIT + 10
        ):
            decisions.append(policy.choose_key(swarm))
            if policy.last_reason == "combat:fruitless":
                break

        self.assertTrue(decisions)
        self.assertGreaterEqual(
            policy._fruitless_disengage_decisions,
            FRUITLESS_DISENGAGE_LIMIT - 4,
        )

    def test_continuous_fruitless_engagement_still_terminates(self):
        base = self._quiet_room()
        worm = hostile(
            1, 10, 11, can_multiply=True, race_id=79, max_melee_damage=1
        )
        swarm = replace(base, visible_monsters=[worm])
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = base.floor_key

        decisions = [
            policy.choose_key(swarm)
            for _ in range(
                BREEDER_CONTAINMENT_WINDOW + FRUITLESS_DISENGAGE_LIMIT + 1
            )
        ]

        self.assertTrue(decisions)
        self.assertGreaterEqual(
            policy._fruitless_disengage_decisions,
            FRUITLESS_DISENGAGE_LIMIT - 4,
        )

    def test_continuous_nonbreeder_disengagement_still_terminates(self):
        base = self._quiet_room()
        swarm = replace(
            base,
            visible_monsters=[
                hostile(index, 10, 11, race_id=257)
                for index in range(1, 91)
            ],
        )
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = base.floor_key

        decisions = [
            policy.choose_key(swarm)
            for _ in range(FRUITLESS_DISENGAGE_LIMIT + 1)
        ]

        self.assertEqual(decisions[-1], WAIT_KEY)
        self.assertEqual(policy.last_reason, "combat:fruitless")

    def test_fruitless_swarm_never_abandons_random_quest_floor(self):
        base = self._quiet_room(upstairs=True)
        louse = hostile(1, 10, 11, can_multiply=True, max_melee_damage=1)
        grids = dict(base.grids)
        grids[Position(10, 11)] = replace(
            grids[Position(10, 11)], has_monster=True
        )
        fighting = replace(
            base,
            floor_key=(1, 6, 40),
            grids=grids,
            visible_monsters=[louse],
        )
        recall = item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL)
        fighting = replace(fighting, inventory=(recall,))
        policy = HengbotPolicy()
        policy._fruitless_disengage_floor = fighting.floor_key
        # Arm the state exactly as the live fruitless latch does: the combat
        # verdict also forces the town return. Without this the escape path
        # never even starts, and the test cannot distinguish guarded from
        # unguarded code (revert-proof caught it passing on the old policy).
        policy._returning_to_town = True

        decisions = [
            policy.choose_key(fighting)
            for _ in range(
                BREEDER_CONTAINMENT_WINDOW + FRUITLESS_DISENGAGE_LIMIT + 1
            )
        ]

        self.assertFalse(
            {"<", ">"}.intersection(decisions)
            or any(key.startswith("r") for key in decisions),
            f"quest floor was abandoned: {sorted(set(decisions))}",
        )
        self.assertGreaterEqual(
            policy._fruitless_disengage_decisions,
            FRUITLESS_DISENGAGE_LIMIT - 4,
        )

    def test_quest_disengage_continues_objective_after_breaking_contact(self):
        # Fixed quests entered through dungeon travel retain quest_id=0 in the
        # emitted floor key, as in the live Warg Quest incident.
        snapshot = replace(self._quiet_room(), floor_key=(2, 5, 0))
        policy = HengbotPolicy()
        policy._active_fixed_quest_id = lambda _snapshot: 2
        policy._fruitless_disengage_floor = snapshot.floor_key
        policy._fruitless_disengage_decisions = 17
        policy._returning_to_town = True

        key = policy.choose_key(snapshot)

        self.assertNotEqual(key, "5")
        self.assertFalse(policy.last_reason.startswith("combat:disengage"))
        self.assertEqual(policy._fruitless_disengage_decisions, 13)

    def test_normal_fight_is_unchanged_without_disengage_latch(self):
        base = self._quiet_room()
        fighting = replace(base, visible_monsters=[hostile(1, 10, 11)])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(fighting), "6")
        self.assertEqual(policy.last_reason, "melee")

    def test_hostile_count_or_experience_progress_prevents_fruitless_stop(self):
        base = self._quiet_room()
        policy = HengbotPolicy()
        many = replace(
            base,
            visible_monsters=[hostile(index, 10, 11) for index in range(1, 5)],
        )
        fewer = replace(many, visible_monsters=many.visible_monsters[:2])
        opening_quarter = (COMBAT_OUTCOME_WINDOW + 1) // 4
        for step in range(COMBAT_OUTCOME_WINDOW + 1):
            policy.last_reason = "melee"
            policy._update_combat_outcome(many if step < opening_quarter else fewer)
        self.assertNotEqual(policy.last_reason, "combat:fruitless")

        policy = HengbotPolicy()
        gained = replace(base, player=replace(base.player, exp=1))
        for step in range(COMBAT_OUTCOME_WINDOW + 1):
            policy.last_reason = "melee"
            policy._update_combat_outcome(gained if step else base)
        self.assertNotEqual(policy.last_reason, "combat:fruitless")

    def test_long_non_unique_fight_with_falling_hp_is_not_fruitless(self):
        base = self._quiet_room()
        tank = hostile(1, 10, 11, hp=100, max_hp=100)
        policy = HengbotPolicy()
        for step in range(COMBAT_OUTCOME_WINDOW + 1):
            policy.last_reason = "melee"
            monster = replace(tank, hp=max(1, 100 - step // 4))
            policy._update_combat_outcome(replace(base, visible_monsters=[monster]))
        self.assertNotEqual(policy.last_reason, "combat:fruitless")

    def test_combat_adjacent_reasons_do_not_reset_or_extend_window(self):
        fighting = replace(
            self._quiet_room(), visible_monsters=[hostile(1, 10, 11)]
        )
        policy = HengbotPolicy()
        policy.last_reason = "melee"
        policy._update_combat_outcome(fighting)
        recorded = len(policy._combat_outcomes)

        for reason in (
            "fundraise:eliminate-multiplier",
            "fundraise:clear-hostile",
            "fundraise:pickup",
        ):
            policy.last_reason = reason
            policy._update_combat_outcome(fighting)
            self.assertEqual(len(policy._combat_outcomes), recorded)

        policy.last_reason = "melee"
        policy._update_combat_outcome(fighting)
        self.assertEqual(len(policy._combat_outcomes), recorded + 1)

    def test_fruitless_combat_no_longer_resets_navigation_invariant(self):
        snapshot = replace(
            self._quiet_room(), visible_monsters=[hostile(1, 10, 11, can_multiply=True)]
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._nav_progress_marker = (
            snapshot.player.gold,
            len(snapshot.inventory),
            len(snapshot.equipment),
        )
        policy._nav_known_high = len(policy._remembered_known_t)
        policy._combat_fruitful = False
        policy.last_reason = "combat:fruitless"
        policy._nav_stall_count = NAV_NO_PROGRESS_LIMIT - 1

        policy._update_navigation_progress(snapshot)

        self.assertTrue(policy._nav_exhausted)


    def test_exhausted_floor_reads_a_recall_scroll(self):
        recall = item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = self._quiet_room(inventory=[recall])
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        self.assertEqual(policy.choose_key(snapshot), "rw")
        self.assertEqual(policy.last_reason, "livelock:recall-escape")

    def test_exhausted_floor_seeks_upstairs_without_a_scroll(self):
        snapshot = self._quiet_room(upstairs=True)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "livelock:seek-upstairs")

    def test_exhausted_return_teleports_to_resume_exploration(self):
        teleport = item("t", SCROLL, SV_SCROLL_TELEPORT, count=12)
        snapshot = self._quiet_room(inventory=[teleport])
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._returning_to_town = True
        policy._nav_exhausted = True

        self.assertEqual(policy.choose_key(snapshot), "rt")
        self.assertEqual(policy.last_reason, "livelock:teleport-explore")
        self.assertFalse(policy._nav_exhausted)

    def test_exhausted_return_preserves_last_emergency_teleport(self):
        teleport = item("t", SCROLL, SV_SCROLL_TELEPORT, count=1)
        snapshot = self._quiet_room(inventory=[teleport])
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._returning_to_town = True
        policy._nav_exhausted = True

        self.assertEqual(policy.choose_key(snapshot), WAIT_KEY)
        self.assertEqual(policy.last_reason, "livelock:exhausted")

    def test_exhausted_floor_with_no_escape_stops_visibly(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        key = policy.choose_key(snapshot)
        # The pocket has a frontier, but exhaustion means those modes already
        # failed for the whole budget — the policy must surface the livelock
        # (the CLI stops on this reason) instead of resuming the cycle.
        if policy.last_reason == "livelock:exhausted":
            self.assertEqual(key, WAIT_KEY)
        else:
            # An up-stairs-free pocket without a scroll may legitimately still
            # explore its frontier once; the invariant then re-trips. Drive a
            # few more decisions and require the visible stop to appear.
            for _ in range(5):
                policy._nav_exhausted = True
                key = policy.choose_key(snapshot)
                if policy.last_reason == "livelock:exhausted":
                    break
            self.assertEqual(policy.last_reason, "livelock:exhausted")
            self.assertEqual(key, WAIT_KEY)

    def test_real_exploration_giveup_relocates_to_western_window_edge(self):
        row = json.loads(
            next(
                line
                for line in self.GIVEUP_CAPTURE.read_text(
                    encoding="utf-8-sig"
                ).splitlines()
                if line.strip()
            )
        )
        snapshot = parse_snapshot(row)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        policy._window_edge_fallback_pending = True

        key = policy.choose_key(snapshot)

        reachable_edges = {
            Position(y, x)
            for y, x in (
                (11, 67), (12, 68), (13, 75), (16, 66), (16, 75),
                (20, 71), (21, 73), (22, 73), (23, 73), (24, 73),
                (25, 73), (26, 75), (27, 73), (27, 75),
            )
        }
        self.assertEqual(policy.last_reason, "livelock:seek-window-edge")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertIn(policy._explore_path[-1], reachable_edges)
        self.assertLess(policy._explore_path[-1].x, snapshot.player.position.x)

    def test_window_edge_replay_reaches_new_coverage_and_resets_stall(self):
        row = json.loads(
            next(
                line
                for line in self.GIVEUP_CAPTURE.read_text(
                    encoding="utf-8-sig"
                ).splitlines()
                if line.strip()
            )
        )
        snapshot = parse_snapshot(row)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        policy._window_edge_fallback_pending = True
        policy.choose_key(snapshot)
        route = list(policy._explore_path)
        goal = route[-1]

        for position in route:
            moved = replace(
                snapshot,
                player=replace(snapshot.player, position=position),
            )
            policy.choose_key(moved)

        shifted_grids = dict(snapshot.grids)
        shifted_grids[Position(goal.y, goal.x - 1)] = grid(
            goal.y, goal.x - 1
        )
        shifted = replace(
            snapshot,
            player=replace(snapshot.player, position=goal),
            grids=shifted_grids,
        )
        policy._nav_stall_count = NAV_NO_PROGRESS_LIMIT - 1
        policy.choose_key(shifted)

        self.assertEqual(goal, Position(16, 66))
        self.assertEqual(policy._nav_stall_count, 0)
        self.assertFalse(policy._nav_exhausted)
        self.assertIn((goal.y, goal.x - 1), policy._remembered_known_t)

    def test_enclosed_window_edge_goals_are_deduplicated_then_terminal(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        policy._window_edge_fallback_pending = True
        policy.choose_key(snapshot)
        first_goal = next(iter(policy._window_edge_goals))

        policy._window_edge_goals.update(
            position
            for position, cell in snapshot.grids.items()
            if cell.passable
        )
        policy._nav_exhausted = True
        policy._window_edge_fallback_pending = True
        key = policy.choose_key(snapshot)

        self.assertIn(first_goal, policy._window_edge_goals)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "livelock:exhausted")


class StarvationStopTest(unittest.TestCase):
    def test_town_death_cycle_trips_within_the_budget(self):
        reasons = ("town:seek-shelter", "town:recover", "shop:leave")
        streak = 0
        for decision in range(STARVING_STOP_LIMIT):
            streak = _advance_starving_streak(
                streak,
                food_state="fainting",
                has_edible=False,
                reason=reasons[decision % len(reasons)],
                position_changed=True,
            )
        self.assertEqual(streak, STARVING_STOP_LIMIT)

    def test_advancing_survival_return_is_exempt(self):
        self.assertEqual(
            _advance_starving_streak(
                20,
                food_state="weak",
                has_edible=False,
                reason="return:seek-upstairs",
                position_changed=True,
            ),
            0,
        )

    def test_stationary_recall_wait_while_weak_is_exempt(self):
        self.assertEqual(
            _advance_starving_streak(
                20,
                food_state="weak",
                has_edible=False,
                reason="return:wait-recall",
                position_changed=False,
            ),
            0,
        )


class SurvivalGateTest(unittest.TestCase):
    def _dungeon(self, *, food, inventory=(), grids=None, monsters=()):
        cells = grids or {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
        }
        return Snapshot(
            player(10, 10, food=food),
            cells,
            list(monsters),
            floor_key=(2, 3, 0),
            width=40,
            height=40,
            inventory=list(inventory),
        )

    def test_hungry_with_food_eats_even_with_a_descent_target_known(self):
        # Pre-R1, a known downstairs made step 6 return before the eat step —
        # the "eat is dead while descending" hole behind the starvation death.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        snap = self._dungeon(
            food=1500, inventory=[item("b", FOOD, 35)], grids=grids
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "Eb")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_starving_with_no_food_overrides_mining_mode(self):
        snap = self._dungeon(food=800)  # "weak", empty pack
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy.choose_key(snap)
        self.assertEqual(policy._last_return_trigger, "food-hungry")
        self.assertTrue(policy.last_reason.startswith("return:"))
        self.assertTrue(policy._returning_to_town)

    def test_well_fed_mining_run_never_triggers_the_survival_path(self):
        # A kitless miner may still be sent home by fundraising's OWN return
        # policy — that is pre-existing behaviour. What the gate must never do
        # is claim a well-fed character is starving.
        snap = self._dungeon(food=12000)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("survival:"))
        self.assertNotEqual(policy._last_return_trigger, "food-hungry")

    def test_gate_defers_to_combat_unless_fainting(self):
        snap = self._dungeon(
            food=1500,
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "melee")

    def test_survival_gate_uses_player_fainting_property_near_hostiles(self):
        snap = self._dungeon(
            food=1500,
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()

        self.assertIsNone(
            policy._survival_gate_key(snap, list(snap.visible_monsters))
        )

    def test_gate_eats_mid_combat_when_fainting(self):
        snap = self._dungeon(
            food=100,  # fainting
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()
        key = policy.choose_key(snap)
        # The emergency-item step (step 0) may claim the fainting case first;
        # either path must put food in the character's mouth this turn.
        self.assertIn("E", key)

    def test_gate_ignores_a_distant_spectator_monster(self):
        # A hostile merely visible across the floor must not indefinitely
        # defer eating — only a NEARBY threat does.
        snap = self._dungeon(
            food=1500,
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 20, distance=10)],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "Eb")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_weak_with_no_food_leaves_a_kill_quest_floor(self):
        # Starvation kills through paralysis with HP untouched, so the
        # kill-quest exit lock's HP panic release never fires. Weak-or-worse
        # with nothing edible must release the lock and walk out via the
        # exit stairs, visibly accepting the quest loss.
        from hengbot.quest_knowledge import QuestInfo
        from hengbot.model import QuestState

        info = QuestInfo(14, "Warg problem", 5, 5, 0, num_mon=16)
        quest = QuestState(
            id=14, status=1, type=5, cur_num=2, num_mon=16, max_num=0,
        )
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8, upstairs=True),
        }
        snap = Snapshot(
            player(10, 10, food=800),  # weak, empty pack
            grids,
            [],
            floor_key=(0, 5, 14),
            width=40,
            height=40,
            quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy.choose_key(snap)
        self.assertIn(
            policy.last_reason,
            {"survival:seek-exit", "survival:stairs-quest-fail",
             "survival:ascend", "return:ascend", "return:seek-upstairs"},
        )

    def test_merely_hungry_keeps_working_a_locked_quest_floor(self):
        from hengbot.quest_knowledge import QuestInfo
        from hengbot.model import QuestState

        info = QuestInfo(14, "Warg problem", 5, 5, 0, num_mon=16)
        quest = QuestState(
            id=14, status=1, type=5, cur_num=2, num_mon=16, max_num=0,
        )
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8, upstairs=True),
        }
        snap = Snapshot(
            player(10, 10, food=1500),  # hungry but not yet weak
            grids,
            [],
            floor_key=(0, 5, 14),
            width=40,
            height=40,
            quests={14: quest},
            inventory=[item("t", SCROLL, SV_SCROLL_TELEPORT)],
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("survival:"))
        self.assertFalse(policy.last_reason.startswith("return:"))


if __name__ == "__main__":
    unittest.main()
