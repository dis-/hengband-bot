"""The preparation phase's loadout step waits for a whole Home scan (n1-b life-411, 14:26:13).

Recorded (tests/fixtures/n1b-finale-after-oberon-1121, n1-b's town visit of 2026-11-21 14:25:37,
capture n1b-411-20261121-98f-ordinary): the phase entered, checked and reached its supplies step
(rows 0-2) with every count carried.  The swap's deposits (rows 27-32) left the Home scan
incomplete, the step went on to the loadout step on row 34, whose search returned no set
(blocker ``home-scan-incomplete``), and the phase stopped as ``loadout:no-set``: the carry was
released and row 35 deposited the 17 Restore Mana, 15 *Healing* and 20 Resistance just withdrawn,
and the visit left as the ordinary 95F play.  Now the supplies step reads the Home first and the
loadout step runs on a whole scan (a search that met an incomplete one goes back to the
supplies step).

Replayed row by row through the journal; DECLARED CONSTRUCTED: nothing.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import finale_prep
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-finale-after-oberon-1121"


class N1b411FinaleLoadoutScanRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def test_no_stop_and_no_deposit_of_the_supplies_on_an_incomplete_scan(self):
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(policy)
        decided = {}
        for recorded, supply in steps[:36]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided[recorded["row"]] = (key, policy.last_reason)
            if recorded["row"] < 34:
                self.assertEqual(decided[recorded["row"]], (recorded["key"], recorded["reason"]))
                posted = recorded["key"]
            else:
                posted = key
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["row"] >= 34:
                break
        self.assertIsNone(held.stopped)
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        self.assertTrue(finale_prep.carrying(policy))
        self.assertNotEqual(decided[34][1], "home:atomic-deposit")


if __name__ == "__main__":
    unittest.main()
