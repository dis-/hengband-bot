"""A process restarted in the dungeon reads a lost absorbed-power list again.

Recorded: n1-b life-411 2026-11-21 (Magic-Eater Lv50, *Destruction* absorbed 99/99, 98% to
cast): tests/fixtures/n1b-411-me-list-reread-1121 holds the arrival checkpoint of the process
started at 11:26 (a fresh process: no ``_me_device_lists``, no absorption record), its first town
rows (row 4-6 browse 'bA', 'bB', 'bC'; the staff list is shown on row 5's board) and three
Angband 95F boards of the same life (12:02-12:03).

The lists live in the process only.  me_capability.reliable reads the displayed row of the
absorbed *Destruction*: without the staff list the power is no means (destruction_use.holds_means
false), and on a 50F+ floor the means-spent rung recalls.  A process restarted in the dungeon reads
each list once (me_powers_refresh.resume_read_key, n1-c life-178); a first 'bA' whose list never
arrived left the kind unread for the whole process.  Pinned: on the recorded 95F boards a list
still missing ``RESUME_RETRY_DECISIONS`` decisions after its read is read again, up to
``RESUME_READ_ATTEMPTS`` reads of each kind and no more; once the recorded staff list is observed,
the absorbed *Destruction* is the 95F floor's means again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, me_powers_refresh
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-me-list-reread-1121"
STAFF_LIST_ROW = 5   # the board after row 4's 'bA': the staff list (*破壊* 99/99, success 98)
# The bound (me_powers_refresh.RESUME_RETRY_DECISIONS / RESUME_READ_ATTEMPTS): read again five
# decisions after a read whose list is still missing, three reads of a kind in all.
RETRY = getattr(me_powers_refresh, "RESUME_RETRY_DECISIONS", 5)
ATTEMPTS = getattr(me_powers_refresh, "RESUME_READ_ATTEMPTS", 3)


class N1b411MeListRereadRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, self.steps = load(FIXTURE, Path(self.scratch.name))
        self.policy._me_power_resume_reads = True
        boards = json.loads(lzma.decompress((FIXTURE / "dungeon-boards.json.xz").read_bytes()))
        self.boards = [parse_snapshot(board, self.policy._monrace_knowledge) for board in boards]

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def _reads(self, decisions: int) -> list:
        keys = []
        for index in range(decisions):
            self.policy._decision_sequence += 1
            board = self.boards[index % len(self.boards)]
            keys.append(me_powers_refresh.resume_read_key(self.policy, board))
        return keys

    def test_a_lost_list_is_read_again_within_the_bound(self):
        policy = self.policy
        self.assertFalse(getattr(policy, "_me_device_lists", None))
        board = self.boards[-1]
        self.assertEqual(board.dungeon_level, 95)
        self.assertFalse(destruction_use.holds_means(policy, board))
        retry, attempts = RETRY, ATTEMPTS
        self.assertEqual((retry, attempts), (5, 3))
        keys = self._reads(retry * (attempts + 2))
        reads = [key for key in keys if key is not None]
        self.assertEqual(reads, ["bA", "bB", "bC"] * attempts)
        self.assertEqual(keys[:3], ["bA", "bB", "bC"])
        self.assertIsNone(keys[3])
        self.assertEqual(keys[retry], "bA")
        self.assertTrue(all(key is None for key in keys[-retry:]))

    def test_the_reread_staff_list_restores_the_means(self):
        policy = self.policy
        self.assertEqual(self._reads(1), ["bA"])          # its list never arrives
        listed = self.steps[STAFF_LIST_ROW][1]()
        self.assertEqual(self.journal[STAFF_LIST_ROW - 1]["key"], "bA")
        self.assertEqual(listed.magic_eater_power_list["kind"], "staff")
        keys = self._reads(RETRY)
        self.assertEqual(keys[:2], ["bB", "bC"])
        self.assertEqual(keys[-1], "bA")                   # the staff list is read again
        observe_lists(policy, listed)                      # and this time it arrives
        board = self.boards[-1]
        self.assertTrue(destruction_use.holds_means(policy, board))
        self.assertNotIn("bA", self._reads(RETRY * 2))


if __name__ == "__main__":
    unittest.main()
