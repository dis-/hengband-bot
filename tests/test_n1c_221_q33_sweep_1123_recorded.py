"""n1-c life-221, Quest 33 (2026-11-23 12:56-13:00): the sweep stopped by name with the floor not looked over.

Recorded (tests/fixtures/n1c-221-q33-sweep-1123, extracted by tests/extract_n1c_221_q33_sweep_1123_fixture.py
from the server capture 20261123-130004-quest-blocked-sweep-nothing-comes, bot main 57a80bc0a).  The room
sweep's kill lines (quest_alignment_split ``split_kills``, the restart record sweep-kills.json) credited
It 393 x2, Bokrug 489 x2 and Dagon 595 x3.  The third It and the third Bokrug died unnamed: 「何かは死んだ。」
at 4485506 beside 「それは死んだ。」 (the It is 「それ」), and the detections after it never showed an It again
nor a second Bokrug (detections.json: from [1,48], [1,19], [2,20], [1,17] and [1,16] at the Powerful
Activation's 45, the It and Bokrug rooms inside every one but the first).  ``living`` read one of each
alive, so the 段2 lure (``after_races_dead`` [393, 595, 489]) never began, and after the summons at
[27,43] the bot teleported (absorbed Teleportation) to [7,72], cast the powered detection there (45 short
of the west rooms) and stopped: quest:blocked:sweep-nothing-comes, '5'.  [7,72] also lay in a pocket of
cells where both sides' summoners act (the Queens' 30 and the sleeping Spawn of Tsathoggua's 20,
quest_alignment_split), and every walk of the plan refused those cells, the way out of the pocket too.

Owner rules: 2026-11-20 「残りの敵を探す時は感知を使うこと」; 2026-11-22 「全感知の強力発動ならクエスト全域を
カバーできるはずだが」 (テレパシーだけで「いない」と決めない); 2026-11-19 「有効な場所で待つ」 and 「来ない時に
延々と待たない」.

Pinned, through the public choose_key:

* the stop board: the bot's choice is a step out of the pocket (quest_room_sweep ``WALK_REASON``), no
  longer the named stop; the detection at [7,72] alone writes nobody off (it covers part of the map);
* the floor's casts at 45 are [15,39] then a neighbour for the two far corners (quest_detect_remaining
  ``_Cover``); out of the pocket the bot walks to [15,39] (``WALK_REASON`` of quest_detect_remaining);
* there the detection is cast, then the second from the neighbour; the board after them, with no It
  and no Bokrug shown, credits the missing ones dead, and the lure of 段2 is active.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival (tests/test_quest33_alignment_split
``recorded``), not life-221's; the board's skill lists are given as in the other Q33 records.  Past
[7,72] the boards are the stop board moved: the player put on the cells the bot's own steps lead to
(after the first steps out of the pocket, straight on [15,39] with the [7,72] detection gone stale),
the game turn advanced 3 a decision, and the detection's result board given the monsters life-221's
detection of 4492306 showed (the floor's latest picture; no It and no Bokrug among them, as on every
detection's board since 4490812).

The owner's answer of 2026-11-23 (「加速して向かい、強引に邪悪側を排除する。」, quest_mixed_assault) came after
this record: its result board (4492306) shows the Queens' fire ants packed round the three awake
Gachapins, the sides mixed, so the shipped plan now assaults the Gachapins from there
(``test_the_shipped_plan_assaults_the_mixed_sides``).  The detection's own rules pinned above are read
on the plan as it was before that answer: DECLARED CONSTRUCTED, ``when_mixed`` taken out of the plan's
``alignment_split`` in ``setUp`` (n1c-221-q33-mixed-1123).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import shutil
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import (
    quest_alignment_split,
    quest_detect_remaining,
    quest_lure_approach,
    quest_mixed_assault,
    quest_room_sweep,
)
from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from tests.test_quest33_alignment_split import BOKRUG, DAGON, IT, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-q33-sweep-1123"
CAST_TURN = 4492304      # the powered detection at [7,72]
RESULT_TURN = 4492306    # its board
STOP_TURN = 4492322      # quest:blocked:sweep-nothing-comes
LANDING = (7, 72)
FIRST_CAST = (15, 39)
CORNERS = ((1, 78), (29, 78))
STEP_KEYS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1), "4": (0, -1), "6": (0, 1), "1": (1, -1), "2": (1, 0),
             "3": (1, 1)}
CREDITED = {IT: 2, BOKRUG: 2, DAGON: 3}


def load(name):
    data = (FIXTURE / name).read_bytes()
    return json.loads(lzma.decompress(data) if name.endswith(".xz") else data)


class N1c221Q33SweepTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        record = Path(self.scratch.name) / "sweep-kills.json"
        shutil.copyfile(FIXTURE / "sweep-kills.json", record)
        self.policy._sweep_kill_record_path = record
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.raw = {board["turn"]: board for board in load("boards.json.xz")}
        if self._testMethodName != "test_the_shipped_plan_assaults_the_mixed_sides":
            # DECLARED CONSTRUCTED (module docstring): the plan before the owner's 2026-11-23 answer.
            del self.plan["alignment_split"][quest_mixed_assault.FIELD]

    def board(self, raw):
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        return replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0))

    def recorded_boards(self):
        """The bot's decisions on the cast, its result and the stop board."""
        return [(turn, self.policy.choose_key(self.board(self.raw[turn])), self.policy.last_reason)
                for turn in (CAST_TURN, RESULT_TURN, STOP_TURN)]

    def navigator(self):
        return self.policy._quest_navigators[QUEST]

    def moved(self, cell, turn, *, shown=False):
        raw = copy.deepcopy(self.raw[STOP_TURN])
        raw["player"]["y"], raw["player"]["x"] = cell
        raw["turn"], raw["messages"] = turn, []
        raw["detected_monsters"] = copy.deepcopy(self.raw[RESULT_TURN]["detected_monsters"]) if shown else []
        return raw

    def test_the_record_is_the_stop(self):
        decisions = load("decisions.json.xz")
        self.assertEqual((decisions[-1]["reason"], decisions[-1]["key"]),
                         (quest_room_sweep.NOTHING_COMES_REASON, WAIT_KEY))
        self.assertEqual((decisions[-1]["position"]["y"], decisions[-1]["position"]["x"]), LANDING)
        record = load("sweep-kills.json")
        counted = {}
        for race, _turn in record["kills"]:
            counted[race] = counted.get(race, 0) + 1
        self.assertEqual({race: counted.get(race, 0) for race in CREDITED}, CREDITED)
        lines = load("kill-lines.json")
        self.assertIn([4485506, "何かは死んだ。"], lines)   # the unnamed death beside the It's
        self.assertIn([4485506, "それは死んだ。"], lines)
        detections = load("detections.json")
        after = [row for row in detections if row["turn"] >= 4486914]
        self.assertTrue(all(IT not in {m[0] for m in row["detected"]} for row in after))
        self.assertTrue(all(sum(1 for m in row["detected"] if m[0] == BOKRUG) <= 1 for row in after))
        last = detections[-1]
        self.assertEqual((last["turn"], tuple(last["player"])), (RESULT_TURN, LANDING))
        self.assertFalse({IT, BOKRUG} & {m[0] for m in last["detected"]})

    def test_the_floor_is_covered_by_two_powered_casts(self):
        self.recorded_boards()
        cover = quest_detect_remaining._cover(self.navigator())
        self.assertEqual(cover.radius, quest_detect_remaining.POWERFUL_RAD)
        self.assertEqual([cell for cell, _adds in cover.steps][:1], [FIRST_CAST])
        self.assertEqual(len(cover.steps), 2)
        uncovered = cover.targets & ~cover.area(FIRST_CAST)
        corners = 0
        for y, x in CORNERS:
            corners |= 1 << (y * cover.width + x)
        self.assertEqual(uncovered, corners)
        self.assertEqual(cover.steps[1][1], corners)

    def test_the_stop_board_steps_out_of_the_pocket(self):
        made = self.recorded_boards()
        self.assertTrue(made[0][2].startswith("me-power:quest-remaining-unseen:detect-all"), made[0])
        turn, key, reason = made[-1]
        self.assertNotEqual(reason, quest_room_sweep.NOTHING_COMES_REASON)
        self.assertEqual(reason, quest_room_sweep.WALK_REASON)
        self.assertIn(key, STEP_KEYS)
        board = self.board(self.raw[STOP_TURN])
        self.assertIn(LANDING, quest_alignment_split.contact_cells(self.policy, board, self.navigator(), self.plan))
        # The detection at [7,72] covers a part of the map only: nobody is written off.
        self.assertEqual(self.navigator().split_kills, CREDITED)
        self.assertEqual(quest_detect_remaining.missing(self.policy, board, self.navigator(), self.plan), [IT, BOKRUG])

    def test_out_of_the_pocket_the_bot_walks_to_the_floors_cast(self):
        self.recorded_boards()
        here, turn = LANDING, STOP_TURN
        for _ in range(6):
            dy, dx = STEP_KEYS[self.policy.choose_key(self.board(self.moved(here, turn)))]
            here, turn = (here[0] + dy, here[1] + dx), turn + 3
        key = self.policy.choose_key(self.board(self.moved(here, turn)))
        self.assertEqual(self.policy.last_reason, quest_detect_remaining.WALK_REASON)
        self.assertIn(key, STEP_KEYS)

    def test_the_whole_floor_detection_writes_off_the_unnamed_dead(self):
        self.recorded_boards()
        navigator = self.navigator()
        turn = STOP_TURN + 200   # the [7,72] detection stale; the bot's walk brought it to [15,39]
        key = self.policy.choose_key(self.board(self.moved(FIRST_CAST, turn)))
        self.assertTrue(self.policy.last_reason.startswith("me-power:quest-remaining-unseen:detect-all:powerful"),
                        self.policy.last_reason)
        self.assertEqual(navigator.remain_detections[-1][:3], (FIRST_CAST, turn, quest_detect_remaining.POWERFUL_RAD))
        # Its board: the two corners are left, so nobody is written off yet; on to a cell covering them.
        turn += 3
        key = self.policy.choose_key(self.board(self.moved(FIRST_CAST, turn, shown=True)))
        self.assertEqual(navigator.split_kills, CREDITED)
        self.assertIn(key, STEP_KEYS)
        dy, dx = STEP_KEYS[key]
        here = (FIRST_CAST[0] + dy, FIRST_CAST[1] + dx)
        cover = quest_detect_remaining._cover(navigator)
        self.assertEqual(cover.area(here) & cover.steps[1][1], cover.steps[1][1])
        turn += 3
        self.policy.choose_key(self.board(self.moved(here, turn)))
        self.assertTrue(self.policy.last_reason.startswith("me-power:quest-remaining-unseen:detect-all:powerful"),
                        self.policy.last_reason)
        # Its board: the whole map covered within the bound, no It and no Bokrug shown: they are dead.
        turn += 3
        shown = self.board(self.moved(here, turn, shown=True))
        self.policy.choose_key(shown)
        self.assertEqual(navigator.split_kills, {IT: 3, BOKRUG: 3, DAGON: 3})
        self.assertEqual(quest_alignment_split.living(self.policy, shown, navigator, self.plan, IT), 0)
        self.assertEqual(quest_alignment_split.living(self.policy, shown, navigator, self.plan, BOKRUG), 0)
        self.assertTrue(quest_lure_approach.active(self.policy, shown, navigator, self.plan))
        self.assertEqual(sorted(turn for race, turn in navigator.split_kill_turns if race in (IT, BOKRUG))[-2:],
                         [shown.turn, shown.turn])

    def test_the_shipped_plan_assaults_the_mixed_sides(self):
        made = self.recorded_boards()
        result = self.board(self.raw[RESULT_TURN])
        self.assertTrue(quest_mixed_assault.mixed_now(self.policy, result, self.navigator(), self.plan))
        self.assertTrue(self.navigator().mixed_assault)
        turn, key, reason = made[-1]
        self.assertEqual((turn, reason), (STOP_TURN, quest_mixed_assault.WALK_REASON))
        self.assertIn(key, STEP_KEYS)


if __name__ == "__main__":
    unittest.main()
