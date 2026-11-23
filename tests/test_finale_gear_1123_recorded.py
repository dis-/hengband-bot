"""The finale's equipment conditions judged on the owned gear (n1-c life-221, 2026-11-23).

Owner 2026-11-23 (verbatim): 「装備に関しては★賢者マーリンの魔法の鏡を使用して条件を満たす装備を作れる。
装備最適化が効いてない可能性あり。」  The readiness (angband_finale ``readiness``) reported resist
curse and resist blindness or light missing from the owned gear: the preparation phase stayed idle
(Healing 2 of 30 owned), so its check step's read-only search never ran and ``equipment_owned``
fell back to the worn set.  The 95F exploration keeps the ordinary loadout (owner 2026-11-20 Q9
「上限を外す時に初めて着け替える」), so the worn set itself is not changed here.

Recorded (tests/extract_finale_gear_1123_fixture.py, ``n1c-221-finale-gear-1123``): the
town-arrival checkpoint of 23:27:31 (turn 5072942).  Rows 0-3 are decided through the public
``choose_key`` and compared with the record; row 2 is the visit's first fresh loadout search, which
now also searches the owned gear in the finale's rank once (angband_finale ``owned_report_due``).
The Home holds ★賢者マーリンの魔法の鏡 (artifact 265, RES_CURSE and RES_BLIND).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_prep
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1c-221-finale-gear-1123"
ROWS = 4
MIRROR = "b10bc1308d7b6de9:0"  # ★賢者マーリンの魔法の鏡 at Home (its catalogue signature)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleGear1123RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(TOWN, Path(cls.scratch.name))
        cls.replayed, cls.boards = [], []
        for recorded, supply in steps[:ROWS]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            cls.boards.append(board)
            post(policy, recorded["key"])
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_rows_as_recorded(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)

    def test_the_owned_gear_meets_the_conditions_with_the_mirror(self):
        policy, board = self.policy, self.boards[-1]
        self.assertTrue(angband_finale.preparing(board))
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.IDLE)  # Healing short
        held = angband_finale.memory(policy)
        # Recorded: equipment_owned missing ["resist_blind|resist_lite", "resist_curse"].  The
        # mirror meets both; the owner's gates of 2026-11-24 (「閃光轟音時間以外の耐性を必須とする」)
        # then name the one this Home's gear cannot add with the rest: resist darkness.
        report = held.report
        self.assertEqual(report["equipment_owned"],
                         {"missing": ["resist_dark"], "ready": False, "judged": "owned-search"})
        # The 95F exploration keeps the ordinary loadout (Q9): the worn set still lacks them.
        self.assertEqual(report["equipment_worn"]["missing"],
                         ["resist_blind|resist_lite", "resist_curse"])
        from hengbot.equipment_optimizer import finale_missing
        best = held.owned_best
        self.assertIsNotNone(best)
        self.assertIn(MIRROR, {finale_prep._signature(item.id) for _, item in best.loadout.slots})
        self.assertEqual(finale_missing(best), ("resist_dark",))
        self.assertEqual(finale_prep.set_missing(policy, board, best.loadout, best.metrics),
                         ["resist_dark"])

    def test_searched_once_a_visit(self):
        policy = self.policy
        catalog = policy._equipment_catalog.items
        self.assertFalse(angband_finale.owned_report_due(policy, self.boards[-1], catalog))
        # A piece of the kept set no longer owned: searched again.
        without = [owned for owned in catalog if finale_prep._signature(owned.id) != MIRROR]
        self.assertTrue(angband_finale.owned_report_due(policy, self.boards[-1], without))


if __name__ == "__main__":
    unittest.main()
