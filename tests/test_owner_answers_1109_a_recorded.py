"""Owner answers of 2026-11-09 to questions 1 and 2 of town-stops-1109b.

1. 「最後の位置の周りを避ける」(麻痺させる敵から離れた時も、見えなくなった敵の最後の位置の周りを避ける
   マスに入れ、歩きで近づかない): n1-b life-346 (Magic-Eater Lv29, Angband 18F, 2026-11-08 10:51,
   build bot-15049b9; tests/fixtures/stops-1109-dungeon/l1-346).  Since owner E of deaths-1109
   the awake ゲイザー (race 218, HOLD) in sight is left on the 09-18 rung, which latched nothing,
   so out of sight its last cell vetoed no route: on the counterfactual walk below the descent
   walk stepped back beside that cell (distance 1, inside the window).  Now the 09-18 rung's
   leave marks the paralyser (sleeper_reach_memory.note_paralyser_left) and out of sight its
   last cell is judged as a latched status threat's for the memory's window.

2. Owner 「直して預け戻さない」(整理のために出した品は鑑定の取り出しと区別し、預け戻さずに売りに行く) is
   pinned in tests/test_town_stops_1109b_recorded.py (JunkSweepTakeAtEntranceTest).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import sleeper_reach_memory
from hengbot.model import Position, parse_snapshot
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS
from tests.test_dungeon_1031_recorded import RecordedHarness, decide
from tests import test_stops_1109_dungeon_recorded as stops
from tests.test_stops_1109_dungeon_recorded import GAZER, MOVES, here, step

GAZER_LAST = Position(25, 20)  # the last board that showed it (1301140)


class LeftParalyserLastCellRecordedTest(RecordedHarness):
    drive_346 = stops.AwakeThreatOutOfSightRecordedTest.drive_346

    def out_of_sight(self):
        """The recorded board 1301148 after the 09-18 rung answered the gazer in sight."""
        policy, raw = self.drive_346()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(snapshot.visible_monsters, [])
        (gazer,) = sleeper_reach_memory.remembered(policy, snapshot)
        self.assertEqual(((gazer.index, gazer.race_id), gazer.position), (GAZER, GAZER_LAST))
        # The real producer: the 09-18 rung's read ('rh', status-threat:scroll) marked it.
        self.assertTrue(sleeper_reach_memory.paralyser_left(policy, snapshot, gazer))
        self.assertFalse(sleeper_reach_memory.status_latched(policy, snapshot, gazer))
        return policy, raw

    def test_the_walks_keep_off_the_last_cell_out_of_sight(self):
        policy, raw = self.out_of_sight()
        start = raw["turn"]
        nearest = here(raw).distance_to(GAZER_LAST)
        self.assertEqual(nearest, 4)
        walked, reasons = [], []
        # DECLARED COUNTERFACTUAL (as in test_stops_1109_dungeon_recorded): the player follows
        # the decided moves with the gazer out of sight, ten game turns a decision, for 200
        # game turns of the window.
        while raw["turn"] - start <= 200:
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = decide(policy, copy.deepcopy(raw))
            reasons.append(policy.last_reason)
            if raw["turn"] == start:
                first_veto = policy._engagement_route_veto(snapshot)
            if key:
                policy.confirm_key_posted(key)
            if key in MOVES:
                moved = step(raw, key)
                walked.append((raw["turn"] - start, policy.last_reason, moved.distance_to(GAZER_LAST)))
                raw["player"]["y"], raw["player"]["x"] = moved.y, moved.x
            raw["turn"] += 10
            raw["messages"] = []
        self.assertIn("approach-descent", reasons)
        # Before: ('1', 'approach-descent') to (26,20) at +140, beside the last cell.
        self.assertTrue(walked)
        self.assertGreaterEqual(min(distance for _turn, _reason, distance in walked), nearest, walked)
        # The ring around the last cell is in the walks' veto.
        self.assertTrue({Position(GAZER_LAST.y + dy, GAZER_LAST.x + dx)
                         for dy in (-1, 0, 1) for dx in (-1, 0, 1)} <= first_veto)

    def test_the_last_cell_is_released_with_the_memory_window(self):
        policy, raw = self.out_of_sight()
        _floor, seen = policy._sleeper_reach_memory
        shown = seen[GAZER][1]
        decide(policy, copy.deepcopy(raw))
        raw["turn"] = shown + UNSEEN_GAME_TURNS + 1
        raw["messages"] = []
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        decide(policy, copy.deepcopy(raw))
        self.assertEqual(sleeper_reach_memory.remembered(policy, snapshot), [])
        self.assertNotIn(GAZER_LAST, policy._engagement_route_veto(snapshot))


if __name__ == "__main__":
    unittest.main()
