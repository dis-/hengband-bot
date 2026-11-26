"""The ten Scrolls of Recharging of a race that eats device charges are a finale readiness row: short
of them the town does not depart for the finale and the other towns' Alchemists are toured.

Owner 2026-11-26 (verbatim), the answer to 「10巻そろうまで出発を待たせますか」:
「そろうまで出発しない（他の町も回る）」, after 「魔力充填の巻物を10巻持っていき、空腹かつ3本とも空の
場合のみ充填して食料とする」 (angband_finale ``RECHARGING``, finale_recharge_food).

Recorded (tests/fixtures/n1b-416-finale-town-1123, tests/test_finale_town_1123_recorded.py):
n1-b life-416 (Zombie Magic-Eater, Angband recall depth 96F+: finale_hold ``applies``), the
town arrival of 2026-11-23 21:13:45, rows 0-18 replayed through ``choose_key``; its pack and Home
held no Scroll of Recharging.

DECLARED CONSTRUCTED:
* the Restore Mana carry lowered to the 79 owned (angband_finale ``restore_mana_carry``), as
  test_finale_town_1123's own tests do, so that the Scrolls of Recharging are the only row short;
* in ``test_suppliers_tried_tour_the_other_towns`` this town's suppliers marked tried;
* in ``test_ten_scrolls_enter_the_phase`` ten Scrolls of Recharging added to the board's pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_finale, finale_hold, finale_prep, finale_teleport_tour
from hengbot.model import DUNGEON_ANGBAND, STORE_ALCHEMIST, InventoryItem
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1b-416-finale-town-1123"
FALLBACK_ROW = 19
OWNED_RESTORE_MANA = 79


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def with_scrolls(board, count):
    """The board with ``count`` Scrolls of Recharging in the next pack letter (DECLARED)."""
    letter = chr(ord(max(item.slot for item in board.inventory)) + 1)
    scroll = InventoryItem(slot=letter, name=f"{count}巻の魔力充填の巻物", count=count,
                           tval=angband_finale.RECHARGING[0], sval=angband_finale.RECHARGING[1],
                           aware=True, known=True, fully_known=True, weight=5)
    return replace(board, inventory=[*board.inventory, scroll])


class FinaleRechargeReadinessRecordedTest(unittest.TestCase):
    def replay(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(TOWN, Path(scratch.name))
        for recorded, supply in steps[:FALLBACK_ROW]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        return policy, steps[FALLBACK_ROW][1]()

    def decide(self, policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason

    def test_the_scrolls_are_a_readiness_row_of_the_zombie(self):
        policy, board = self.replay()
        with mock.patch.object(angband_finale, "restore_mana_carry",
                               return_value=OWNED_RESTORE_MANA):
            self.decide(policy, board)
            owned = angband_finale.memory(policy).report["owned"]
            self.assertEqual(owned["recharging"],
                             {"measured": 0, "required": angband_finale.RECHARGING_CARRY,
                              "ready": False})
            self.assertEqual(finale_hold.short_rows(policy), ["recharging"])
        # Short: the phase is not entered (revert: every row owned, the phase entered).
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.IDLE)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertIsNone(policy._alternate_dungeon)
        self.assertFalse(board.player.recalling)

    def test_this_towns_alchemist_first(self):
        policy, board = self.replay()
        with mock.patch.object(angband_finale, "restore_mana_carry",
                               return_value=OWNED_RESTORE_MANA):
            self.decide(policy, board)
            self.assertEqual(policy._angband_finale_errand_store(board), STORE_ALCHEMIST)
            self.assertFalse(finale_teleport_tour.due(policy, board))

    def test_suppliers_tried_tour_the_other_towns(self):
        policy, board = self.replay()
        with mock.patch.object(angband_finale, "restore_mana_carry",
                               return_value=OWNED_RESTORE_MANA), \
                mock.patch.object(type(policy), "_shelf_stop_tried", return_value=True):
            self.decide(policy, board)
            self.assertTrue(finale_hold.applies(policy, board))
            self.assertTrue(finale_teleport_tour.due(policy, board))
            key = finale_hold.town_key(policy, board)
            shortages = dict(policy._cross_town_shortages(board))
        self.assertIsNotNone(key)
        circuit = finale_teleport_tour.circuit(policy)
        self.assertIsNotNone(circuit)
        self.assertEqual(tuple(circuit.blocking_categories),
                         (finale_teleport_tour.RECHARGING_CATEGORY,))
        self.assertEqual(shortages[finale_teleport_tour.RECHARGING_CATEGORY],
                         angband_finale.RECHARGING_CARRY)
        self.assertEqual(policy._cross_town_shopping_funds["circuit"], "angband-finale-teleport")
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.IDLE)

    def test_ten_scrolls_enter_the_phase(self):
        policy, board = self.replay()
        board = with_scrolls(board, angband_finale.RECHARGING_CARRY)
        with mock.patch.object(angband_finale, "restore_mana_carry",
                               return_value=OWNED_RESTORE_MANA):
            _key, reason = self.decide(policy, board)
            self.assertEqual(finale_hold.short_rows(policy), [])
        self.assertNotIn("unsafe-recall-fallback", reason)
        self.assertNotEqual(finale_prep.phase(policy).step, finale_prep.IDLE)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)


if __name__ == "__main__":
    unittest.main()
