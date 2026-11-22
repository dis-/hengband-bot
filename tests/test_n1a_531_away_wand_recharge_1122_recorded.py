"""n1-a life-531: the empty Wands of Teleport Other are taken out and recharged at the Tower.

n1-a life-531 (Warrior Lv50, device skill 42) died on Mountain 49F at 2026-11-22 13:40:13 beside
two teleport followers, its Teleport Other no means: the carried Rod of Teleport Other succeeds
26% (zaprod-execution.cpp:66-94 at the rod's level 45: chance 42 - 16 = 26 against fail 50,
26/100), below the 50% of owner 2026-11-16 「成功率50%未満は使える手に数えない」.  The Home held
thirteen Wands of Teleport Other with no charge: a wand succeeds 42 - 20 = 22, (22 - 2)/22 = 91%
(zapwand-execution.cpp:63-78, level 20) whatever its charges, and the Tower's recharge-all fills a
wand to its base charges (market/building-recharger.cpp, morivant_tower.charges_after_recharge).
teleport_away_carry counted a charged wand only, so no wand was taken out, and the visit's Tower
trip (13:39, for the Stone to Mud wand) recharged the pack without one.

Owner 2026-11-14 「1本持ち歩く」 and 2026-11-16 「実際の成功率が高い方」: the empty wand is ranked at
the success it has once recharged; it is taken out and the town's Tower trip
(wand_tower_recharge, owner 2026-11-10 「資金に余裕があるとき魔法棒を塔でチャージする」) fills it.

Recorded:

* tests/fixtures/n1a-531-climb-fix-1122: the 13:38:55 town-arrival checkpoint of the death capture,
  the town board after the Home knowledge scan (journal row 1) and the board before the Tower trip
  (row 34, ``town:wand-recharge:travel``);
* tests/fixtures/n1a-531-mountain-climb-1122-survival: the 08:25:05 visit of the same life (device
  skill 40, twelve empty wands at Home): its row 11 (recorded ``home:route-claim-unfulfilled``) now
  queues the wand's Home take.

DECLARED CONSTRUCTED: the withdrawn wand is one of the Home stack moved into the pack of the row-34
board (``_with_wand``); the Stone to Mud wand is taken out of that pack to show the trip is the Teleport
Other wand's own; the recharged wand carries the Tower's charges.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import morivant_tower, teleport_away_carry, wand_tower_recharge
from hengbot.policy_constants import MORIVANT_TOWN_ID
from hengbot.model import (
    SV_ROD_TELEPORT_AWAY, SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_WAND,
)
from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures")


def _quiet(call):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call()


def _away(items, tval):
    return next(item for item in items
                if (item.tval, item.sval) == (tval, SV_WAND_TELEPORT_AWAY if tval == TVAL_WAND
                                              else SV_ROD_TELEPORT_AWAY))


class DeathVisitTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, steps = _quiet(
            lambda: load(FIXTURES / "n1a-531-climb-fix-1122", Path(cls.scratch.name)))
        _quiet(lambda: replay_window("n1a-531-away-wand", cls.policy, iter(steps[:1])))
        cls.board = steps[1][1]()
        cls.trip_board = steps[34][1]()
        cls.trip_row = steps[34][0]

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_recorded_chances(self):
        board = self.board
        self.assertEqual(board.player.device_skill, 42)
        rod = _away(board.inventory, TVAL_ROD)
        self.assertEqual(round(teleport_away_carry.success(board.player, rod)), 26)
        self.assertFalse(teleport_away_carry.usable(board.player, rod))
        wands = _away(self.policy._home_knowledge_items, TVAL_WAND)
        self.assertEqual((wands.count, wands.charges), (13, 0))
        self.assertEqual(round(teleport_away_carry.success(board.player, wands)), 91)
        self.assertTrue(morivant_tower.morivant_unlocked(board))

    def test_the_empty_home_wand_is_the_device_to_take_out(self):
        policy, board = self.policy, self.board
        wands = _away(policy._home_knowledge_items, TVAL_WAND)
        rods = _away(policy._home_knowledge_items, TVAL_ROD)
        self.assertTrue(teleport_away_carry.rechargeable(board, wands))
        self.assertEqual(teleport_away_carry.home_missing(policy, board, wands), 1)
        self.assertEqual(teleport_away_carry.home_missing(policy, board, rods), 0)
        # The Home binder's membership (policy_home, home_missing) and amount (policy_supply's
        # default one).
        self.assertTrue(policy._home_procurement_batch_member(board, wands))
        self.assertEqual(policy._procurement_missing_amount(board, wands), 1)
        # DECLARED CONSTRUCTED: Morivant not listed (no Tower trip): the empty wand is no device.
        no_tower = replace(board, visited_town_ids=tuple(
            town for town in board.visited_town_ids if town != MORIVANT_TOWN_ID))
        self.assertFalse(teleport_away_carry.rechargeable(no_tower, wands))
        self.assertEqual(teleport_away_carry.home_missing(policy, no_tower, wands), 0)

    def _with_wand(self, *, charges=0, stone_to_mud=True):
        """DECLARED CONSTRUCTED: one wand of the Home stack in the row-34 pack."""
        board = self.trip_board
        home = _away(self.policy._home_knowledge_items, TVAL_WAND)
        rod = _away(board.inventory, TVAL_ROD)
        wand = replace(rod, tval=TVAL_WAND, sval=SV_WAND_TELEPORT_AWAY, count=1, charges=charges,
                       name=home.name, known=True, aware=True, charging=False)
        inventory = [item for item in board.inventory
                     if stone_to_mud or (item.tval, item.sval) != (TVAL_WAND, SV_WAND_STONE_TO_MUD)]
        return replace(board, inventory=[*inventory, wand]), wand, rod

    def test_the_tower_trip_recharges_the_carried_empty_wand(self):
        self.assertEqual(self.trip_row["reason"], wand_tower_recharge.TRAVEL_REASON)
        board, wand, rod = self._with_wand()
        self.assertIs(teleport_away_carry.carried_device(board), wand)
        self.assertIs(teleport_away_carry.recharge_due(board), wand)
        self.assertIn(wand, wand_tower_recharge.short(board))
        # The rod is kept beside it until the wand is filled.
        self.assertEqual(teleport_away_carry.retained_count(board, wand), 1)
        self.assertEqual(teleport_away_carry.retained_count(board, rod), 1)
        # The trip is the wand's own: without the Stone to Mud wand it still applies.
        board, wand, _rod = self._with_wand(stone_to_mud=False)
        self.assertEqual(wand_tower_recharge.short(board), [wand])
        self.assertTrue(wand_tower_recharge.applies(self.policy, board))
        # Recharged (the Tower's charges): a ready device, nothing more to recharge, the rod free.
        filled = morivant_tower.charges_after_recharge(wand)
        self.assertGreater(filled, 0)
        board, wand, rod = self._with_wand(charges=filled, stone_to_mud=False)
        self.assertIs(teleport_away_carry.carried_device(board), wand)
        self.assertIsNone(teleport_away_carry.recharge_due(board))
        self.assertEqual(wand_tower_recharge.short(board), [])
        self.assertEqual(teleport_away_carry.retained_count(board, rod), 0)

    def test_a_charged_home_wand_comes_before_the_recharge(self):
        """Of one success and kind the ready device ranks first: an empty carried wand does not
        keep a charged Home wand on the shelf (DECLARED CONSTRUCTED: the Home stack charged)."""
        policy = self.policy
        board, _wand, _rod = self._with_wand()
        home = _away(policy._home_knowledge_items, TVAL_WAND)
        charged = replace(home, charges=50)
        items = policy._home_knowledge_items
        try:
            policy._home_knowledge_items = tuple(charged if item is home else item
                                                 for item in items)
            self.assertEqual(teleport_away_carry.home_missing(policy, board, charged), 1)
        finally:
            policy._home_knowledge_items = items
        # The empty Home stack against the empty carried wand: nothing more is taken.
        self.assertEqual(teleport_away_carry.home_missing(policy, board, home), 0)


class MorningVisitTest(unittest.TestCase):

    def test_the_0825_visit_queues_the_empty_wand_take(self):
        with TemporaryDirectory() as scratch:
            policy, _journal, steps = _quiet(lambda: load(
                FIXTURES / "n1a-531-mountain-climb-1122-survival", Path(scratch)))
            result = _quiet(lambda: replay_window("n1a-531-away-wand-0825", policy, iter(steps)))
            try:
                # Recorded row 11: ('\x1b', 'home:route-claim-unfulfilled').
                self.assertEqual(result.first_divergence["row"], 11)
                self.assertEqual(result.first_divergence["new"][1], "home:queue-catalogue-shortage")
                self.assertEqual(policy._home_pending_item[1:], (TVAL_WAND, SV_WAND_TELEPORT_AWAY))
                self.assertEqual(policy._home_pending_quantity, 1)
            finally:
                policy._home_disposal.history_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
