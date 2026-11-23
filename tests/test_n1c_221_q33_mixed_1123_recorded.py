"""n1-c life-221, Quest 33 (2026-11-23 13:57-13:58): loop-detected on [15,39], the sides already mixed.

Recorded (tests/fixtures/n1c-221-q33-mixed-1123, extracted by tests/extract_n1c_221_q33_mixed_1123_fixture.py
from the server capture 20261123-135824-loop-detected, bot main 2e85676a9).  After the stop of 13:00
(n1c-221-sweep-1123) the bot resumed, cast the Rod of Detection's Powerful Activation (radius 45) at [7,72]
on 4492322, fought the Queens' ants in the east (two Queens killed: the restart record credits 581 x2),
cast the Staff of Detect Evil (30) at [1,43] and walked to [15,39], the floor's first cast cell of the plan
(quest_detect_remaining ``_Cover`` at 45).  The It and the Bokrug the kill lines miss were looked for; the
rod was charging, so the staff's row served the trigger at 30, and [15,39] stayed the next cast's cell:
the 30 was sent there 35 times (30 landed, me-power-uses.json) until the loop guard stopped the bot.  The
boards of those casts show the three Gachapins in their room ([20,57], [21,59], [22,57]) and, on some of
them, the Queens' ants beside two of them (巨大シロアリ [20,56], 巨大黒アリ [22,56], by telepathy): the
sides already mixed.

Owner rules: 2026-11-23, asked 「善と悪の召喚持ちがすでに同じ部屋に混ざって互いに召喚し合っている時、どうしますか？」,
verbatim 「加速して向かい、強引に邪悪側を排除する。」 (quest_mixed_assault); 2026-11-20 「残りの敵を探す時は感知を
使うこと」 and 2026-11-22 「全感知の強力発動ならクエスト全域をカバーできるはずだが」 (quest_detect_remaining).

Pinned, through the public choose_key:

* the record is the loop: the decisions end with 35 Detect Evil casts on [15,39] and the loop guard;
* the staff's cast on [15,39] is made once: the next boards cast nothing there (it would add nothing);
* the board with a Gachapin and an ant in a line is read mixed (``mixed_now``; the Gachapins alone with
  no GOOD monster are not), the assault is latched and the bot's choice is its walk toward a Gachapin;
* in view, the Gachapin is shot before the ant beside the player; with the haste off the haste comes
  first; with the sides not mixed the 段2 lure's own rung is unchanged (no assault).

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival (tests/test_quest33_alignment_split
``recorded``), not life-221's.  Its absorbed lists are life-217's, with the Rod of Detection row set
charging (the record shows the staff serving the rod-preferring row on every cast, me_powers
``_serving``: the rod could not be used; its list screen is not in the capture).  The navigator is given
the [7,72] powered cast of 4492322 (me-power-uses.json; the boards begin after it).  The in-view boards
are the stop board with the player and the monsters moved into the Gachapins' room.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import shutil
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import haste_read, quest_alignment_split, quest_detect_remaining, quest_lure_approach, quest_mixed_assault
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import MELEE_REASON, SPEED_REASON
from tests.test_quest33_alignment_split import QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-q33-mixed-1123"
POWERED_CAST = ((7, 72), 4492322, quest_detect_remaining.POWERFUL_RAD, "detect-all")
LOOP_CELL = (15, 39)
FIRST_STAFF_ON_CELL = 4492893
STOP_TURN = 4492977
MIXED_TURN = 4492969     # a board of the casts with the ants beside the Gachapins (telepathy)
DETECT_EVIL = "me-power:quest-remaining-unseen:detect-evil"
GACHAPIN, WHITE_ANT, QUEEN = 441, 75, 581
STEP_KEYS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1), "4": (0, -1), "6": (0, 1), "1": (1, -1), "2": (1, 0),
             "3": (1, 1)}


def load(name):
    data = (FIXTURE / name).read_bytes()
    return json.loads(lzma.decompress(data) if name.endswith(".xz") else data)


class N1c221Q33MixedTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        record = Path(self.scratch.name) / "sweep-kills.json"
        shutil.copyfile(FIXTURE / "sweep-kills.json", record)
        self.policy._sweep_kill_record_path = record
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        self.boards = load("boards.json.xz")
        self.raw = {board["turn"]: board for board in self.boards}
        # The first board builds the navigator; then the facts the boards begin after.
        self.policy.choose_key(self.board(self.boards[0]))
        self.navigator().remain_detections = (POWERED_CAST,)
        lists = dict(self.policy._me_device_lists)
        lists["rod"] = (self.boards[0]["turn"], tuple(
            dict(row, charging=row["max"]) if row.get("name") == "全感知" else row for row in lists["rod"][1]))
        self.policy._me_device_lists = lists

    def board(self, raw):
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        return replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0))

    def navigator(self):
        return self.policy._quest_navigators[QUEST]

    def replay(self, until):
        made = []
        for raw in self.boards[1:]:
            if raw["turn"] > until:
                break
            key = self.policy.choose_key(self.board(raw))
            made.append((raw["turn"], (raw["player"]["y"], raw["player"]["x"]), key, self.policy.last_reason))
        return made

    def in_room(self, player, monsters, *, hasted=True):
        """DECLARED CONSTRUCTED: the stop board with the player and the monsters moved (in view)."""
        raw = copy.deepcopy(self.raw[STOP_TURN])
        raw["player"]["y"], raw["player"]["x"] = player
        raw["turn"], raw["messages"], raw["detected_monsters"] = STOP_TURN + 3, [], []
        shown = []
        for index, race, (y, x) in monsters:
            knowledge = self.policy._monrace_knowledge[race]
            shown.append({"asleep": False, "confused": False, "fast": False, "fearful": False, "friendly": False,
                          "health": "unhurt", "index": index, "invulnerable": False, "level": knowledge.level,
                          "name": knowledge.names[0], "pet": False, "race_id": race, "slow": False,
                          "stunned": False, "x": x, "y": y})
        raw["visible_monsters"] = shown
        board = self.board(raw)
        if not hasted:
            value, text, _colour, riding = board.player.speed_display
            board = replace(board, player=replace(board.player, speed=board.player.speed - 10,
                                                  speed_display=(value - 10, text, "white", riding)))
        return board

    def test_the_record_is_the_loop(self):
        decisions = load("decisions.json.xz")
        self.assertEqual(decisions[-1]["reason"], "loop-detected")
        casts = [row for row in decisions[:-1] if row["reason"] == DETECT_EVIL
                 and (row["position"]["y"], row["position"]["x"]) == LOOP_CELL]
        self.assertEqual(len(casts), 35)
        uses = load("me-power-uses.json")
        self.assertEqual((tuple(uses[0]["position"]), uses[0]["turn"], uses[0]["reason"]),
                         ((7, 72), 4492322, "me-power:quest-remaining-unseen:detect-all:powerful"))
        on_cell = [use for use in uses if tuple(use["position"]) == LOOP_CELL]
        self.assertTrue(on_cell and all(use["used"] == ["staff", 15] for use in on_cell))
        kills = {}
        for race, _turn in load("sweep-kills.json")["kills"]:
            kills[race] = kills.get(race, 0) + 1
        self.assertEqual(kills, {393: 2, 489: 2, 595: 3, QUEEN: 2})
        mixed = self.raw[MIXED_TURN]
        self.assertEqual(sorted((m["race_id"], m["y"], m["x"]) for m in mixed["detected_monsters"]),
                         [(49, 22, 56), (WHITE_ANT, 20, 56), (GACHAPIN, 20, 57), (GACHAPIN, 21, 59),
                          (GACHAPIN, 22, 57)])

    def test_the_staff_is_cast_once_on_the_cell(self):
        made = self.replay(STOP_TURN)
        on_cell = [row for row in made if row[1] == LOOP_CELL and row[3].startswith("me-power:quest-remaining-unseen")]
        self.assertEqual([(turn, reason) for turn, _cell, _key, reason in on_cell],
                         [(FIRST_STAFF_ON_CELL, DETECT_EVIL)])
        # The cover is the 45 of the powered cast; the staff's 30 on [15,39] adds nothing more there.
        navigator = self.navigator()
        cover = quest_detect_remaining._cover(navigator)
        self.assertEqual(cover.radius, quest_detect_remaining.POWERFUL_RAD)
        self.assertEqual(cover.steps[0][0], LOOP_CELL)
        board = self.board(self.raw[STOP_TURN])
        # The It and the Bokrug the kill lines miss (and the Queen, which Detect Evil does not show).
        self.assertEqual(quest_detect_remaining.missing(self.policy, board, navigator, self.plan), [QUEEN, 393, 489])

    def test_the_mixed_sides_are_assaulted(self):
        before = self.board(self.raw[4492838])   # the Gachapins alone on the board, from [1,43]
        self.assertFalse(quest_mixed_assault.mixed_now(self.policy, before, self.navigator(), self.plan))
        self.assertTrue(quest_mixed_assault.mixed_now(
            self.policy, self.board(self.raw[MIXED_TURN]), self.navigator(), self.plan))
        made = self.replay(STOP_TURN)
        board = self.board(self.raw[STOP_TURN])   # the ants out of telepathy again: the latch holds
        self.assertFalse(quest_mixed_assault.mixed_now(self.policy, board, self.navigator(), self.plan))
        self.assertTrue(self.navigator().mixed_assault)
        turn, cell, key, reason = made[-1]
        self.assertEqual((turn, cell, reason), (STOP_TURN, LOOP_CELL, quest_mixed_assault.WALK_REASON))
        self.assertEqual(key, "2")   # down the central column toward the Gachapins' room
        # The lure of 段2 gives way while mixed.
        self.assertIsNone(quest_lure_approach.key(self.policy, board, self.navigator(), self.plan, None))

    def test_in_view_the_gachapin_is_shot_before_the_ant_beside(self):
        self.replay(STOP_TURN)
        board = self.in_room((23, 58), [(35, GACHAPIN, (20, 58)), (69, WHITE_ANT, (23, 59))])
        key = self.policy.choose_key(board)
        self.assertNotEqual(self.policy.last_reason, MELEE_REASON)
        self.assertNotEqual(self.policy.last_reason, quest_mixed_assault.WALK_REASON)
        self.assertNotIn(key, STEP_KEYS)
        self.assertIn("8", key)   # aimed north, at the Gachapin

    def test_the_haste_first(self):
        self.replay(STOP_TURN)
        board = self.in_room(LOOP_CELL, [], hasted=False)
        haste_read.observe(self.policy, board)
        self.assertFalse(self.policy._player_hasted(board))
        self.policy.choose_key(board)
        self.assertTrue(self.policy.last_reason.startswith(SPEED_REASON), self.policy.last_reason)

    def test_not_mixed_no_assault(self):
        board = self.board(self.raw[4492838])
        self.policy.choose_key(board)
        self.assertFalse(self.navigator().mixed_assault)
        self.assertIsNone(quest_mixed_assault.key(self.policy, board, self.navigator(), self.plan, None))
        self.assertEqual(quest_alignment_split._monster_side(
            self.policy, board.detected_monsters[0], quest_alignment_split.split_of(self.plan)),
            quest_alignment_split.EVIL)


if __name__ == "__main__":
    unittest.main()
