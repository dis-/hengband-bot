"""The Black Markets' Restore Mana circuit short of gold, and the gold kept for it (n1-b life-416).

Owner rules: 2026-11-23 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。」 (finale_bm_tour); 2026-11-18 「必要なものは買う。本当に資金枯渇したら採掘で良いが、自宅に
大量の換金用アイテムがあるので先に売る。」 (home_cash_sale first); 2026-11-25, the 96F+ case (this
character's Angband recall depth is 99, finale_hold ``applies``): 鉄獄以外で探索できる一番深いダンジョン
（城・山など）に帰還して稼ぎ、目標額に届いたら決戦の準備に戻る (policy_town ``_finale_funds_dive_key``,
finale_bm_tour ``settle_dive``), no 1F mining run any more.

Recorded (tests/extract_finale_bm_funds_1124_fixture.py, ``n1b-416-finale-bm-funds-1124``): the
town-arrival checkpoint of the restarted process (2026-11-24 00:49:02, turn 4317991, Angwil).  The
circuit lapped, stayed the night (row 44) and bought one Restore Mana (row 53, 15,724 gold); row 62
bought a Potion of Resistance for 3,930 (``black-market:resistance``, 94 owned against the finale's
20); at row 66 (20,649 gold) the next leg was short of gold and the circuit closed, and from row 73
the town repeated ``town:blocked:finale-not-in-town:restore_mana:funds`` until the loop detector.
Rows before the one decided are replayed through the public ``choose_key`` and post the recorded
key (row 10 differs on any replay: the recorded progress invariant's rewrite is timing-dependent).

DECLARED CONSTRUCTED: ``test_short_of_gold_the_deepest_other_dungeon_is_dived`` reads the
departure with the town's errand holder out of the way (every producer entry admitted) and the
visit's departure conjuncts ready, as the precedent test of n1-c life-222 does (row 73's town
still had its Home catalogue errand); ``test_the_dive_ends_on_the_next_town_board`` forgets the
circuit as the dive's dungeon board does (angband_finale ``observe``);
``test_no_landing_is_a_named_stop`` has the alternate pick find nothing.
``test_home_cash_wares_are_sold_first`` reads Home's cash sale as pending
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

from hengbot import cli, finale_bm_tour, finale_hold, home_cash_sale, me_inn_refill
from hengbot.model import DUNGEON_ANGBAND, SV_POTION_RESISTANCE, TVAL_POTION
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-finale-bm-funds-1124"
RESTORE_MANA_ROW = 53
RESISTANCE_ROW = 62
FUNDS_ROW = 66
STOP_ROW = 73
CASTLE = 12  # the Castle (DungeonDefinitions), recall depth 64 on these boards


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
        self.assertTrue(finale_bm_tour.supplies_first(policy, board))

    def test_short_of_gold_the_deepest_other_dungeon_is_dived(self):
        policy, board = self.replay(FUNDS_ROW)
        self.assertEqual(board.player.gold, 20649)
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 99)
        self.assertEqual(board.dungeon_recall_depths[CASTLE], 64)

        self.decide(policy, board)

        # Recorded: the circuit closed for its funds, then the town stopped and spun (row 73);
        # before this change a fundraising run (mode 'prepare', the Yeek cave 1F).
        tour = finale_bm_tour.record(policy)
        self.assertIsNone(tour.closed)
        self.assertGreater(tour.funds_needed, board.player.gold)
        self.assertFalse(home_cash_sale.pending(policy, board))
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(tour.fundraise_target)
        self.assertEqual(tour.dive_target, tour.funds_needed)
        self.assertTrue(finale_bm_tour.diving(policy, board))
        # The deepest other dungeon whose landing fits: the Castle, recall depth 64.
        self.assertEqual(policy._alternate_dungeon, CASTLE)
        self.assertEqual(policy._alternate_dungeon_reason, finale_bm_tour.DIVE_REASON)
        self.assertEqual(policy._town_recall_destination(board), ("alt-dungeon", CASTLE))

        later, town = self.replay(STOP_ROW)
        self.assertEqual(later._alternate_dungeon, CASTLE)
        # DECLARED CONSTRUCTED (module docstring): the departure itself, its errands done.
        conjuncts = later._recall_town_departure_conjuncts
        later._recall_town_departure_conjuncts = (
            lambda snapshot, **kw: {name: True for name in conjuncts(snapshot, **kw)})
        later.last_reason = None
        with mock.patch.object(me_inn_refill, "destruction_key", return_value=None), \
                mock.patch.object(type(later), "_town_producer_entry",
                                  lambda self, name, call, **kw: call()), \
                contextlib.redirect_stdout(io.StringIO()):
            key = later._town_special_key(town)
        self.assertEqual(later.last_reason, "town:recall-to-alt-dungeon")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(later._town_recall_issue_watch[0], CASTLE)

    def test_the_dive_ends_on_the_next_town_board(self):
        policy, board = self.replay(STOP_ROW)
        self.assertEqual(policy._alternate_dungeon_reason, finale_bm_tour.DIVE_REASON)
        self.assertFalse(finale_bm_tour.settle_dive(policy, board))
        # DECLARED CONSTRUCTED (module docstring): the dive's dungeon board forgot the circuit.
        policy._finale_bm_tour = None

        self.assertTrue(finale_bm_tour.settle_dive(policy, board))

        self.assertIsNone(policy._alternate_dungeon)
        self.assertIsNone(policy._alternate_dungeon_reason)
        self.decide(policy, board)
        # Angband the target again: the finale's preparation owns the town (the circuit anew).
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertTrue(finale_hold.applies(policy, board))

    def test_no_landing_is_a_named_stop(self):
        policy, board = self.replay(STOP_ROW)
        # DECLARED CONSTRUCTED (module docstring): no other dungeon's landing fits.
        with mock.patch.object(type(policy), "_pick_alternate_dungeon", return_value=None):
            policy._finale_funds_dive_key(board, DUNGEON_ANGBAND)
        self.assertEqual(policy.last_reason, "town:blocked:finale-funds-no-dive-destination")
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertIsNone(policy._fundraising_mode)

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
            # A sale making no progress at one gold: the dive (owner 2026-11-25), no mining run.
            key = finale_bm_tour._funds_key(policy, board, tour, needed)
        self.assertIsNone(key)
        self.assertEqual(tour.dive_target, needed)
        self.assertIsNone(policy._fundraising_mode)

    def test_a_closed_circuit_is_a_final_stop(self):
        policy, board = self.replay(STOP_ROW)
        tour = finale_bm_tour.record(policy) or finale_bm_tour._start(policy, board)
        # DECLARED CONSTRUCTED (module docstring): the inn could not be reached.
        tour.closed = "inn-unreachable"
        # A closed circuit dives no more: its Castle is dropped and the next board's observation
        # takes Angband again (the replay picked the dive on an earlier row).
        self.assertTrue(finale_bm_tour.settle_dive(policy, board))
        policy._target_dungeon_id = DUNGEON_ANGBAND
        self.assertTrue(finale_hold.applies(policy, board))
        finale_hold.town_key(policy, board)
        self.assertEqual(policy.last_reason, "town:blocked:finale-bm-tour-closed:inn-unreachable")
        self.assertTrue(cli._policy_final_stop_required(policy))


if __name__ == "__main__":
    unittest.main()
