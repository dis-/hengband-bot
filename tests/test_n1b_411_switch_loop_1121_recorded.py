"""A restore potion bought and drunk is progress, not a no-progress cycle.

n1-b life-411 stopped 2026-11-21 04:56:58 (bot-96a461c09) with "navigation exhausted" in the
Outpost: at 04:56:51 it entered the Black Market, bought a Restore Intelligence (3,199 gold,
its Intelligence drained), drank it at the door, and the next decision walked into the Black
Market again.  The no-progress cycle guard (``_refuse_no_progress_cycle``) compares the place,
the store and the pack and equipment (gold excluded): the potion bought and drunk left the pack
as it was at the first entry, so the second entry was refused as livelock:exhausted, although
the stat was restored in between.  (The 99F/100F switch did not happen on this visit:
angband_finale.switching is False, the owned equipment lacking *Destruction*; the Home swaps
before it were the optimizer's one change per slot.)

Recorded: that visit's town-arrival checkpoint and its whole journal (tests/
extract_n1b_411_switch_loop_1121_fixture.py), the recorded keys delivered row by row as the game
received them (the restored policy pages the Home before a few recorded withdrawals, rows
20-30: those rows are compared only up to row 19).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-switch-loop-1121"
FAITHFUL_ROWS = 20


class N1b411SwitchLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_the_black_market_again_after_the_restore(self):
        policy = self.policy
        drained = {}
        for recorded, supply in self.steps:
            board = supply()
            drained[recorded["reason"]] = board.player.drained_stats
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if recorded["row"] < FAITHFUL_ROWS:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            if recorded["reason"] == "livelock:exhausted":
                break
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, recorded["key"]):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": recorded["key"]})
        self.assertFalse(angband_finale.memory(policy).switching)
        self.assertIn("int", drained["restore:quaff-int"])
        self.assertEqual(board.player.drained_stats, ())
        self.assertEqual(recorded["key"], "5")
        self.assertEqual((key, policy.last_reason), ("5", "shop:travel:await-entry"))


if __name__ == "__main__":
    unittest.main()
