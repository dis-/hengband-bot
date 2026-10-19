"""Replay the C4-A dark walk beside an empty lantern and oil (issue #85).

Fixture rows are copied as-is from the Linux soak capture
c4a-loops-20261016/20261019-134916-dark-locomotion-exhausted (bot 7e695504),
state rows 55 and 56 (turns 1113689 and 1113700, dungeon 1 level 4):

* the worn light is "暗視の松明(0ターンの寿命)" (known, 0 turns), the pack
  holds 油つぼ x5 in slot a and "真鍮のランタン(0ターンの寿命)" in slot o;
* row 55: light_radius 0, can_see_own_grid True (lit room); recorded decision
  4402 ``3`` ``return:seek-upstairs`` (claim rung ``_return_to_town_key#3``);
* row 56: light_radius 0, can_see_own_grid False; recorded decision 4403 ``2``
  ``dark:backtrack`` (``_dark_locomotion_key``), followed by 44 more dark
  decisions and ``<dark:locomotion-exhausted>``.

DECLARED CONSTRUCTED: the return latch of the recorded walk (``return`` escape
owner); the ``~f`` skill-exp cache; in the refill tests the board after the
lantern was wielded (lantern worn, the empty torch in pack slot o); in the
optimizer tests row 55 moved to the town floor, the esp-threat-rest
calibration fixture returned as the character calibration, and (control) the
oil removed from the pack.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from test_esp_threat_rest_recorded import CALIBRATION, EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "lantern-rewield-20261019.jsonl.gz"
SHA256 = "b5a1951b74c9d750605039d80943c52d5a6e84ed774804b3b3a1335e208f2987"
TURNS = (1113689, 1113700)
WIELD_LANTERN_FROM_SLOT_O = "wo"
REFILL_FROM_SLOT_A = "\\Fa"


class LanternRewieldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _board(self, line: int, *, returning: bool = True):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[line]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        self.assertEqual(board.turn, TURNS[line])
        # DECLARED CONSTRUCTED: see the module docstring.
        policy._skill_exp_cache = (
            0, 0, board.player.level, policy._town_visit_epoch
        )
        if returning:
            policy._returning_to_town = True
            policy._escape_state.enter("return", "return:seek-upstairs")
        return policy, board

    @staticmethod
    def _lantern_wielded(board):
        worn = next(item for item in board.equipment if item.is_light)
        lantern = next(item for item in board.inventory if item.is_lantern)
        return replace(
            board,
            equipment=type(board.equipment)(
                replace(lantern, slot=worn.slot) if item.is_light else item
                for item in board.equipment
            ),
            inventory=type(board.inventory)(
                replace(worn, slot=lantern.slot) if item.is_lantern else item
                for item in board.inventory
            ),
        )

    def test_fixture_rows_show_the_empty_torch_lantern_and_oil(self):
        for line, dark in ((0, False), (1, True)):
            policy, board = self._board(line)
            worn = next(item for item in board.equipment if item.is_light)
            self.assertTrue(worn.is_torch and worn.known)
            self.assertEqual(worn.fuel, 0)
            lantern = next(item for item in board.inventory if item.is_lantern)
            self.assertEqual((lantern.slot, lantern.known, lantern.fuel), ("o", True, 0))
            oil = next(item for item in board.inventory if item.is_oil)
            self.assertEqual((oil.slot, oil.count), ("a", 5))
            self.assertEqual(board.light_radius, 0)
            self.assertIs(policy._is_dark(board), dark)
            self.assertIsNone(policy._light_refill_item(board))
            self.assertIsNone(policy._darkness_torch(board))

    def test_recorded_lit_return_board_wields_the_lantern(self):
        policy, board = self._board(0)
        key = policy.choose_key(board)
        self.assertEqual(key, WIELD_LANTERN_FROM_SLOT_O)
        self.assertEqual(policy.last_reason, "restore-lantern")

    def test_recorded_dark_board_wields_the_lantern(self):
        for returning in (True, False):
            with self.subTest(returning=returning):
                policy, board = self._board(1, returning=returning)
                key = policy.choose_key(board)
                self.assertEqual(key, WIELD_LANTERN_FROM_SLOT_O)
                self.assertEqual(policy.last_reason, "restore-lantern")

    def test_wielded_lantern_is_refilled_next(self):
        for line in (0, 1):
            with self.subTest(line=line):
                policy, board = self._board(line)
                board = self._lantern_wielded(board)
                key = policy.choose_key(board)
                self.assertEqual(key, REFILL_FROM_SLOT_A)
                self.assertEqual(policy.last_reason, "refill-light")

    def test_control_dark_board_without_oil_keeps_the_dark_walk(self):
        policy, board = self._board(1)
        board = replace(board, inventory=type(board.inventory)(
            item for item in board.inventory if not item.is_oil
        ))
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "restore-lantern")
        self.assertTrue(policy.last_reason.startswith("dark:"))

    def _optimizer_light_candidates(self, board, policy):
        board = replace(board, floor_key=(0, 0, 0), town_flag=True)
        self.assertTrue(board.in_town)
        policy._refresh_carried_equipment_catalog(board)
        calibration = load_character_calibration(CALIBRATION)
        with mock.patch.object(
            policy, "_validated_character_calibration", return_value=calibration
        ):
            policy._prepare_equipment_optimization(board)
        telemetry = policy._equipment_optimization_telemetry
        lantern_ids = {
            owned.id for owned in policy._equipment_catalog.items
            if owned.item.is_lantern
        }
        self.assertEqual(len(lantern_ids), 1)
        return (
            telemetry["search_slot_candidate_counts"]["light"],
            bool(lantern_ids & policy._equipment_optimization_search_surviving_ids),
        )

    def test_optimizer_counts_the_lantern_while_oil_is_carried(self):
        policy, board = self._board(0, returning=False)
        self.assertEqual(self._optimizer_light_candidates(board, policy), (1, True))

    def test_control_optimizer_drops_the_empty_lantern_without_oil(self):
        policy, board = self._board(0, returning=False)
        board = replace(board, inventory=type(board.inventory)(
            item for item in board.inventory if not item.is_oil
        ))
        self.assertEqual(self._optimizer_light_candidates(board, policy), (0, False))


if __name__ == "__main__":
    unittest.main()
