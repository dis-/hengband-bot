"""ROOT-FIX S2-d part 1 rest: Home withdrawal and the remaining declarations.

The approach rungs (``_shopping_approach_key`` and its #1/#2 call sites) walk
to Home for the filed visit request.  A WITHDRAW request whose item the
current Home catalogue no longer holds is refused BEFORE the walk with
``reservation-unavailable`` (#63: the in-Home exits learned it only after
entering).  Also declared here: the device identification
(``_town_device_processing_key``), the entrance deposit
(``home-atomic-deposit``), the open-page deposit / Home-full relief
(``_open_home_deposit_key``) and the Home-full carry-over
(``_defer_home_full_deposit``).  All SHADOW until the S2 ENFORCE flip.

Board: the CONSTRUCTED goldburn seam (row 3512, Telmora; see
test_goldburn_shopping_constructed) with DECLARED CONSTRUCTED Home catalogue,
visit request and carried items per case.
"""

import tests  # noqa: F401

import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.model import (
    STORE_GENERAL, STORE_HOME, SV_SCROLL_IDENTIFY, SV_STAFF_IDENTIFY, TVAL_SCROLL,
    TVAL_STAFF, TVAL_WAND,
)
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import REFUSAL_SERVERS, Server
from policy_fixtures import item
from test_goldburn_shopping_constructed import board

STAFF = item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, name="Identify", charges=10)


def withdraw_policy(*, stored, current=True, kind=HomeVisitKind.WITHDRAW,
                    store_type=STORE_HOME):
    policy = HengbotPolicy()
    signature = policy._item_signature(STAFF)
    policy._home_knowledge_current = current
    policy._home_knowledge_items = (STAFF,) if stored else ()
    policy._shopping_approach_store_type = store_type
    policy._home_visit.request = HomeVisitRequest(
        kind, "home-errand:identify-staff",
        signature if kind == HomeVisitKind.WITHDRAW else None,
        address=signature if kind == HomeVisitKind.WITHDRAW else None)
    return policy


def entry(policy, snap, rung, producer=lambda: "walk", family=None):
    policy._build_grid_index(snap)
    policy._begin_map_predicate_cache(snap)
    policy._decision_sequence += 1
    policy._decision_terminal_admissions = []
    terminal = town_terminal.rung_terminal(policy, rung, snap)
    key = policy._town_producer_entry(rung, producer, family=family)
    return terminal, key, policy._decision_terminal_admissions


class HomeWithdrawTerminalTest(unittest.TestCase):
    def test_catalogue_without_the_item_refuses_before_the_walk(self):
        for rung in ("_shopping_approach_key", "_shopping_approach_key#1",
                     "_shopping_approach_key#2"):
            with self.subTest(rung=rung):
                decl = town_terminal.TERMINALS[rung]
                with patch.dict(town_terminal.TERMINALS, {
                        rung: decl._replace(mode=town_terminal.SHADOW)}):
                    terminal, key, rows = entry(
                        withdraw_policy(stored=False), board(), rung,
                        family="store-router" if rung == "_shopping_approach_key" else None)
                self.assertEqual(terminal.terminal_id, "home-withdraw")
                self.assertEqual(key, "walk")  # SHADOW: recorded only
                row, = rows
                self.assertEqual((row["codes"], row["mode"]),
                                 (["reservation-unavailable"], "shadow"))
        self.assertIn(Server("shop-buy", "identify-staff"),
                      REFUSAL_SERVERS["reservation-unavailable"])
        self.assertIn(Server("cross-town"), REFUSAL_SERVERS["reservation-unavailable"])

    def test_default_mode_refuses_the_missing_item_before_walking(self):
        for rung in ("_shopping_approach_key", "_shopping_approach_key#1",
                     "_shopping_approach_key#2"):
            with self.subTest(rung=rung):
                terminal, key, rows = entry(
                    withdraw_policy(stored=False), board(), rung,
                    family="store-router" if rung == "_shopping_approach_key" else None)
                self.assertEqual(terminal.terminal_id, "home-withdraw")
                self.assertIsNone(key)
                row, = rows
                self.assertEqual((row["codes"], row["mode"]),
                                 (["reservation-unavailable"], "enforce"))

    def test_stored_item_admits(self):
        terminal, key, rows = entry(withdraw_policy(stored=True), board(),
                                    "_shopping_approach_key#2")
        self.assertEqual(terminal.terminal_id, "home-withdraw")
        self.assertEqual((key, rows), ("walk", []))

    def test_stale_catalogue_admits(self):
        # Control: without a current catalogue the walk is the only way to know.
        terminal, key, rows = entry(withdraw_policy(stored=False, current=False),
                                    board(), "_shopping_approach_key#2")
        self.assertEqual(terminal.terminal_id, "home-withdraw")
        self.assertEqual(rows, [])

    def test_other_requests_and_stores_have_no_terminal(self):
        scan = withdraw_policy(stored=False, kind=HomeVisitKind.SCAN)
        self.assertIsNone(town_terminal.rung_terminal(scan, "_shopping_approach_key#2", board()))
        shop = withdraw_policy(stored=False, store_type=STORE_GENERAL)
        self.assertIsNone(town_terminal.rung_terminal(shop, "_shopping_approach_key#2", board()))
        inside = withdraw_policy(stored=False)
        snap = board()
        self.assertIsNone(town_terminal.rung_terminal(
            inside, "_shopping_approach_key#2",
            replace(snap, store=object())))


class DeviceIdentificationTerminalTest(unittest.TestCase):
    def device_board(self, *, scroll):
        wand = item("a", TVAL_WAND, 1, aware=False, known=False, name="Wand")
        inventory = [wand] + ([item("b", TVAL_SCROLL, SV_SCROLL_IDENTIFY,
                                    name="Identify")] if scroll else [])
        return replace(board(), inventory=inventory)

    def test_body_and_verdict_agree(self):
        for scroll in (True, False):
            with self.subTest(scroll=scroll):
                policy = HengbotPolicy()
                snap = self.device_board(scroll=scroll)
                terminal, key, rows = entry(
                    policy, snap, "_town_device_processing_key",
                    lambda: policy._town_device_processing_key(snap))
                self.assertEqual(terminal.terminal_id, "identify-device")
                if scroll:
                    self.assertIsNotNone(key)
                    self.assertEqual(rows, [])
                else:
                    self.assertIsNone(key)
                    row, = rows
                    self.assertEqual(row["codes"], ["no-identification-source"])

    def test_no_device_has_no_terminal(self):
        policy = HengbotPolicy()
        self.assertIsNone(town_terminal.rung_terminal(
            policy, "_town_device_processing_key", replace(board(), inventory=[])))


class HomeDepositRungsTest(unittest.TestCase):
    def test_entrance_deposit_refused_while_a_relief_owns_home(self):
        policy = HengbotPolicy()
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_full_relief = {"town": 1, "deposits": ()}
        terminal, key, rows = entry(policy, board(), "home-atomic-deposit",
                                    lambda: policy._atomic_home_deposit_dispatch_key(
                                        board(), board().player.position),
                                    family="home-visit")
        self.assertEqual(terminal, town_terminal.TerminalRef("home-atomic-deposit", ()))
        self.assertIsNone(key)
        row, = rows
        self.assertEqual(row["codes"], ["home-full-relief-pending"])
        self.assertEqual(REFUSAL_SERVERS["home-full-relief-pending"], (Server("home-visit"),))

    def test_entrance_deposit_admitted_without_a_relief(self):
        policy = HengbotPolicy()
        policy._shopping_approach_store_type = STORE_HOME
        terminal, _key, rows = entry(policy, board(), "home-atomic-deposit", lambda: None,
                                     family="home-visit")
        self.assertEqual(terminal.terminal_id, "home-atomic-deposit")
        self.assertEqual(rows, [])
        other = HengbotPolicy()
        other._shopping_approach_store_type = STORE_GENERAL
        self.assertIsNone(town_terminal.rung_terminal(other, "home-atomic-deposit", board()))

    def test_open_page_terminal_is_the_relief_while_home_is_full(self):
        policy = HengbotPolicy()
        snap = board()
        self.assertIsNone(town_terminal.rung_terminal(policy, "_open_home_deposit_key", snap))
        page = replace(snap, store=replace_store(STORE_HOME))
        self.assertEqual(town_terminal.rung_terminal(policy, "_open_home_deposit_key", page),
                         town_terminal.TerminalRef("home-open-deposit", ()))
        policy._home_full_relief = {"town": 1, "deposits": ()}
        self.assertEqual(town_terminal.rung_terminal(policy, "_open_home_deposit_key", page),
                         town_terminal.TerminalRef("home-full-relief", ()))

    def test_home_full_defer_terminal(self):
        policy = HengbotPolicy()
        self.assertIsNone(town_terminal.rung_terminal(
            policy, "_defer_home_full_deposit", board()))
        policy._home_full_relief = {"town": 1, "deposits": ()}
        self.assertEqual(town_terminal.rung_terminal(
            policy, "_defer_home_full_deposit", board()),
            town_terminal.TerminalRef("home-full-defer", ()))


def replace_store(store_type):
    from hengbot.model import StoreState
    return StoreState(store_type=store_type, items=[], stock_num=0, capacity=0)


if __name__ == "__main__":
    unittest.main()
