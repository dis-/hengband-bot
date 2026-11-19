"""n1-a life-531 2026-11-19 14:17:54, town:blocked:overweight-home-unreachable (bot f5861884e).

The Lv50 warrior came home at 221.8 lb over a 190.0 lb limit with loot waiting on
identification or sale (an Olog double chain mail 25.0 lb, hard leather armour, a shield, a
helm, a digger), 38 Teleportation scrolls it carried back from the dungeon (19.0 lb), and a
full Home.  The full-Home relief sold Home wares on round trips (rows 15-27); after the
shield's sale (row 27) the Home had a free slot and the Olog mail was the overload's deposit.

Then an equipment transaction (swap the worn Ring of Slaying) charged Home passes under the
equipment allowance (CALIBRATION_HOME_VISIT_LIMIT, 300): its approach on rows 28 and 29
(neither decision posted that approach) and, on row 32, the leave of the Home where it had
taken the ring off and deferred the deposit to identification.  That deferral ended the
equipment work, the ordinary bound (TOWN_STOP_PASS_LIMIT, 3) applied again, and the three
passes -- none of them a weight deposit -- blocked Home: row 33 stopped as
overweight-home-unreachable at the Home entrance (45,123) with a deposit Home had room for.

Owner 2026-09-03: only a deposit that really fails is a stop; owner 2026-11-15
「必要品だけで重さ超過なら今回買った品を要る分だけ自宅に預けて出発」: the overweight character
deposits and departs.  The passes charged under the equipment allowance are that work's
(``TownVisitLedger.allowance_passes``); the ordinary bound of the Home work after it counts
only its own (``_home_unsatisfied_passes``), so row 33 enters Home for the weight deposit.

Recorded: the stop's town-arrival checkpoint and all 34 journal rows
(tests/extract_n1a_531_overweight_home_1119_fixture.py).  Rows 0-32 are decided through the
public choose_key and compared with the record.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import STORE_HOME, TOWN_STOP_PASS_LIMIT
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-overweight-home-1119"
STOP_ROW = 33
HOME_ENTRANCE = (45, 123)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class OverweightHomeAfterEquipmentAllowanceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:STOP_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.policy, cls.board = policy, steps[STOP_ROW][1]()
        ledger = policy._town_visit_ledger
        cls.before = dict(
            passes=ledger.unsatisfied_passes[STORE_HOME],
            allowance=ledger.allowance_passes[STORE_HOME],
            limit=policy._town_store_visit_limit(STORE_HOME),
            counted=policy._home_unsatisfied_passes(),
            blocked=STORE_HOME in ledger.blocked_stores,
            exhausted=policy._overweight_home_bound_exhausted(),
            outstanding=policy._outstanding_equipment_work(),
        )
        cls.decided = (policy.choose_key(cls.board), policy.last_reason,
                       policy._town_blocked_reason)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_rows_before_the_stop_replay_as_recorded(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[STOP_ROW]["reason"], "town:blocked:overweight-home-unreachable")

    def test_the_passes_were_the_equipment_allowances(self):
        policy, board = self.policy, self.board
        self.assertEqual((board.player.position.y, board.player.position.x), HOME_ENTRANCE)
        self.assertTrue(policy._inventory_overweight(board))
        self.assertFalse(policy._home_is_full(board))
        self.assertIsNotNone(policy._find_home_deposit(board))
        # Before: three passes against the ordinary bound, Home blocked, the stop.
        self.assertEqual(self.before, dict(
            passes=3, allowance=2, limit=TOWN_STOP_PASS_LIMIT, counted=1,
            blocked=False, exhausted=False, outstanding=False))

    def test_the_overweight_character_enters_home_to_deposit(self):
        self.assertEqual(self.decided, ("5", "home:weight-overload-deposit", None))


if __name__ == "__main__":
    unittest.main()
