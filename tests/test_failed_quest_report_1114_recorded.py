"""A FAILED fixed quest is reported at its building (failed-quest-report-1114).

n1-b life-397 and n1-c life-207 recalled out of Q18 (2026-11-14 14:46 -> 14:53 and
05:13 -> 05:17): Q18 is FAILED (5).  market/building-quest.cpp castle_quest turns a FAILED
quest into FAILED_DONE (6) only when the character enters the building and selects it,
and lib/edit/towns/01_Outpost_Full.jsonc keeps the castle on Q18 while it is 5 ("Quest 18
failed, wait for the player to enter the castle"); Q25 is offered only at $QUEST18 4 or 6.
The bot knew statuses 0..4 only: the head (``_build_fixed_quest_head``) took taken,
completed and offered untaken quests, so with the castle showing [18, 32] the head was
None, Q25 was never evaluated and the visit left town.

Fix: a FAILED quest whose building in this town still holds it is the head; its report
(``_fixed_quest_report_failed_key``, reason fixedquest:report-failed) walks to the
building and enters it with the building's 'q' (BACT_QUEST), the keys of a request or a
claim, in the quest stage.  Once the game reads 6 the castle offers Q25 and its existing
acceptance gates decide.

Recorded: n1-c life-207's town-arrival checkpoint of the 15:56:51 Outpost visit (its six
journal rows and sidecars, tests/extract_failed_quest_report_1114_fixture.py) through the
public choose_key; every key is posted through the production executor
(``_ExecutorInputPort``).  Rows 0-1 replay (row 0 FORCED); the recorded row 2 walked to
the General Store and row 4 to the dungeon entrance; the fixed policy walks to the castle.

DECLARED CONSTRUCTED: the boards after row 2 (each step moves the player one cell, ten
game turns on); the board after the report (Q18 at 6 and the rebuilt castle cells' special
25, as the town map's $QUEST18 6 rule builds them, the player on the castle cell).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import (
    LEAVE_STORE_KEY, QUEST_STATUS_FAILED, QUEST_STATUS_FAILED_DONE, QUEST_STATUS_UNTAKEN,
)
from hengbot.town_terminal import rung_terminal
from hengbot.town_visit_plan import STAGE_DEADLINES, stage_of
from support.town_arrival_fixture import load
from tests.support import recorded as harness

FIXTURE = Path(__file__).with_name("fixtures") / "failed-quest-report-1114"
# DECLARED: row 0's recorded key is posted undecided-equal (the periodic character dump's
# timer runs on the replay's clock; the recorded row 0 restored the weapon first).
FORCED = {0}
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
REPORT = "fixedquest:report-failed"
ENTER_TAIL = "q" + LEAVE_STORE_KEY


class FailedQuestReport1114RecordedTest(harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def load(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy, rows

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def to_row_2(self):
        """Rows 0-1 decided as recorded; row 2's raw board."""
        policy, rows = self.load()
        for recorded, supply in rows[:2]:
            key = policy.choose_key(supply())
            if recorded["row"] not in FORCED:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            policy.confirm_key_posted(recorded["key"])
        self.assertEqual(rows[2][0]["reason"], "shop:travel")
        self.assertEqual(rows[4][0]["reason"], "town:travel-entrance")
        return policy, self.raw(2)

    def board(self, policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    def walk_to_report(self, policy, raw):
        """Decide and post each step to the castle; the entering key, its board and steps."""
        steps = []
        for _ in range(60):
            board = self.board(policy, raw)
            key = str(policy.choose_key(board))
            steps.append((key, policy.last_reason))
            if key.endswith(ENTER_TAIL):
                return key, raw, steps
            self.assertEqual(policy.last_reason, REPORT + ":approach", steps)
            self.assertIn(key, DIRECTIONS, steps)
            dy, dx = DIRECTIONS[key]
            following = self.later(raw)
            following["player"] = dict(following["player"], y=raw["player"]["y"] + dy,
                                       x=raw["player"]["x"] + dx)
            self.assertEqual(self.post(policy, raw, key, [], following), [key])
            policy.confirm_key_posted(key)
            raw = following
        self.fail(steps)

    def test_the_recorded_visit_holds_a_failed_q18_in_the_castle(self):
        policy, raw = self.to_row_2()
        board = self.board(policy, raw)
        self.assertEqual(board.quests[18].status, QUEST_STATUS_FAILED)
        # Q25 is not disclosed yet: the bot knows it from the quest definitions.
        self.assertNotIn(25, board.quests)
        self.assertEqual(policy._known_fixed_quests(board)[25].status, QUEST_STATUS_UNTAKEN)
        self.assertEqual(sorted({grid.building_special for grid in board.grids.values()
                                 if grid.building_special > 0}), [18, 32])
        self.assertFalse(policy._fixed_quest_is_offered(board, 25))
        head = policy._build_fixed_quest_head(board)
        self.assertEqual((head.id, head.status), (18, QUEST_STATUS_FAILED))
        terminal = rung_terminal(policy, "_fixed_quest_key#2", board)
        self.assertEqual((terminal.terminal_id, terminal.args), ("quest-report-failed", (18,)))

    def test_the_bot_reports_q18_at_the_castle_and_the_head_moves_on(self):
        policy, raw = self.to_row_2()
        key, raw, steps = self.walk_to_report(policy, raw)
        board = self.board(policy, raw)
        castle = {grid.position for grid in board.grids.values() if grid.building_special == 18}
        # One step onto the castle's cell, its 'q' (BACT_QUEST), then out of the building.
        self.assertEqual(policy.last_reason, REPORT, steps)
        direction = key[:-len(ENTER_TAIL)]
        self.assertIn(direction, DIRECTIONS)
        dy, dx = DIRECTIONS[direction]
        entered = Position(board.player.position.y + dy, board.player.position.x + dx)
        self.assertIn(entered, castle)
        # The report is the quest stage's own operation; the walk is not counted.
        self.assertEqual(stage_of("quest-request"), "quest")
        from hengbot.town_visit import town_visit
        self.assertLessEqual(town_visit(policy).stage_decisions.get("quest", 0),
                             STAGE_DEADLINES["quest"])
        # DECLARED CONSTRUCTED: the game's answer.  castle_quest: FAILED -> FAILED_DONE and
        # the town is rebuilt on leaving the building; the $QUEST18 6 rule puts Q25 on the
        # castle cells.
        reported = self.later(raw)
        reported["player"] = dict(reported["player"], y=entered.y, x=entered.x)
        for quest in reported["progress"]["quests"]:
            if quest["id"] == 18:
                quest["status"] = QUEST_STATUS_FAILED_DONE
        rebuilt = 0
        for cell in reported["grid_map"]["cells"]:
            if cell.get("p") == 18:
                cell["p"] = 25
                rebuilt += 1
        self.assertEqual(rebuilt, len(castle))
        self.assertEqual(self.post(policy, raw, key, [], reported), [key])
        policy.confirm_key_posted(key)

        board = self.board(policy, reported)
        self.assertEqual(board.quests[18].status, QUEST_STATUS_FAILED_DONE)
        self.assertTrue(policy._fixed_quest_is_offered(board, 25))
        key = str(policy.choose_key(board))
        # Never the failed quest again: the head is Q25, whose acceptance is now judged.
        self.assertNotEqual(policy.last_reason, REPORT)
        self.assertFalse(policy.last_reason.startswith("fixedquest:report-failed"))
        self.assertFalse(key.endswith(ENTER_TAIL) and policy.last_reason.startswith(REPORT))
        head = policy._build_fixed_quest_head(board)
        self.assertEqual((head.id, head.status), (25, QUEST_STATUS_UNTAKEN))
        readiness = policy.fixed_quest_readiness_state()
        self.assertEqual(readiness.get("quest_id"), 25, readiness)


if __name__ == "__main__":
    unittest.main()
