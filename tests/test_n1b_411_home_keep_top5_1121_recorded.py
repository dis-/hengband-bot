"""n1-b life-411 2026-11-21 01:08: a Home of 239 stacks the cap tidy could not shed.

Recorded: the town arrival of 01:08:34 (turn 11195981; tests/fixtures/
n1b-411-transfer-clear-1121, the incident capture 20261121-010918-town-blocked-survival-
equipment-transfer-clear).  The Home held 239 stacks against the cap of 200 (owner 2026-11-19
「200件（空き40）」), but every stack's fate was to stay: 127 protected (mostly artifacts), 97
ordinary gear within its slot's top ten, 16 supplies; the one room-sale was not enough, the Home
filled to 240 in the visit and a deposit was refused.

Owner 2026-11-21 (verbatim): 「部位ごとに残す数を5位までに減らす」: each slot keeps its top five
ordinary pieces (item_fate.KEPT_RANKS); ranks 6-20 go for room under the existing cheapest-first
order, artifacts stay protected.  Pinned: on the arrival's first board (the Home list current)
the cap tidy's shed fates now cover 49 stacks, enough to bring the 239 under the cap (39 over),
and no artifact or top-five piece is among them.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_cap, item_fate
from hengbot.home_ledger import HOME_KEEP_CAP
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-transfer-clear-1121"


class N1b411HomeKeepTop5RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        _recorded, supply = steps[0]
        cls.board = supply()
        with contextlib.redirect_stdout(io.StringIO()):
            cls.policy.choose_key(cls.board)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_cap_tidy_can_bring_the_home_under_its_cap(self):
        policy, board = self.policy, self.board
        self.assertTrue(policy._home_knowledge_current)
        count = home_cap.stock_count(policy, board)
        self.assertEqual(count, 239)
        shed = [item for item in policy._home_knowledge_items
                if home_cap.sheds(policy, board, item)]
        fates = Counter(item_fate.fate(policy, board, item, item_fate.SHELF) for item in shed)
        self.assertEqual(dict(fates), {item_fate.ROOM_SALE: 49})
        self.assertGreaterEqual(len(shed), count - HOME_KEEP_CAP)
        self.assertLess(count - len(shed), HOME_KEEP_CAP)
        for item in shed:
            self.assertFalse(item.is_artifact, item.name)
            rank = item_fate.gear_rank(policy, board, item)
            self.assertIsNotNone(rank, item.name)
            self.assertGreater(rank, item_fate.KEPT_RANKS, item.name)
            self.assertLessEqual(rank, item_fate.ROOM_RANKS, item.name)
        self.assertEqual(item_fate.KEPT_RANKS, 5)


if __name__ == "__main__":
    unittest.main()
