"""n1-c life-217, Quest 33 段2 (2026-11-19 23:52): the lure worked, then the sweep stopped by name.

The resumed process (tests/fixtures/n1c-217-q33-open-path-1119.json.gz, extracted by
tests/extract_n1c_217_q33_open_path_1119_fixture.py from C:/hengband-backups/pdca/captures/
n1c-217-q33-lure3-1119) walked from [20,48] to the start [21,48], the Gachapins came out of their room,
it stepped back out of the Queens' range to [26,41] and shot: one Gachapin died (「『ガチャピン』は死んだ。」),
its fire ball burnt the trees of the band (「木は燃えた。」).  The next board stopped the bot with
quest:blocked:sweep-nothing-comes: another Gachapin stood seen at [27,53], 12 away (the plan's shot
reaches 10, policy_constants RANGED_MAX_DISTANCE), on a brake where a tree had been.  The reader said
it did not act on the player: its line crossed the band's trees as the quest map has them, while the
game had burnt them (effect-feature.cpp affect_feature: TREE -> GRASS, or BRAKE one time in three).

Now: a monster the player sees from where he stands acts (decide_process_continue's ``has_los_at``),
and the map the reader and the lines use is the board's where a tree is burnt or a wall melted
(quest_alignment_split ``board_terrain``): that Gachapin comes and the plan waits for it.

Owner 2026-11-19 (verbatim), for a lure with no cell a Gachapin walks to: 「壁を溶かして道を作る。邪魔なら
木もファイアボルトなどで燃やして良い」 (quest_lure_approach ``_open_way``).  On the first board, with every
cell the Gachapins come to spent (DECLARED CONSTRUCTED below), the fewest openings are one wall: the
granite [24,56] at the corner of the Gachapins' room, the cell south-west of [23,57] that sent the
Gachapin back and forth; melted, its walk leads to the player.  The player walks to a cell out of every
Queen's line of fire from which Stone to Mud's ray meets that wall, and melts it.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``),
which holds the Stone to Mud and fire powers absorbed; the kill lines of the Its, Dagons and Bokrugs
are set on the navigator (the seeded restart record held them); for the opening the navigator holds
every lure start of the first board as spent, and the player is put on the opening's origin.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import (
    quest_alignment_split,
    quest_lure_approach,
    quest_plan_base,
    quest_room_sweep,
    quest_wait_placement,
)
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, GACHAPIN, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-open-path-1119.json.gz"
KILLS = {IT: 3, DAGON: 3, BOKRUG: 3}
WALL = (24, 56)


class N1c217Q33OpenPathTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.paths = []
        original = quest_plan_base._path_step

        def recording(policy, snapshot, path, reason):
            self.paths.append([(cell.y, cell.x) for cell in path])
            return original(policy, snapshot, path, reason)

        quest_plan_base._path_step = recording
        self.addCleanup(setattr, quest_plan_base, "_path_step", original)

    def board(self, raw, cell=None):
        raw = copy.deepcopy(raw)
        if cell is not None:
            raw["player"]["y"], raw["player"]["x"] = cell
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.split_kills = dict(KILLS)
        return snapshot, navigator

    def test_the_recorded_run(self):
        reasons = [run["reason"] for run in self.case["runs"]]
        self.assertIn(quest_lure_approach.LURE_WALK_REASON, reasons)
        self.assertIn(quest_lure_approach.LURE_BACK_REASON, reasons)
        self.assertEqual(reasons[-1], quest_room_sweep.NOTHING_COMES_REASON)
        self.assertTrue(any("木は燃えた" in message for run in self.case["runs"] for message in run["messages"]))
        snapshot, _navigator_ = self.board(self.case["last"])
        seen = [m for m in snapshot.visible_monsters if m.race_id == GACHAPIN]
        self.assertEqual([(m.position.y, m.position.x) for m in seen], [(27, 53)])
        self.assertEqual(snapshot.player.position.distance_to(seen[0].position), 12)

    def test_the_seen_gachapin_comes_and_is_waited_for(self):
        snapshot, navigator = self.board(self.case["last"])
        terrain = quest_alignment_split.board_terrain(navigator, snapshot)
        self.assertEqual(navigator.battlefield.terrain[(27, 53)], "tree")
        self.assertEqual(terrain[(27, 53)], "floor")  # burnt to a brake
        read = quest_wait_placement.reader(self.policy, snapshot, navigator, self.plan)
        row = next(row for row in read.rows if row.cell == (27, 53))
        here = (snapshot.player.position.y, snapshot.player.position.x)
        self.assertTrue(read.acts(row, here))
        self.assertTrue(read.comes(row, here))
        quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, quest_plan_base.HOLD_REASON)

    def spent_starts(self, snapshot, navigator):
        read = quest_wait_placement.reader(self.policy, snapshot, navigator, self.plan)
        lure = quest_lure_approach._rows(self.policy, snapshot, navigator, self.plan, read, [GACHAPIN])
        queens = quest_lure_approach._rows(self.policy, snapshot, navigator, self.plan, read, [QUEEN])
        taken = quest_lure_approach._taken(self.policy, snapshot, navigator, self.plan, read, queens)
        here = (snapshot.player.position.y, snapshot.player.position.x)
        seen = quest_lure_approach._walk_from(navigator, snapshot, here, taken)
        return read, lure, queens, frozenset(
            cell for cell in seen if navigator.battlefield.terrain.get(cell) in quest_lure_approach._STAND
            and any(read.comes(row, cell) for row in lure))

    def test_with_no_start_the_wall_that_turns_the_gachapin_is_melted(self):
        snapshot, navigator = self.board(self.case["board"])
        read, lure, queens, starts = self.spent_starts(snapshot, navigator)
        self.assertTrue(starts)
        navigator.lure_spent = starts
        quest_room_sweep.walk_key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, quest_lure_approach.OPEN_WALK_REASON)
        origin = self.paths[-1][-1]
        self.assertFalse(any(quest_lure_approach._line_of_fire(read, row, origin) for row in queens))
        self.assertTrue(quest_lure_approach._reaches(self.policy, snapshot, read, origin, WALL, False))
        # The wall turned the Gachapin at [23,57]: opened, its walk leads on.
        mover = next(row for row in lure if row.cell == (23, 56))
        self.assertEqual(quest_lure_approach._openings(self.policy, snapshot, navigator, read, mover, (22, 47),
                                                       False, True), [WALL])
        there, navigator = self.board(self.case["board"], origin)
        navigator.lure_spent = starts
        quest_room_sweep.walk_key(self.policy, there)
        self.assertTrue(self.policy.last_reason.startswith(quest_lure_approach.OPEN_MELT_REASON))
        self.assertEqual(dict(navigator.open_tries), {WALL: 1})

    def test_a_tree_is_burnt_with_a_fire_power(self):
        snapshot, _navigator_ = self.board(self.case["board"])
        self.assertTrue(quest_lure_approach._can_burn(self.policy, snapshot))
        key = quest_lure_approach._fire_key(self.policy, snapshot, (24, 51))
        self.assertTrue(key.endswith("@24,51"))
        self.assertEqual(self.policy.last_reason, quest_lure_approach.OPEN_BURN_REASON)


if __name__ == "__main__":
    unittest.main()
