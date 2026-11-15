"""n1-c life-214 2026-11-15: with no landing to fall back to, the Mountain is dived to 29F.

Owner (verbatim), asked what to do when the over-extension switch finds no landing: 「想定は城か
山。城29F、山29Fをターゲットにして、浅いところから潜って辿り着く。」  n1-c (Lv38 Magic-Eater) was
over-extended at Angband 49F; the fallback depth floor is 29 (the deepest reached 49 less 20,
owner 2026-11-13) and the only entered landing in 29-48 is the Chameleon cave 30, never a
fallback (owner 2026-11-11 「絶対に入れない」).  The valve fired at 16:12:38 (d73, under the
kept-haul rule) and at 16:53:36 (d100) and changed nothing.  Now it switches to the Mountain
(landing 25, the deeper of the Mountain 25 and the Castle 20) with the target 29F; the descent
does not pass 29 there (``dive_floor.capped``).

Recorded: tests/fixtures/n1c-214-overextend-1115 (tests/extract_n1c_214_overextend_1115_fixture.py)
-- the 17:07 town-arrival checkpoint and the packs of the 16:00-16:18 and 16:50-16:53 Angband 49F
dives -- replayed as tests/test_n1c_214_overextend_1115_recorded.py does (its DECLARED
construction).  DECLARED CONSTRUCTED: the Mountain boards of the next dive are the recorded 49F
board moved to the Mountain at the depth asked, the player on a downstairs.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import alternate_dungeon_record, alternate_lease, dive_floor, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_CHAMELEON_CAVE, parse_snapshot
from tests.test_n1c_214_overextend_1115_recorded import N1c214Dives

MOUNTAIN, CASTLE = dive_floor.DUNGEON_MOUNTAIN, dive_floor.DUNGEON_CASTLE


class DiveFloorTest(N1c214Dives):
    def run_dives(self, names):
        streaks = []
        for name in names:
            # DECLARED: the no-depth-progress valve (its own test below) kept out of the
            # over-extension replay: none of these recorded Angband dives went deeper.
            self.policy._no_depth_progress_dives = 0
            arrival = self.dive(name)
            streaks.append((name, self.policy._target_empty_dives))
        return arrival, streaks

    def mountain_board(self, level):
        """DECLARED CONSTRUCTED: the recorded 49F board in the Mountain at ``level``, the player
        on a downstairs."""
        raw = copy.deepcopy(self.dives["template"])
        raw["floor"] = {**raw["floor"], "dungeon_id": MOUNTAIN, "level": level,
                        "dungeon_name": "山"}
        raw["turn"] += 2_000_000
        board = parse_snapshot(raw, self.policy._monrace_knowledge)
        here = board.player.position
        grids = dict(board.grids)
        grids[here] = replace(grids[here], has_down_stairs=True, has_up_stairs=False)
        return replace(board, grids=grids), grids[here]

    def assert_dived_to_the_mountain(self, arrival, reason="over_extended_dives"):
        policy = self.policy
        self.assertEqual(fallback_depth_floor.floor(policy, arrival), 29)
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason,
                          dive_floor.target(policy)), (MOUNTAIN, reason, 29))
        self.assertEqual(policy._target_dungeon_id, MOUNTAIN)
        self.assertEqual(policy._alternate_lease, alternate_lease.FIRST_LEASE)
        self.assertEqual(arrival.dungeon_recall_depths[MOUNTAIN], 25)
        self.assertEqual(policy._dungeon_entry_depth(arrival, MOUNTAIN, via_recall=True), 25)

    def test_1612_the_valve_dives_the_mountain_to_29(self):
        arrival, streaks = self.run_dives(["d64", "d65", "d66", "d67", "d73"])
        self.assertEqual(self.dives["d73"]["time"], "2026-11-15T16:12:38+0900")
        self.assertEqual(streaks[-2:], [("d67", 2), ("d73", 0)])
        # Unfixed (11-15 kept-haul rule): no landing, the alternate stays None.
        self.assert_dived_to_the_mountain(arrival)
        self.assertEqual(policy_landings(arrival), {CASTLE: 20, MOUNTAIN: 25, DUNGEON_CHAMELEON_CAVE: 30})

    def test_1653_the_valve_dives_the_mountain_to_29(self):
        arrival, streaks = self.run_dives(["d94", "d95", "d96", "d97", "d98", "d99", "d100"])
        self.assertEqual(self.dives["d100"]["time"], "2026-11-15T16:53:36+0900")
        self.assertEqual([self.dives[name]["escapes"] for name, _ in streaks], [0, 1, 8, 2, 0, 0, 2])
        self.assertEqual(streaks, [("d94", 0), ("d95", 0), ("d96", 1), ("d97", 2), ("d98", 2),
                                   ("d99", 2), ("d100", 0)])
        self.assert_dived_to_the_mountain(arrival)

    def test_the_castle_when_the_mountain_is_the_one_left(self):
        arrival, _streaks = self.run_dives(["d64", "d65", "d66", "d67", "d73"])
        policy = self.policy
        # The step down from the Mountain: the Castle 20 reaches 29 (its depth is 20-65).
        self.assertEqual(dive_floor.pick(policy, arrival, too_hard=49), CASTLE)
        self.assertEqual(policy._dungeon_knowledge[CASTLE].max_depth, 65)
        # Control: the target is never the depth that was too hard or deeper.
        self.assertIsNone(dive_floor.pick(policy, arrival, too_hard=29))

    def test_the_next_dive_descends_to_29_and_no_further(self):
        self.run_dives(["d64", "d65", "d66", "d67", "d73"])
        policy = self.policy
        for level in (25, 26, 27, 28):
            board, stair = self.mountain_board(level)
            self.assertTrue(policy._is_descent_target(board, stair), level)
        board, stair = self.mountain_board(29)
        self.assertFalse(policy._is_descent_target(board, stair))
        self.assertTrue(dive_floor.capped(policy, board, 30))
        # Unfixed: nothing stops the Mountain's 30F (its requirements are those of 29F).
        self.assertEqual(policy._missing_required_abilities(board, 30), frozenset())

    def test_control_without_the_target_the_mountain_goes_deeper(self):
        self.run_dives(["d64", "d65", "d66", "d67", "d73"])
        # DECLARED: the switch held without a dive to the floor (a landing switch).
        self.policy._alternate_dive_floor = None
        board, stair = self.mountain_board(29)
        self.assertTrue(self.policy._is_descent_target(board, stair))

    def test_the_no_depth_progress_valve_dives_the_mountain_too(self):
        # 16:50-16:52: five Angband dives without depth progress (the count from 0).
        for name in ["d94", "d95", "d96", "d97", "d98"]:
            arrival = self.dive(name)
        self.assertEqual(self.policy._target_empty_dives, 2)
        self.assert_dived_to_the_mountain(arrival, reason="no_depth_progress")

    def test_the_target_is_carried_across_a_restart(self):
        arrival, _streaks = self.run_dives(["d64", "d65", "d66", "d67", "d73"])
        policy = self.policy
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy._alternate_dungeon_record_path = Path(scratch.name) / "alternate-dungeon.json"
        alternate_dungeon_record.record(policy, arrival, force=True)
        # DECLARED: a fresh process holds neither the switch nor its target.
        policy._alternate_dungeon = policy._alternate_dungeon_reason = None
        policy._alternate_dive_floor = None
        alternate_dungeon_record.restore(policy, arrival)
        self.assertEqual((policy._alternate_dungeon, dive_floor.target(policy)), (MOUNTAIN, 29))
        # The depth floor does not end the switch whose target is at it.
        self.assertFalse(fallback_depth_floor.settle(policy, arrival))
        self.assertEqual(policy._alternate_dungeon, MOUNTAIN)
        self.assertNotEqual(policy._alternate_dungeon, DUNGEON_ANGBAND)


def policy_landings(board):
    return {did: depth for did, depth in board.dungeon_recall_depths.items()
            if did in (CASTLE, MOUNTAIN, DUNGEON_CHAMELEON_CAVE)}


if __name__ == "__main__":
    import unittest
    unittest.main()
