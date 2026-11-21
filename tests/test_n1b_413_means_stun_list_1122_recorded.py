"""A power list shown under a stun the use then cured is read under that stun (n1-b life-413, 1122).

Recorded (tests/fixtures/n1b-413-means-stun-list-1122.jsonl.gz: the snapshot file
snapshots-20261122-040941-2507a3, player turns 2932972-2933001): Angband 80F, the Magic-Eater Lv39
just landed.  A plasma breath of 『火の鳥』 stunned it (SLIGHT); its own *Destruction* then blinded it,
and on turn 2932985 (blind, stunned) it cast the absorbed Cure Light Wounds from the staff list.  The
game printed that list under the stun (cmd-magiceat.cpp adds the stun's magic penalty, 10 for
SLIGHT: *破壊* 87% shown as 77%); the cure ended the stun, and the list arrived on the next board,
2933001, unstunned.  It was read as shown unstunned: *破壊* at 77%, below the 80% of the 50F+
means (me_capability.reliable), so ``destruction_use.means_spent`` held and the Recall was read with
19 charges left (recorded ``return:recall``, trigger ``emergency-destruction-means-spent``).  Now the
list is read under the stun of the board its key was decided on (me_power_success
``note_decided``), and the means hold.

DECLARED RECONSTRUCTED: the staff list (the snapshot files carry no list): its rows as the
town-arrival checkpoint of 04:17:07 (turn 3054123) holds them, *破壊* at 19 charges of 19 (the
decision record's ``*Destruction* uses`` 19); the list the cure showed, attached to 2933001 as the
executor attaches it (``_magic_eater_power_list``), is those rows with the SLIGHT stun's 10 added.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_use, me_power_success, me_powers
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-means-stun-list-1122.jsonl.gz"
CURE_CAST = 2932985   # blind, stunned SLIGHT: the absorbed Cure Light Wounds
RECALLED = 2933001    # unstunned, the list attached: recorded return:recall (means spent)
SLIGHT_PENALTY = 10   # me_power_success.STUN_MAGIC_PENALTY[1]
STAFF_ROWS = (
    ("軽傷の治癒", 4, 19, 19), ("癒し", 4, 13, 13), ("テレポート", 4, 24, 24), ("鑑定", 4, 79, 79),
    ("解呪", 4, 9, 9), ("スピード", 4, 35, 35), ("スターライト", 4, 29, 29), ("光", 4, 71, 71),
    ("邪悪存在退散", 13, 8, 8), ("周辺感知", 4, 52, 52), ("力", 59, 5, 5), ("財宝感知", 4, 59, 59),
    ("聖浄", 59, 5, 5), ("アイテム感知", 4, 41, 41), ("トラップ感知", 4, 34, 34), ("地震", 4, 5, 5),
    ("ドア/階段感知", 4, 75, 75), ("*破壊*", 13, 19, 19), ("透明物体感知", 4, 13, 13),
    ("邪悪存在感知", 4, 50, 50),
)


def _rows(penalty=0):
    rows = []
    for name, fail, current, maximum in STAFF_ROWS:
        shown = min(95, fail + penalty)
        rows.append({"name": name, "fail": shown, "success": 100 - shown,
                     "current": current, "max": maximum})
    return tuple(rows)


class MeansStunListRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, last):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn - 1, _rows())}
        # The town's list, shown unstunned with the same INT, level and worn items.
        me_power_success.forget_list_boards(policy)
        policy._me_device_list_boards = {"staff": (0, me_power_success._inputs(first))}
        for raw in self.boards:
            raw = copy.deepcopy(raw)
            if raw["turn"] == RECALLED:
                raw["_magic_eater_power_list"] = {"kind": "staff", "rows": list(_rows(SLIGHT_PENALTY))}
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            if board.turn == last:
                return policy, board
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("no board %d" % last)

    def test_the_cure_was_cast_stunned(self):
        _, board = self.replay(CURE_CAST)
        self.assertTrue(board.player.stunned)
        self.assertTrue(board.player.blind)

    def test_the_list_is_read_under_the_stun_it_was_shown_under(self):
        policy, board = self.replay(RECALLED)
        self.assertFalse(board.player.stunned)
        key = policy.choose_key(board)
        # Recorded: return:recall with 19 charges of *Destruction* left.
        self.assertNotEqual(policy.last_reason, destruction_use.MEANS_SPENT_REASON, key)
        self.assertNotEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)
        self.assertTrue(destruction_use.holds_means(policy, board))
        self.assertEqual(policy._me_device_list_boards["staff"][0], 1)
        self.assertEqual(
            me_powers.unstunned_success(policy, board, ("staff", SV_STAFF_DESTRUCTION)), 87)

    def test_without_a_decided_board_the_list_board_is_its_own(self):
        policy, board = self.replay(RECALLED)
        setattr(policy, me_power_success.DECIDED, None)
        me_power_success.observe_list_board(policy, "staff", board)
        self.assertEqual(policy._me_device_list_boards["staff"][0], 0)


if __name__ == "__main__":
    unittest.main()
