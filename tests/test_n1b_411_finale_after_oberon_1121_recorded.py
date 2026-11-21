"""After Oberon: resupplied in town, the expedition goes on down to 100F (n1-b life-411).

Owner 2026-11-21 (verbatim, LOCKED) 「100Fへ降りる前に巻物を補給する」: Oberon killed on 99F, the
success recall and the town's resupply, then 100F.  Recorded (capture
n1b-411-20261121-98f-ordinary): n1-b killed Oberon (quest 8 COMPLETED), recalled and
resupplied; its next expeditions landed on 99F (14:25:30, and by the stairs from 98F at 14:36:55)
and the battle read the success recall on the arrival board each time, because the floor's quest
was done (angband_finale_battle ``recall_permitted``), so 100F was never reached.  The battle now
owns only a floor whose quest was TAKEN when it was first seen (``applies``,
``Battle.done_on_arrival``): a cleared 99F is the ordinary descent's, toward 100F.

Fixture tests/fixtures/n1b-finale-after-oberon-1121: n1-b's town-arrival checkpoint of 14:25:37
(the first 36 journal rows) and the recorded 99F boards 765 (the 14:36:55 arrival by the stairs) and
767 (where it read the recall), quest 8 COMPLETED and quest 9 TAKEN.

DECLARED CONSTRUCTED: the expedition's mark (finale_prep ``lifted``), as during the trip; the
battle memory of the earlier 99F forgotten (the town visit's floor change); no return latched; no list re-read at the decision's head; for the success case, the battle's floor
first seen with quest 8 still TAKEN.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, angband_finale_battle as battle, finale_prep
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-finale-after-oberon-1121"


class N1b411FinaleAfterOberonRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(self.policy)
        held.lifted, held.step, held.in_town = True, finale_prep.DONE, False  # DECLARED
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        self.policy._me_power_resume_reads = False  # DECLARED
        # DECLARED: the town visit between (journal rows not replayed here) is a floor change, which
        # forgets the battle of the 99F where Oberon fell (floor_visit_memory); the checkpoint was
        # taken before that visit's first board, so it still holds it.
        setattr(self.policy, battle.MEMORY, None)
        rows = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
        self.boards = {row["line"]: parse_snapshot(row["board"], self.policy._monrace_knowledge)
                       for row in rows}

    def tearDown(self):
        self.scratch.cleanup()

    def decide(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = self.policy.choose_key(board)
        if key:
            self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason

    def test_a_cleared_99f_is_no_success_to_recall_on(self):
        board = self.boards[765]
        self.assertEqual(board.dungeon_level, 99)
        self.assertTrue(angband_finale.quest_done(board))
        _key, reason = self.decide(board)
        self.assertNotEqual(reason, battle.RECALL_REASON)
        _key, reason = self.decide(self.boards[767])  # the recorded recall's board
        self.assertNotEqual(reason, battle.RECALL_REASON)
        self.assertFalse(battle.applies(self.policy, board))
        self.assertTrue(finale_prep.lifted(self.policy))  # the expedition goes on

    def test_a_kill_on_this_floor_is_the_success_recall(self):
        board = self.boards[767]
        # DECLARED: this floor first seen with quest 8 still TAKEN (the battle's own kill).
        battle.battle(self.policy, board).done_on_arrival = False
        self.assertTrue(battle.applies(self.policy, board))
        self.assertTrue(battle.recall_permitted(self.policy, board))


if __name__ == "__main__":
    unittest.main()
