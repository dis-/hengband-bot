"""The Black Markets' circuit for every finale supply no town store sells (n1-c life-221).

Owner rule 2026-11-24, verbatim (the question 「99Fへの準備で、体力回復の薬が足りない時はどうしますか？」):
「闇市を巡回して買い足す — 魔力復活の薬と同じく、4つの町の闇市を巡回して買い足し、一周ごとに宿で一泊する。
お金が足りなければ自宅の品を売り、資金集めをする。目標に届くまで99Fへは行かない。」 (finale_bm_tour,
finale_hold, angband_finale ``BLACK_MARKET_KINDS``).

Recorded (tests/extract_finale_bm_supplies_1124_fixture.py, ``n1c-221-finale-bm-supplies-1124``):
the town-arrival checkpoint of 2026-11-24 03:01:17 (turn 5552811), Angband's recall depth 96F, the
preparation phase idle.  Row 84 stopped under ``town:blocked:finale-not-in-town:healing`` (2 of the
30 Potions of Healing owned; store/articles-on-sale.cpp lists no Healing) and the rows after it
spun on '5' until the loop detector halted the driver at 03:02:17.  Rows before the one decided are
replayed through the public ``choose_key`` and post the recorded key.

DECLARED CONSTRUCTED: ``test_a_short_ware_of_the_shelf_is_bought_first`` reads a Black Market
Potion of Healing built from the recorded board's kinds (no market page was recorded on this
visit); ``test_a_supply_only_the_dungeon_gives_is_a_final_stop`` reads the absorbed Stone to Mud
short beside the Healing (``finale_hold.short_rows``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import angband_finale, finale_bm_tour, finale_hold, finale_prep
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import (
    FINALE_NOT_IN_TOWN_STOP_PREFIX, POLICY_FINAL_STOP_PREFIXES,
)
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-finale-bm-supplies-1124"
STOP_ROW = 84
STOP_REASON = "town:blocked:finale-not-in-town:healing"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleBlackMarketSupplies1124RecordedTest(unittest.TestCase):
    def replay(self, rows):
        """(policy, the recorded row ``rows``, its board) after the rows before it."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        self.assertEqual(steps[rows][0]["key"], journal[rows]["key"])
        for recorded, supply in steps[:rows]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        return policy, steps[rows][0], steps[rows][1]()

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def assert_the_recorded_town(self, policy, recorded, board):
        self.assertEqual(recorded["reason"], STOP_REASON)
        self.assertGreaterEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 96)
        self.assertTrue(finale_hold.applies(policy, board))
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.IDLE)
        self.assertEqual(angband_finale.shortage(policy, board, angband_finale.HEALING), 28)

    def test_the_healing_short_starts_the_circuit(self):
        policy, recorded, board = self.replay(STOP_ROW)
        self.assert_the_recorded_town(policy, recorded, board)

        key, reason = self.decide(policy, board)

        # Recorded: ('7', 'town:blocked:finale-not-in-town:healing'), then '5' until the loop
        # detector.
        self.assertFalse(reason.startswith("town:blocked:"), reason)
        self.assertNotEqual(key, "5")
        self.assertEqual(finale_hold.short_rows(policy), ["healing"])
        tour = finale_bm_tour.record(policy)
        self.assertIsNotNone(tour)
        self.assertIsNone(tour.closed)
        self.assertEqual(tour.short_at_lap, 28)
        # This town's Black Market first (the store router's approach).
        self.assertEqual(reason, finale_bm_tour.APPROACH_REASON)
        self.assertTrue(key)
        # The gold goes to the shortfall: no optional purchase while it lasts.
        self.assertTrue(finale_bm_tour.supplies_first(policy, board))
        self.assertTrue(finale_hold.black_market_due(policy, board))

    def test_a_short_ware_of_the_shelf_is_bought_first(self):
        policy, _recorded, board = self.replay(STOP_ROW)
        # DECLARED CONSTRUCTED (module docstring): the Black Market's wares of the finale.
        healing = SimpleNamespace(tval=angband_finale.HEALING[0], sval=angband_finale.HEALING[1],
                                  aware=True)
        resistance = SimpleNamespace(tval=angband_finale.RESISTANCE[0],
                                     sval=angband_finale.RESISTANCE[1], aware=True)
        self.assertTrue(angband_finale.black_market_wanted(policy, board, healing))
        # 110 of the 20 owned: not short, not the finale's.
        self.assertFalse(angband_finale.black_market_wanted(policy, board, resistance))

    def test_a_supply_only_the_dungeon_gives_is_a_final_stop(self):
        # DECLARED CONSTRUCTED (module docstring): the absorbed Stone to Mud short as well.
        with mock.patch.object(finale_hold, "short_rows",
                               return_value=["healing", "stone_to_mud"]):
            policy, _recorded, board = self.replay(STOP_ROW)
            key, reason = self.decide(policy, board)
        self.assertTrue(reason.startswith(FINALE_NOT_IN_TOWN_STOP_PREFIX), reason)
        self.assertIn("stone_to_mud", reason)
        # A final stop of the driver (cli), not a '5' wait the loop detector ends.
        self.assertTrue(reason.startswith(POLICY_FINAL_STOP_PREFIXES))
        self.assertIsNone(finale_bm_tour.record(policy))

    def test_the_hold_reads_the_supplies_no_town_store_sells(self):
        self.assertEqual(finale_hold.BLACK_MARKET_SUPPLIES, angband_finale.BLACK_MARKET_SUPPLIES)
        self.assertEqual(angband_finale.BLACK_MARKET_SUPPLIES,
                         {"healing", "star_healing", "resistance", "restore_mana"})
        self.assertNotIn("teleport", finale_hold.BLACK_MARKET_SUPPLIES)


if __name__ == "__main__":
    unittest.main()
