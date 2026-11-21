"""A worn NO_AC piece (宵闇のローブ) is swapped out in town before any departure.

Owner 2026-11-21 (verbatim): 「AC0では打撃を受けると即死抽選がある。優先対処。」.  n1-b life-411 left town
in the robe again at 12:41: no loadout search had run on any visit since 05:51.  The character
sheet refused every calibration while the robe was worn (character_sheet
``unsupported-ac-interaction``: NO_AC zeroes the AC, so the constant beyond the gear cannot be read),
and with no calibration the optimizer answered calibration-required on every visit, so the search
that leaves NO_AC out never ran and no swap took the robe off.

Now the sheet calibrates with a worn NO_AC piece (the AC constant taken as 0), the search runs and
its swap takes the robe off; and the town's Word of Recall waits while one is worn.

Recorded: n1-b's town visit of 12:41:04 (tests/fixtures/n1b-411-robe-town-1121), replayed with the
calibration the live process held (none: ``adopt_recorded_calibration=False``); and its 11:26:08
visit (tests/fixtures/n1b-411-twilight-robe-1121), replayed to its recall read (row 142).

DECLARED CONSTRUCTED: the dump the C screen of row 11 wrote is the arrival's dump file (the robe was
worn on both, nothing changed between them), its modification time set after the request.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import no_ac_recall
from hengbot.policy import staged_prompt_chain_matches
from hengbot.equipment_rules import TR_NO_AC
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
DUMP_ROW = 11  # town:character-dump


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1b411RobeTownRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def load(self, name):
        policy, _journal, steps = load(FIXTURES / name, Path(self.scratch.name) / name,
                                       adopt_recorded_calibration=False)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        return policy, steps

    @staticmethod
    def decide(policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            return policy.choose_key(board)

    def test_the_sheet_calibrates_and_the_swap_takes_the_robe_off(self):
        policy, steps = self.load("n1b-411-robe-town-1121")
        self.assertIsNone(policy._character_calibration)
        self.assertEqual(policy._calibration_unavailable_reason, "unsupported-ac-interaction")
        for recorded, supply in steps[:DUMP_ROW + 1]:
            board = supply()
            key = self.decide(policy, board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            post(policy, key)
        self.assertTrue(no_ac_recall.worn(board))
        now = time.time_ns() + 10 ** 9  # DECLARED: the dump written for row 11's C screen
        os.utime(policy._character_dump_path, ns=(now, now))
        recorded, supply = steps[DUMP_ROW + 1]
        board = supply()
        key = self.decide(policy, board)
        self.assertIsNotNone(policy._character_calibration)  # the sheet read with the robe worn
        self.assertNotIn("recall", policy.last_reason)
        post(policy, key)
        recorded, supply = steps[DUMP_ROW + 2]
        self.decide(policy, supply())
        # The search ran: its swap heads for the Home (the record walked to the next town).
        self.assertEqual(policy.last_reason, "equipment-transaction:travel-home")
        robe = next(owned for owned in policy._equipment_catalog.items
                    if owned.origin == "equipped" and TR_NO_AC in owned.flags)
        session = policy._equipment_transaction_session
        actions = [(action.kind, action.item_id) for action in session.plan.actions]
        self.assertTrue(any(kind in ("takeoff", "deposit") and item == robe.id
                            for kind, item in actions), actions)
        self.assertTrue(any(kind == "equip" for kind, _item in actions), actions)

    def test_no_departure_in_the_robe(self):
        policy, steps = self.load("n1b-411-twilight-robe-1121")
        for recorded, supply in steps[:142]:
            key = self.decide(policy, supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            post(policy, key)
        recorded, supply = steps[142]
        self.assertEqual(recorded["reason"], "town:recall-to-angband")
        board = supply()
        self.assertTrue(no_ac_recall.worn(board))
        self.decide(policy, board)
        self.assertEqual(policy.last_reason, "town:blocked:no-ac-worn")


if __name__ == "__main__":
    unittest.main()
