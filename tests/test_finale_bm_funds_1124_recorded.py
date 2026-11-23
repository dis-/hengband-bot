"""The Black Markets' Restore Mana circuit short of gold, and the gold kept for it (n1-b life-416).

Owner rules: 2026-11-23 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。」 (finale_bm_tour); 2026-11-18 「必要なものは買う。本当に資金枯渇したら採掘で良いが、自宅に
大量の換金用アイテムがあるので先に売る。」 (home_cash_sale, the fundraising run).

Recorded (tests/extract_finale_bm_funds_1124_fixture.py, ``n1b-416-finale-bm-funds-1124``): the
town-arrival checkpoint of the restarted process (2026-11-24 00:49:02, turn 4317991, Angwil).  The
circuit lapped, stayed the night (row 44) and bought one Restore Mana (row 53, 15,724 gold); row 62
bought a Potion of Resistance for 3,930 (``black-market:resistance``, 94 owned against the finale's
20); at row 66 (20,649 gold) the next leg was short of gold and the circuit closed, and from row 73
the town repeated ``town:blocked:finale-not-in-town:restore_mana:funds`` until the loop detector.
Rows before the one decided are replayed through the public ``choose_key`` and post the recorded
key (row 10 differs on any replay: the recorded progress invariant's rewrite is timing-dependent).

DECLARED CONSTRUCTED: ``test_home_cash_wares_are_sold_first`` reads Home's cash sale as pending
(no cash ware was on this Home) and asks the circuit's funds step on row 53's board (before the circuit's own funds step) for one gold
more than held; ``test_a_closed_circuit_is_a_final_stop`` closes the circuit
(an inn the walk cannot reach) on row 73's board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import cli, finale_bm_tour, finale_hold, home_cash_sale
from hengbot.model import SV_POTION_RESISTANCE, TVAL_POTION
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-funds-1124"
RESTORE_MANA_ROW = 53
RESISTANCE_ROW = 62
FUNDS_ROW = 66
STOP_ROW = 73


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleBlackMarketFunds1124RecordedTest(unittest.TestCase):
    def replay(self, rows):
        """(policy, the board of row ``rows``) after the rows before it, as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(scratch.name))
        for recorded, supply in steps[:rows]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        return policy, steps[rows][1]()

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_the_resistance_potion_is_not_bought(self):
        policy, board = self.replay(RESISTANCE_ROW)
        shelf = {item.letter: item for item in board.store.items}
        self.assertEqual((shelf["t"].tval, shelf["t"].sval), (TVAL_POTION, SV_POTION_RESISTANCE))
        key, reason = self.decide(policy, board)

        # Recorded: ('pt\r', 'shop:in-store-buy'), the Potion of Resistance for 3,930.
        self.assertNotEqual(key, "pt\r")
        self.assertIsNone(policy._black_market_optional_purchase(board))
        self.assertTrue(finale_bm_tour.restore_mana_first(policy, board))

    def test_short_of_gold_the_fundraising_run_is_handed_over(self):
        policy, board = self.replay(FUNDS_ROW)
        self.assertEqual(board.player.gold, 20649)

        self.decide(policy, board)

        # Recorded: the circuit closed for its funds, then the town stopped and spun (row 73).
        tour = finale_bm_tour.record(policy)
        self.assertIsNone(tour.closed)
        self.assertGreater(tour.funds_needed, board.player.gold)
        # No cash ware on this Home (home_cash_sale ``wares``): the run, to the gold needed.
        self.assertFalse(home_cash_sale.pending(policy, board))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._supply_stockout_gold_target, tour.funds_needed)
        self.assertEqual(tour.fundraise_target, tour.funds_needed)

    def test_home_cash_wares_are_sold_first(self):
        policy, board = self.replay(RESTORE_MANA_ROW)
        self.assertIsNone(policy._fundraising_mode)
        tour = finale_bm_tour.record(policy)
        needed = board.player.gold + 1
        # DECLARED CONSTRUCTED (module docstring): a cash ware on Home's shelf.
        with mock.patch.object(home_cash_sale, "pending", return_value=True):
            for _wait in range(finale_bm_tour.FUNDS_SALE_WAITS):
                key = finale_bm_tour._funds_key(policy, board, tour, needed)
                self.assertEqual(policy.last_reason, finale_bm_tour.FUNDS_SALE_REASON)
                self.assertTrue(key)
                self.assertIsNone(policy._fundraising_mode)
            # The sale's own line (home_cash_sale ``due``) is the circuit's need.
            self.assertTrue(finale_bm_tour.funds_short(policy, board))
            # A sale making no progress at one gold: the fundraising run.
            finale_bm_tour._funds_key(policy, board, tour, needed)
        self.assertEqual(policy.last_reason, f"{finale_bm_tour.FUNDRAISE_REASON}:{needed}")
        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_a_closed_circuit_is_a_final_stop(self):
        policy, board = self.replay(STOP_ROW)
        tour = finale_bm_tour.record(policy) or finale_bm_tour._start(policy, board)
        # DECLARED CONSTRUCTED (module docstring): the inn could not be reached.
        tour.closed = "inn-unreachable"
        self.assertTrue(finale_hold.applies(policy, board))
        finale_hold.town_key(policy, board)
        self.assertEqual(policy.last_reason, "town:blocked:finale-bm-tour-closed:inn-unreachable")
        self.assertTrue(cli._policy_final_stop_required(policy))


if __name__ == "__main__":
    unittest.main()
