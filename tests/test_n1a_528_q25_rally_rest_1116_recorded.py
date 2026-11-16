"""Quest 25 on n1-a life-528 (2026-11-16 13:12:42-13:13:13): the rally's rest on the choke, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-a/life-528/captures/20261116-131306-loop-detected,
build bot-0f3b00a68; battle phase 2, Ipsissimus, rallying on the choke [3,1]):

 * A summons fought on [4,1] (decisions 26-30), the rally walked back to the choke ('8' 31,
   ``quest25:walk``) at 778/1056 HP.
 * On [3,1] none was remembered nor in view: ``_rally`` ended the rally and answered None, and the
   phase's walk to a cell that sees the pen ran on in the same decision ('2' 32,
   ``quest25:walk-to-sight``), off the choke.
 * On [4,1] the phase's preparation (``_prepare``: phase2 「全快して(7,1)に移動」) rested ('R&' 33):
   Ipsissimus summoned at once (34).  The same three boards repeated at 36-38 and 101-103, and the
   next process rested on [4,1] the same way (13:13:10, its decision 1) into the fight it died in.

The rule (``_rally``'s own note: 「The rally ends on the choke ...; the phase then rests to full HP
again before its walk to [7,1]」): the board the rally ends on, the preparation answers first, on
the choke.

Recorded: tests/fixtures/n1a-528-q25-rally-rest-1116.json.gz
(tests/extract_n1a_528_q25_rally_rest_1116_fixture.py, copies of the captures in
C:/hengband-backups/pdca/captures/n1a-528-q25-death-1116): the restarted process's boards (its
ring: decisions 26-105) and the battle record.  A fresh policy restores the record through the real
path and decides the boards through the public ``choose_key``; each key is posted through the
production executor, the game then showing the next recorded board
(tests/test_n1b_382_q25_patrol_owner_1113_recorded ``_Replay``).

DECLARED: the record is the one the last process left (13:13:13, phase 2 and rallying as on these
boards), its turn set to the first board's; the skill knowledge is the next process's (turn
3684472, the same character five seconds later).  The character is a warrior: no magic-eater lists.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.model import parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-528-q25-rally-rest-1116.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CHOKE, SUMMONED = (3, 1), (4, 1)
RALLY_END = 32   # the decision on the choke the rally ended on


def _row(sequence):
    index = next(index for index, row in enumerate(CASE["second"]["recorded"])
                 if row["sequence"] == sequence)
    board = CASE["second"]["boards"][index]
    return index, board, CASE["second"]["recorded"][index]


class TheRecordingTest(unittest.TestCase):

    def test_the_walk_left_the_choke_and_the_rest_drew_a_summons(self):
        _index, board, row = _row(RALLY_END)
        self.assertEqual((board["player"]["y"], board["player"]["x"]), CHOKE)
        self.assertLess(board["player"]["hp"], board["player"]["max_hp"])
        self.assertEqual((row["key"], row["reason"]), ("2", battle.SIGHT_REASON))
        _index, board, row = _row(RALLY_END + 1)
        self.assertEqual((board["player"]["y"], board["player"]["x"]), SUMMONED)
        self.assertEqual(row["reason"], battle.FULL_HP_REASON)
        _index, board, _row_ = _row(RALLY_END + 2)
        self.assertTrue(any("イプシシマス" in line and "召喚" in line for line in board["messages"]))
        record = CASE["battle_record"]["battle"]
        self.assertEqual(record["phase"], battle.phase_index("ipsissimus"))
        self.assertIs(record["rallying"], True)


class RestOnTheChokeTest(replay._Replay):
    case = CASE

    def _drive_to(self, last, edit=None):
        """[(sequence, cell, key, reason)] of the boards from the first to ``last`` (decided)."""
        boards, recorded = CASE["second"]["boards"], CASE["second"]["recorded"]
        answers = []
        with TemporaryDirectory() as directory:
            policy = replay.new_policy(Path(directory), {}, None, CASE)
            for index in range(len(boards)):
                raw = copy.deepcopy(boards[index])
                if edit is not None and recorded[index]["sequence"] == last:
                    edit(raw)
                snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                key = policy.choose_key(snapshot)
                answers.append((recorded[index]["sequence"],
                                (snapshot.player.position.y, snapshot.player.position.x),
                                key, policy.last_reason))
                if recorded[index]["sequence"] == last:
                    return answers
                self.assertTrue(replay._shown(key), answers[-1])
                self.post(policy, raw, key, boards[index + 1])
        self.fail(answers[-1])

    def test_the_rally_ends_with_the_rest_on_the_choke(self):
        answers = self._drive_to(RALLY_END)
        self.assertEqual(answers[-2][1:], (SUMMONED, "8", battle.WALK_REASON))   # back to the choke
        self.assertEqual(answers[-1], (RALLY_END, CHOKE, battle.FULL_HP_REST_KEY,
                                       battle.FULL_HP_REASON))

    def test_at_full_hp_the_walk_to_the_sight_goes_on(self):
        # DECLARED CONSTRUCTED control: the same board at full HP -- nothing to rest for, the
        # preparation is done and the walk to the pen's sight steps off the choke as recorded.
        def full(raw):
            raw["player"]["hp"] = raw["player"]["max_hp"]

        answers = self._drive_to(RALLY_END, full)
        self.assertEqual(answers[-1], (RALLY_END, CHOKE, "2", battle.SIGHT_REASON))


if __name__ == "__main__":
    unittest.main()
