"""The town's errand stores are served after the recall circuit's leg is chosen (n1-b life-411).

Owner 2026-11-17: 「他の町に買いに行く。」 (recall_stockout_travel).  Live (n1-b life-411,
Magic-Eater Lv50, 126,856 gold, the Outpost, 2026-11-18 07:50,
tests/extract_n1b_411_crosstown_approach_1118_fixture.py): the Temple's Word of Recall
ran out (rows 11-12, ``town:cross-town-recall-stockout``) and the first board outside
chose the inn leg to Telmora (row 13).  At the inn the visit's errands (the Weapon
Smiths, the Black Market) answered first, as the leg waits for them; but every errand
store page judged the stock-out again and left at once (row 15 the Weapon Smiths,
row 53 the Black Market), the leg was chosen again, the errand walked back to its store,
and the town ended ``town:blocked:repetition`` (loop-detected).

Now a store page of the town whose stock-out already chose the leg
(``recall_stockout_travel.leg_chosen_here``) serves its own errand.

DECLARED CONSTRUCTED: the inn-side board of row 14 with the Weapon Smiths and the Black
Market recorded as attempted (their errands served), for the leg taken afterwards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import recall_stockout_travel
from hengbot.model import STORE_BLACK, STORE_TEMPLE, STORE_WEAPON
from support.town_arrival_fixture import load
from test_bm_tour_loop_1117_recorded import post

FIXTURE = (Path(__file__).with_name("fixtures") / "n1b-411-crosstown-approach-1118"
           / "n1b-411-0749")
STOCKOUT_ROW = 12
LEG_ROW = 13
INN_SIDE_ROW = 14
WEAPON_ROW = 15
BLACK_ROW = 53
TELMORA = 1


class CrossTownApproach1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Rows 0-13 posted as recorded: the leg to Telmora chosen."""
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        cls.mismatches = []
        for row, supply in steps[:INN_SIDE_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                cls.mismatches.append((row["row"], key, policy.last_reason))
            post(policy, board, entry["key"], before)
        cls.after_leg = policy
        cls.recorded = recorded
        cls.steps = steps

    def policy(self):
        return copy.deepcopy(self.after_leg)

    def test_the_stockout_and_the_leg_replay_as_recorded(self):
        self.assertEqual(self.mismatches, [])
        self.assertEqual(self.recorded[STOCKOUT_ROW]["reason"],
                         recall_stockout_travel.LEAVE_REASON)
        self.assertEqual(self.recorded[LEG_ROW]["reason"],
                         f"town:cross-town-shopping:travel-{TELMORA}")
        circuit = recall_stockout_travel.circuit(self.after_leg)
        self.assertEqual((circuit.tried_towns, circuit.target_town_id), ([0], TELMORA))

    def test_the_weapon_smiths_page_serves_its_errand(self):
        policy = self.policy()
        policy.choose_key(self.steps[INN_SIDE_ROW][1]())  # the errand's travel to it
        board = self.steps[WEAPON_ROW][1]()
        self.assertEqual(board.store.store_type, STORE_WEAPON)
        self.assertEqual(self.recorded[WEAPON_ROW]["reason"], recall_stockout_travel.LEAVE_REASON)
        self.assertTrue(recall_stockout_travel.leg_chosen_here(policy, board))
        policy.choose_key(board)
        # Live: ("\x1b", "town:cross-town-recall-stockout").
        self.assertEqual(policy.last_reason, "shop:in-store-buy")
        self.assertEqual(recall_stockout_travel.circuit(policy).target_town_id, TELMORA)

    def test_the_black_market_page_does_not_judge_the_stockout_again(self):
        policy = self.policy()
        board = self.steps[BLACK_ROW][1]()
        self.assertEqual(board.store.store_type, STORE_BLACK)
        self.assertEqual(self.recorded[BLACK_ROW]["reason"], recall_stockout_travel.LEAVE_REASON)
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, recall_stockout_travel.LEAVE_REASON)
        self.assertEqual(recall_stockout_travel.circuit(policy).target_town_id, TELMORA)

    def test_the_stockout_page_itself_still_leaves(self):
        """Before the leg is chosen the Temple's page judges the stock-out as before."""
        policy = self.policy()
        # The circuit as the stock-out page left it (start: no leg chosen yet).
        recall_stockout_travel.circuit(policy).target_town_id = None
        temple = self.steps[STOCKOUT_ROW][1]()
        self.assertEqual(temple.store.store_type, STORE_TEMPLE)
        self.assertFalse(recall_stockout_travel.leg_chosen_here(policy, temple))

    def test_the_leg_follows_the_served_errands(self):
        policy = self.policy()
        board = self.steps[INN_SIDE_ROW][1]()
        # DECLARED CONSTRUCTED: both errand stores served.
        for store in (STORE_WEAPON, STORE_BLACK):
            policy._set_town_store_attempted(store, board.turn, "constructed")
            policy._town_visit_ledger.nonhome_attempted_without_effect[store] = (
                policy._town_observable_effect_state(board))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, f"town:cross-town-shopping:travel-{TELMORA}")
        self.assertTrue(key.endswith("m" + chr(ord("a") + TELMORA)), key)


if __name__ == "__main__":
    unittest.main()
