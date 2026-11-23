"""A restarted Magic-Eater's unread absorbed-power list is not "no *Destruction* means".

n1-c life-221 (Magic-Eater Lv46, the absorbed *Destruction* at 96%) was restarted on the
Mountain's 50F at 15:17:34 on 2026-11-23 (turn 4507414).  The lists live in the process only and
me_capability.reliable reads the displayed row, so until 'bA' shows the staff list
destruction_use.holds_means is False.  The climb no longer reads that as "no means"
(deep_climb._means_unread, tests/test_n1c_221_restart_climb_1123_recorded.py); the means-spent
return (destruction_use.means_spent, the floor's gap ``gap_here``) and the trap-door guard's leave
(deep_fall_guard.key) did: with the climb not held, the board after the three reads, the staff
list still awaited, read Word of Recall under ``emergency-destruction-means-spent`` (owner
「破壊の手段は十分にあるが？」).

Pinned: while the staff list is to be read (destruction_use.means_unread, the same rule as the
climb's) no rule leaves, climbs or recalls for the missing means; once the list is read the means
hold and nothing recalls; a list never read after every bounded attempt is no means, and the
means-spent return reads Word of Recall as before.

Recorded: tests/fixtures/n1c-221-restart-climb-1123 (the 15:15:13 town-arrival checkpoint and the
restarted process's first board on the Mountain's 50F).

DECLARED CONSTRUCTED: the restart (the process-only state of a fresh process, as in
tests/test_n1c_221_restart_climb_1123_recorded.py); the staff list that does not arrive for the
first decisions (its read is retried, me_powers_refresh.RESUME_RETRY_DECISIONS) and the arrival
policy's own list as the one read.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-restart-climb-1123"
MOUNTAIN = 14
RECALL_KEY = "rg"


class MeListUnreadTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.arrival, _journal, _steps = load(FIXTURE, Path(cls.scratch.name))
        raws = json.loads(lzma.decompress((FIXTURE / "dungeon-boards.json.xz").read_bytes()))
        cls.first = parse_snapshot(raws[0], cls.arrival._monrace_knowledge)
        cls.lists = copy.deepcopy(cls.arrival._me_device_lists)

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _restarted(self):
        """DECLARED CONSTRUCTED: the fresh process of 15:17:34."""
        from hengbot import deep_climb

        policy = copy.deepcopy(self.arrival)
        policy._me_device_lists = {}
        policy._me_power_resume_attempts = {}
        policy._me_power_resume_reads = True
        policy._decision_sequence = 0
        setattr(policy, deep_climb.MEMORY, None)
        return policy

    def _decide(self, policy, decisions):
        out = []
        for _ in range(decisions):
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                key = policy.choose_key(self.first)
            out.append((key, policy.last_reason))
        return out

    def test_the_recorded_board(self):
        from hengbot import destruction_use

        self.assertEqual((self.first.floor_key, self.first.turn), ((MOUNTAIN, 50, 0), 4507414))
        policy = self._restarted()
        self.assertFalse(destruction_use.holds_means(policy, self.first))
        policy._me_device_lists = copy.deepcopy(self.lists)
        self.assertTrue(destruction_use.holds_means(policy, self.first))

    def test_no_recall_while_the_staff_list_is_awaited(self):
        from hengbot import destruction_use, dive_floor

        policy = self._restarted()
        decided = self._decide(policy, 4)
        # The three resume reads, the lists not arriving (DECLARED CONSTRUCTED).
        self.assertEqual([key for key, _reason in decided[:3]], ["bA", "bB", "bC"])
        # Without the fix: ('rg', 'return:recall') under emergency-destruction-means-spent.
        self.assertNotEqual(decided[3][0], RECALL_KEY, decided[3])
        self.assertFalse(destruction_use.means_spent(policy, self.first))
        self.assertNotEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)
        self.assertFalse(policy._returning_to_town)
        self.assertIsNone(dive_floor.climb_dungeon(policy))
        self.assertFalse(destruction_use.gap_here(policy, self.first, {"destruction"}))
        # The staff list read: the means hold, nothing returns.
        policy._me_device_lists = copy.deepcopy(self.lists)
        self.assertTrue(destruction_use.holds_means(policy, self.first))
        decided = self._decide(policy, 2)
        self.assertNotIn(RECALL_KEY, [key for key, _reason in decided])
        self.assertFalse(policy._returning_to_town)
        self.assertIsNone(dive_floor.climb_dungeon(policy))

    def test_a_list_never_read_is_no_means(self):
        from hengbot import destruction_use, me_powers_refresh

        policy = self._restarted()
        policy._me_power_resume_attempts = {kind: (me_powers_refresh.RESUME_READ_ATTEMPTS, 1)
                                            for kind in me_powers_refresh.KINDS}
        policy._decision_sequence = 1 + me_powers_refresh.RESUME_RETRY_DECISIONS
        self.assertFalse(destruction_use.means_unread(policy, self.first))
        self.assertEqual(destruction_use.gap_here(policy, self.first, {"destruction"}),
                         frozenset({"destruction"}))
        # No climb held yet: the floor is the means-spent return's (on the Mountain the climb's
        # observe holds the climb instead, tests/test_n1c_221_restart_climb_1123_recorded.py).
        self.assertTrue(destruction_use.means_spent(policy, self.first))


if __name__ == "__main__":
    unittest.main()
