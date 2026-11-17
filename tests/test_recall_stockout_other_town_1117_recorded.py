"""Word of Recall out of stock: buy it in another town (owner 2026-11-17).

Owner 2026-11-17, verbatim: 「他の町に買いに行く。」, replacing 2026-09-13
「帰還の巻物が品切れなら採掘して待つ。他の街までいかない。」; and 「念のため。すべての町に
ズルは含まない。」.

Recorded: n1-c life-216 (Magic-Eater, 2,566,788 gold) at the Outpost on 2026-11-17
15:04: the Temple sold its last two Word of Recall (7 of 11 carried), the Alchemist had
none, and the Temple page after the purchase answered ``town:recall-stockout-mining``
(ESC, then the one-run Yeek Cave mining time-pass).  The pages are decided on the same
character's 08:46 recall-arrival policy (tests/extract_recall_stockout_other_town_1117_
fixture.py; DECLARED LOSS: the 15:04 arrival checkpoint had rotated away).  On that
policy the code before this change answers the Temple page as live
(``town:recall-stockout-mining``, mining plan set).

Now the page leaves for the circuit (recall_stockout_travel): the visited inn towns
Telmora, Morivant and Angwil (1, 2, 3), never Zul (4, visited too).

DECLARED CONSTRUCTED: the same pages re-labelled as Telmora's (town 1) and Angwil's
(town 3), later by 10 turns and poorer by the 1,000-gold inn fares; the circuit with
Telmora and Morivant already tried; and the Temple page with 2,000 gold (the fare not
covered).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import recall_stockout_travel
from hengbot.policy import staged_prompt_chain_matches
from hengbot.model import STORE_ALCHEMIST, STORE_TEMPLE, parse_snapshot
from hengbot.policy_constants import CROSS_TOWN_TOWN_IDS, LEAVE_STORE_KEY, ZUL_TOWN_ID
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "recall-stockout-other-town-1117"
ARRIVAL = FIXTURE / "n1c-216-0846"
ALCHEMIST, TEMPLE, OUTSIDE = range(3)
TRAVEL_MACRO_PREFIX = "\x1b`n"  # the travel command to the inn
GOLD = 2566788


class RecallStockoutOtherTown1117RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.arrival, _journal, _steps = load(ARRIVAL, Path(scratch.name))
        cls.raw = [json.loads(line) for line in lzma.decompress(
            (FIXTURE / "pages-1504.jsonl.xz").read_bytes()).decode("utf-8").splitlines()]

    def policy(self):
        return copy.deepcopy(self.arrival)

    def board(self, policy, which, *, town=None, gold=None):
        raw = copy.deepcopy(self.raw[which])
        if town is not None:
            raw["floor"]["town_id"] = town
            raw["turn"] += 10 * town  # each town is visited later,
            raw["player"]["gold"] -= 1000 * town  # after a 1,000-gold inn fare each
        if gold is not None:
            raw["player"]["gold"] = gold
        return parse_snapshot(raw, policy._monrace_knowledge)

    def shop(self, policy, *, town=None, gold=None):
        """The Alchemist page, then the Temple page: the Temple's decision."""
        for which in (ALCHEMIST, TEMPLE):
            board = self.board(policy, which, town=town, gold=gold)
            key = self.decide(policy, board)
        return key, policy.last_reason, board

    def outside(self, policy, town=None):
        policy.observe_store_screen(None)
        key = self.decide(policy, self.board(policy, OUTSIDE, town=town))
        return key, policy.last_reason

    @staticmethod
    def decide(policy, board):
        """The public decision, posted as the live CLI posts it."""
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        return key

    def test_recorded_pages(self):
        policy = self.policy()
        alchemist = self.board(policy, ALCHEMIST)
        temple = self.board(policy, TEMPLE)
        self.assertEqual((alchemist.store.store_type, temple.store.store_type),
                         (STORE_ALCHEMIST, STORE_TEMPLE))
        self.assertEqual((temple.town_id, temple.player.gold), (0, GOLD))
        self.assertFalse(any(item.is_recall_scroll for item in alchemist.store.items))
        self.assertFalse(any(item.is_recall_scroll for item in temple.store.items))
        self.assertIn(ZUL_TOWN_ID, temple.visited_town_ids)

    def test_the_stockout_page_leaves_for_another_town_not_the_time_pass(self):
        policy = self.policy()
        key, reason, board = self.shop(policy)
        self.assertTrue(policy._recall_stockout_persists(board))
        # Live: ("\x1b", "town:recall-stockout-mining").
        self.assertEqual((key, reason), (LEAVE_STORE_KEY, recall_stockout_travel.LEAVE_REASON))
        circuit = policy._cross_town_shopping
        self.assertEqual(circuit.blocking_categories, ("recall",))
        self.assertEqual(circuit.trigger_town_id, 0)
        self.assertEqual(circuit.candidate_order, (1, 2, 3))
        self.assertEqual(circuit.tried_towns, [0])
        self.assertFalse(policy._recall_stockout_mining_plan)
        self.assertIsNone(policy._fundraising_mode)
        self.assertNotIn("fallback", policy._cross_town_shopping_funds)

    def test_the_first_board_outside_takes_the_inn_to_the_cheapest_untried_town(self):
        policy = self.policy()
        self.shop(policy)
        key, reason = self.outside(policy)
        self.assertTrue(key.startswith(TRAVEL_MACRO_PREFIX))
        self.assertEqual(reason, "town:cross-town-shopping:travel-1")
        self.assertEqual(policy._cross_town_shopping.target_town_id, 1)
        self.assertEqual(policy._cross_town_shopping.tried_towns, [0])

    def test_the_next_town_out_of_stock_too_moves_the_circuit_on(self):
        policy = self.policy()
        self.shop(policy)
        self.outside(policy)  # the inn leg to Telmora
        key, reason, _board = self.shop(policy, town=1)
        self.assertEqual((key, reason), (LEAVE_STORE_KEY, recall_stockout_travel.LEAVE_REASON))
        self.assertEqual(policy._cross_town_shopping.tried_towns, [0, 1])
        self.assertFalse(policy._recall_stockout_mining_plan)

    def test_the_last_town_out_of_stock_falls_back_to_the_time_pass(self):
        policy = self.policy()
        self.shop(policy)
        # DECLARED CONSTRUCTED: Telmora and Morivant were tried out of stock and the inn
        # leg to Angwil was taken.
        policy._cross_town_shopping.tried_towns.extend((1, 2))
        policy._cross_town_shopping.target_town_id = 3
        key, reason, _board = self.shop(policy, town=3)
        self.assertEqual((key, reason), (LEAVE_STORE_KEY, "town:recall-stockout-mining"))
        self.assertIsNone(policy._cross_town_shopping)
        self.assertTrue(policy._recall_stockout_mining_plan)
        self.assertEqual(policy._fundraising_mode, "prepare")
        funds = policy._cross_town_shopping_funds
        self.assertEqual((funds["fallback"], funds["why"], funds["tried_towns"]),
                         (recall_stockout_travel.FALLBACK, "all-towns-tried", [0, 1, 2, 3]))

    def test_a_town_change_forgets_the_old_town_shelves(self):
        policy = self.policy()
        self.shop(policy)
        self.outside(policy)
        self.outside(policy, 1)
        # Telmora's suppliers are not seen yet: no stock-out is declared there.
        self.assertEqual(policy._town_supplier_stock, {})
        self.assertFalse(policy._recall_stockout_persists(self.board(policy, OUTSIDE, town=1)))

    def test_the_fare_not_covered_falls_back_to_the_time_pass(self):
        policy = self.policy()
        key, reason, _board = self.shop(policy, gold=2000)
        self.assertEqual((key, reason), (LEAVE_STORE_KEY, "town:recall-stockout-mining"))
        self.assertTrue(policy._recall_stockout_mining_plan)
        self.assertEqual(policy._cross_town_shopping_funds["why"], "funds")

    def test_zul_is_never_a_town_of_the_trips(self):
        policy = self.policy()
        self.assertNotIn(ZUL_TOWN_ID, CROSS_TOWN_TOWN_IDS)
        self.assertEqual(CROSS_TOWN_TOWN_IDS, frozenset({0, 1, 2, 3}))
        board = self.board(policy, TEMPLE)
        self.assertEqual(policy._cross_town_candidate_order(board), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
