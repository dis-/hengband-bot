"""CONSTRUCTED detection seams from row 3691; no surviving board replay.

Gold/position/turn/level come from the compact hashed decision fixture.
Inventory, empty Home knowledge, and supplier prices are constructed explicitly.
The incident's supplier price is unknown: the pin must observe/buy, not assert
that a historical shelf existed. Real cycle repair, terminal routing, restart
and purchase selection run; no result collaborators are mocked.
"""
import tests  # noqa: F401
import unittest
from dataclasses import replace
from policy_fixtures import item, store_item
from test_goldburn_shopping_constructed import board
from hengbot.model import STORE_HOME, STORE_ALCHEMIST, STORE_BLACK, StoreState, TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, DUNGEON_YEEK_CAVE
from hengbot.policy import HengbotPolicy


def detection_offer(price):
    return store_item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, price=price)


def supplier(policy, snap, price, store=STORE_ALCHEMIST):
    policy._town_supplier_stock[store] = StoreState(store, [detection_offer(price)])
    policy._town_supplier_stock_observations[store] = (snap.town_id, snap.turn)


class GoldburnDetectionConstructedTest(unittest.TestCase):
    def test_cycle_break_655_unknown_price_keeps_detection_acquisition(self):
        snap = board(1)
        policy = HengbotPolicy()
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertFalse(policy._town_restock_suppressed)
        self.assertEqual(policy._next_required_store_type(snap), STORE_ALCHEMIST)
        # The first divergence ends this pin. Construct the next supplier page
        # separately to prove the same gold can buy one scroll through production.
        offered = replace(snap, store=StoreState(STORE_ALCHEMIST, [detection_offer(100)]))
        self.assertTrue(policy._next_purchase(offered).is_treasure_detection_scroll)

    def test_cycle_break_affordable_detection_keeps_supplier(self):
        snap = board(1)
        policy = HengbotPolicy()
        supplier(policy, snap, 100)
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_home_detection_vetoes_exception_and_rearms_home(self):
        snap = board(1)
        policy = HengbotPolicy()
        supplier(policy, snap, 1000)
        policy._home_knowledge_items = [item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)]
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)

    def test_carried_detection_never_becomes_scavenge(self):
        snap = replace(board(1), inventory=[item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)])
        policy = HengbotPolicy()
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "mine")
        self.assertEqual(policy._planned_mining_runs, 1)

    def test_exception_requires_known_price_above_gold(self):
        for price, allowed in [(None, False), (100, False), (655, False), (656, True)]:
            with self.subTest(price=price):
                policy = HengbotPolicy()
                snap = board(1)
                if price is not None:
                    supplier(policy, snap, price)
                policy._break_town_cycle(snap)
                self.assertEqual(policy._fundraising_mode, "scavenge" if allowed else "prepare")

    def test_cheapest_observed_supplier_vetoes_exception(self):
        policy = HengbotPolicy()
        snap = board(1)
        supplier(policy, snap, 1000)
        supplier(policy, snap, 100, STORE_BLACK)
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_exhausted_home_alchemist_do_not_authorize_scavenge(self):
        policy = HengbotPolicy()
        snap = board(1)
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted.update({STORE_HOME: snap.turn, STORE_ALCHEMIST: snap.turn})
        policy._town_terminal_transitions(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

    def test_exhausted_suppliers_allow_only_unaffordable_exception(self):
        policy = HengbotPolicy()
        snap = board(1)
        supplier(policy, snap, 1000)
        policy._fundraising_mode = "prepare"
        policy._town_store_attempted.update({STORE_HOME: snap.turn, STORE_ALCHEMIST: snap.turn})
        policy._town_terminal_transitions(snap)
        self.assertEqual(policy._fundraising_mode, "scavenge")

    def test_restart_without_known_price_does_not_reconstruct_scavenge(self):
        snap = replace(board(1), floor_key=(DUNGEON_YEEK_CAVE, 1, 0), town_flag=False, angband_recall_unlocked=True)
        policy = HengbotPolicy()
        policy.prime(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_home_other_page_knowledge_vetoes_exception(self):
        policy = HengbotPolicy()
        snap = replace(board(1), store=StoreState(STORE_HOME, []))
        supplier(policy, snap, 1000)
        policy._home_knowledge_items = [item("a", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)]
        self.assertFalse(policy._detectionless_scavenge_allowed(snap))
        self.assertEqual(policy._settle_fundraising_detection(snap), STORE_HOME)
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_observed_empty_shelf_waits_for_existing_restock_route(self):
        policy = HengbotPolicy()
        snap = board(1)
        policy._town_supplier_stock[STORE_ALCHEMIST] = StoreState(STORE_ALCHEMIST, [])
        policy._town_supplier_stock_observations[STORE_ALCHEMIST] = (snap.town_id, snap.turn)
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._town_restock_waiting_for, (STORE_ALCHEMIST,))
        self.assertFalse(policy._town_restock_suppressed)

    def test_zero_gold_known_price_allows_the_explicit_exception(self):
        snap = replace(board(1), player=replace(board(1).player, gold=0))
        policy = HengbotPolicy()
        supplier(policy, snap, 100)
        policy._break_town_cycle(snap)
        self.assertEqual(policy._fundraising_mode, "scavenge")
