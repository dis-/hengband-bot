"""Issue #89 (predicate audit question 6): one own-grid sight predicate.

The game refuses a read when blind or ``no_lite()`` (action-limited.cpp
``cmd_limit_blind``) or confused (``cmd_limit_confused``), and refuses every
native-travel step when blind or ``no_lite()`` (travel-execution.cpp:134), at
any depth.  Before #89 ``_can_read_scrolls`` consulted ``_is_dark``, which is
dungeon-only, and the town departure read checked only blind/confused, so an
unlit town grid passed.

Substrate: the recorded 2026-10-05 07:16 departure board of
tests/test_star_identify_departure_recorded.py (same restored policy state),
whose departure producer reads the Word of Recall (``ric``,
``town:recall-to-alt-dungeon``).  DECLARED CONSTRUCTED: the worn light is an
empty Brass Lantern with five flasks of oil carried, ``can_see_own_grid``
False, ``light_radius`` 0 and the clock at 22:22 (the #79 soak board: town at
night, worn light 0 turns).  Measured on 653c1bb6: ``_town_special_key`` read
the recall (``ric``) on this board.  Controls: the same board lit, and the
production decision, whose light upkeep refills the lantern first.

The travel pin uses the #79 recorded board (tests/test_town_unseen_travel_
recorded.py) with DECLARED CONSTRUCTED protocol-2 shape (``can_see_own_grid``
None) and blindness: 653c1bb6 let native travel through (only
``can_see_own_grid is False`` counted), the game refuses it while blind.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    SV_FLASK_OIL, SV_LITE_LANTERN, TVAL_FLASK, InventoryItem,
)
from hengbot.monrace_knowledge import load_monrace_knowledge

import test_star_identify_departure_recorded as star
import test_town_unseen_travel_recorded as unseen
from test_esp_threat_rest_recorded import EDIT, _policy


RECALL = ("ric", "town:recall-to-alt-dungeon")


def _dark_night(board):
    lamp = next(item for item in board.equipment if item.is_light)
    lantern = replace(
        lamp, name="真鍮のランタン(0ターンの寿命)", sval=SV_LITE_LANTERN,
        fuel=0, light_turns=0, is_artifact=False, is_ego=False,
    )
    oil = InventoryItem(
        slot="w", name="油つぼ", count=5, tval=TVAL_FLASK, sval=SV_FLASK_OIL,
        aware=True, known=True, fuel=7500,
    )
    day = board.clock[0] if board.clock is not None else None
    return replace(
        board,
        equipment=type(board.equipment)(
            lantern if item.is_light else item for item in board.equipment
        ),
        inventory=type(board.inventory)([*board.inventory, oil]),
        can_see_own_grid=False, light_radius=0, clock=(day, 22, 22),
    )


class DarkTownRecallReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        star.StarIdentifyDepartureRecordedTest.setUpClass()

    def _stalled(self):
        case = star.StarIdentifyDepartureRecordedTest(
            "test_recorded_stop_diverges_to_ready_recall_without_candidate_loss"
        )
        policy, board, _signature = case.stalled()
        self.assertIsNone(policy._next_required_store_type(board))
        return policy, board

    def test_dark_town_departure_does_not_read_recall(self):
        policy, board = self._stalled()
        board = _dark_night(board)
        self.assertTrue(board.in_town)
        self.assertFalse(board.player.blind or board.player.confused)
        self.assertIs(board.can_see_own_grid, False)
        self.assertIsNotNone(policy._find_recall_scroll(board))
        self.assertFalse(policy._own_grid_visible(board))
        self.assertFalse(policy._can_read_now(board))
        # 653c1bb6: "ric" town:recall-to-alt-dungeon (the game answers
        # "明かりがないので見えない。" and no turn passes).
        key = policy._town_special_key(board)
        self.assertIsNone(key)
        self.assertNotEqual(policy.last_reason, RECALL[1])

    def test_dark_town_decision_lights_the_lantern(self):
        policy, board = self._stalled()
        key = policy.choose_key(_dark_night(board))
        self.assertEqual(policy.last_reason, "refill-light")
        self.assertTrue(key.startswith("\\F"))

    def test_control_lit_town_departure_reads_recall(self):
        policy, board = self._stalled()
        self.assertIs(board.can_see_own_grid, True)
        self.assertTrue(policy._own_grid_visible(board))
        self.assertTrue(policy._can_read_now(board))
        self.assertEqual(policy._town_special_key(board), RECALL[0])
        self.assertEqual(policy.last_reason, RECALL[1])

    def test_control_confused_lit_town_departure_does_not_read(self):
        policy, board = self._stalled()
        board = replace(board, player=replace(board.player, confused=True))
        self.assertTrue(policy._own_grid_visible(board))
        self.assertFalse(policy._can_read_now(board))
        self.assertNotEqual(policy._town_special_key(board), RECALL[0])


class SightlessTravelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _recorded_board(self):
        lines = unseen._rows()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        policy = _policy(path, self.monrace)
        policy._crossarea_fundraising_enforced = True
        cursor = 0
        for count in unseen.GROUPS:
            _decoded, snapshots = _consume_response_sequence(
                lines[cursor:cursor + count], policy, lambda _key: True,
                self.monrace, knowledge_ledger_path=path / "knowledge.jsonl",
            )
            cursor += count
        return policy, snapshots[-1]

    def test_blind_board_without_own_grid_report_is_sightless(self):
        policy, board = self._recorded_board()
        self.assertTrue(board.in_town)
        self.assertTrue(policy._native_travel_sightless(board))
        legacy = replace(board, can_see_own_grid=None)
        self.assertFalse(policy._native_travel_sightless(legacy))
        blind = replace(legacy, player=replace(legacy.player, blind=True))
        self.assertFalse(policy._own_grid_visible(blind))
        # 653c1bb6: False (travel posted; the game refuses it while blind).
        self.assertTrue(policy._native_travel_sightless(blind))
        self.assertFalse(policy._can_read_now(blind))


if __name__ == "__main__":
    unittest.main()
