"""A staff-sequence key another rung replaces is no attempt.

n1-b life-320 (2026-11-06 01:38:26) and life-329 (20:30:43): after the Tower's
recharge the sequence chose ``G`` to absorb a wand, and the spectator's
Magic-Eater list refresh (cli._request_due_me_powers_refresh) replaced it on
three boards with ``bA``, ``bB`` and ``bC``.  Each unposted ``G`` counted as a
failed absorb, so the fourth board stopped as absorb-no-progress and
quest:blocked:me-staff.

Replayed on the n1-c life-128 fourth-absorb visit
(tests/test_n1c_stops_1104_recorded.py), whose last board absorbs a Staff of
Speed: the refresh, latched by the CLI's own timer, takes three boards and the
absorb follows with its attempt count untouched.  Since owner 2026-11-07
(every copy of an absorb_after_charge kind is absorbed) the carried Teleport
Other wand, its kind absorbed already, is that board's first absorb; the
attempts are counted on whichever key the sequence absorbs first.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot import cli, me_staff_sequence
from hengbot.me_powers_refresh import REFRESH_REASON
import test_n1c_stops_1104_recorded as _n1c_stops
from tests.support import recorded as executor_pins



class AbsorbUnderRefreshTest(executor_pins.ProductionHarness):
    load = _n1c_stops.TownStops.load

    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def at_the_absorb(self):
        """The fourth-absorb visit up to its last board, as that test declares it."""
        policy, _recorded, steps = self.load("fourth-absorb")
        record = me_staff_sequence.state(policy)
        record.pending = ("absorb", (("staff:22", record.absorbed["staff:22"]),))
        for entry, supply in steps[:-1]:
            policy.choose_key(supply())
            if entry["key"]:
                policy.confirm_key_posted(entry["key"])
        board = steps[-1][1]
        first = me_staff_sequence._absorbable(policy, board())[0][0]
        return policy, record, board, ("absorb", first)

    def test_refresh_boards_do_not_spend_absorb_attempts(self):
        policy, record, board, absorb = self.at_the_absorb()
        # DECLARED CONSTRUCTED: the spectator's lists are due (its wall clock).
        spectator = SimpleNamespace(magic_eater_refresh_due=lambda _interval: True)
        chosen = []
        latch = None
        for _ in range(3):
            snapshot = board()
            # The board's supply restores the journal's CLI latches; the
            # refresh latch the CLI set here lives on across these boards.
            if latch is None:
                cli._request_due_me_powers_refresh(policy, spectator, 100.0, 0.0, 600.0)
            else:
                policy._me_power_refresh_pending = latch
            key = policy.choose_key(snapshot)
            latch = policy._me_power_refresh_pending
            chosen.append((key, policy.last_reason))
            policy.confirm_key_posted(key)
        self.assertEqual(chosen, [("bA", REFRESH_REASON), ("bB", REFRESH_REASON),
                                  ("bC", REFRESH_REASON)])
        self.assertEqual(record.attempts.get(absorb, 0), 0)
        self.assertIsNone(record.pending)
        # Recorded live: '' quest:blocked:me-staff (absorb-no-progress).
        key = policy.choose_key(board())
        self.assertEqual(policy.last_reason, me_staff_sequence.ABSORB_REASON)
        self.assertTrue(key.startswith("G"), key)
        self.assertIsNone(record.failure)
        # Posted, the absorb is one attempt and its board settles it.
        policy.confirm_key_posted(key)
        self.assertEqual(record.attempts[absorb], 1)
        self.assertEqual(record.pending[0], "absorb")

    def test_posted_absorbs_still_meet_the_attempt_limit(self):
        policy, record, board, absorb = self.at_the_absorb()
        for _ in range(me_staff_sequence.ATTEMPT_LIMIT):
            key = policy.choose_key(board())
            self.assertTrue(key.startswith("G"), key)
            policy.confirm_key_posted(key)
        self.assertEqual(policy.choose_key(board()), "")
        self.assertEqual(record.failure, f"absorb-no-progress:{absorb[1]}")


if __name__ == "__main__":
    unittest.main()
