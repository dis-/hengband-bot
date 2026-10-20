"""Replay the C4-A lantern-loss boards (issue #65) through the production policy.

Fixture rows are copied as-is from the soak capture
c4a-loops-20261016/20261018-063248-town-blocked-departure-unsatisfiable:

* line 0 (turn 656632, Yeek cave level 1): the latched return walk with the worn
  Brass lantern at 0 turns, five flasks of oil in the pack and the own grid
  still visible (an artifact cloak lights radius 1).  Recorded decision 30909
  ``return:explore`` from rung ``_return_to_town_key#3``.
* line 1 (turn 658046, town): the empty lantern in the pack beside a worn torch
  and the oil.  Recorded decision 30987 ``inventory:destroy-disposable-item``
  ``01kn``.

DECLARED CONSTRUCTED: the return latch (policy runtime state, not captured),
the ~f skill-exp cache, and in the individual tests the worn light's fuel /
identification / kind where a control needs a different light.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import LANTERN_REFILL_FUEL, TORCH_REFILL_FUEL
from test_esp_threat_rest_recorded import EDIT, _policy
from recorded_junk_scope import pre_town_junk_step_replay


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "lantern-lost-20261018.jsonl.gz"
BOUNDARIES = FIXTURES / "lantern-lost-20261018.boundaries.json"
REFILL_FROM_SLOT_A = "\\Fa"


def _with_worn_light(board, **changes):
    equipment = type(board.equipment)(
        replace(item, **changes) if item.is_light else item
        for item in board.equipment
    )
    return replace(board, equipment=equipment)


class LanternLostRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = stream.read().splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _board(self, line: int):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[line]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        board = snapshots[-1]
        self.assertEqual(board.turn, self.boundaries["rows"][line]["turn"])
        # DECLARED CONSTRUCTED: the startup ~f skill-exp exchange is outside
        # this fixture; unused single-weapon values satisfy the protocol gate.
        policy._skill_exp_cache = (
            0, 0, board.player.level, policy._town_visit_epoch
        )
        return policy, board

    def _return_walk(self):
        policy, board = self._board(0)
        # DECLARED CONSTRUCTED: the latched return of the recorded walk
        # (claim rung _return_to_town_key#3, objective "Return to town").
        policy._returning_to_town = True
        policy._escape_state.enter("return", "return:explore")
        return policy, board

    def test_fixture_matches_recorded_boundaries(self):
        data = gzip.decompress(FIXTURE.read_bytes())
        self.assertEqual(
            hashlib.sha256(data).hexdigest(), self.boundaries["board_sha256"]
        )
        policy, board = self._board(0)
        light = next(item for item in board.equipment if item.is_light)
        self.assertTrue(light.is_lantern and light.known)
        self.assertEqual(light.fuel, 0)
        self.assertIs(board.can_see_own_grid, True)
        self.assertEqual(board.dungeon_level, 1)
        self.assertFalse(policy._is_dark(board))
        oil = policy._light_refill_item(board)
        self.assertEqual((oil.slot, oil.count), ("a", 5))

    def test_recorded_empty_lantern_is_refilled_on_the_return_walk(self):
        policy, board = self._return_walk()
        key = policy.choose_key(board)
        self.assertEqual(key, REFILL_FROM_SLOT_A)
        self.assertEqual(policy.last_reason, "refill-light")

    def test_dimming_lantern_is_refilled_before_it_burns_out(self):
        policy, board = self._return_walk()
        # DECLARED CONSTRUCTED: fuel above zero but at the refill threshold,
        # the state of the 06:25:17-06:25:36 dimming messages.
        board = _with_worn_light(board, fuel=LANTERN_REFILL_FUEL)
        key = policy.choose_key(board)
        self.assertEqual(key, REFILL_FROM_SLOT_A)
        self.assertEqual(policy.last_reason, "refill-light")

    def test_control_lantern_above_threshold_keeps_walking(self):
        policy, board = self._return_walk()
        board = _with_worn_light(board, fuel=LANTERN_REFILL_FUEL + 1)
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "return:explore")

    def test_control_unknown_fuel_lantern_keeps_the_darkness_rule(self):
        policy, board = self._return_walk()
        # Constructed: an unidentified lantern does not show its fuel; the
        # existing rule refills it only once the own grid is dark.
        board = _with_worn_light(board, known=False)
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "return:explore")

    def test_control_torch_only_character_keeps_the_torch_rules(self):
        policy, board = self._return_walk()
        torch = next(item for item in board.inventory if item.is_torch)
        oil = next(item for item in board.inventory if item.is_oil)
        # Constructed: a worn low torch instead of the lantern, no oil.
        board = _with_worn_light(
            board, sval=torch.sval, name=torch.name, fuel=TORCH_REFILL_FUEL,
            light_turns=TORCH_REFILL_FUEL,
        )
        board = replace(
            board,
            inventory=type(board.inventory)(
                item for item in board.inventory if item is not oil
            ),
        )
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "return:explore")
        # In darkness the existing rule still combines the spare torch.
        dark_policy, dark_board = self._return_walk()
        dark_board = replace(
            _with_worn_light(
                dark_board, sval=torch.sval, name=torch.name, fuel=0,
                light_turns=0,
            ),
            can_see_own_grid=False,
            inventory=board.inventory,
        )
        self.assertEqual(
            dark_policy._darkness_recovery_key(dark_board),
            f"\\F{torch.slot}",
        )

    # declared wall: pre-2026-10-21 town junk step
    @pre_town_junk_step_replay
    def test_recorded_town_board_keeps_the_empty_lantern(self):
        policy, board = self._board(1)
        lantern = next(item for item in board.inventory if item.is_lantern)
        self.assertEqual((lantern.slot, lantern.fuel), ("n", 0))
        oil = next(item for item in board.inventory if item.is_oil)
        self.assertEqual((oil.slot, oil.count), ("a", 5))
        self.assertIsNone(policy._find_disposable_item(board))
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "inventory:destroy-disposable-item")
        self.assertFalse(key.startswith("01k"))

    def test_control_empty_torch_is_still_disposable_with_oil(self):
        policy, board = self._board(1)
        lantern = next(item for item in board.inventory if item.is_lantern)
        torch = next(item for item in board.equipment if item.is_light)
        # Constructed: an exhausted torch in place of the pack lantern.
        board = replace(
            board,
            inventory=type(board.inventory)(
                replace(torch, slot=item.slot, fuel=0, light_turns=0,
                        is_equipment=item.is_equipment)
                if item is lantern else item
                for item in board.inventory
            ),
        )
        disposable = policy._find_disposable_item(board)
        self.assertIsNotNone(disposable)
        self.assertTrue(disposable.is_torch)

    def test_control_spare_lantern_beside_worn_lantern_stays_disposable(self):
        policy, board = self._board(1)
        lantern = next(item for item in board.inventory if item.is_lantern)
        # Constructed: a fuelled lantern worn instead of the torch.
        board = _with_worn_light(
            board, sval=lantern.sval, name=lantern.name, fuel=7500,
            light_turns=7500,
        )
        disposable = policy._find_disposable_item(board)
        self.assertIsNotNone(disposable)
        self.assertEqual(disposable.slot, "n")


if __name__ == "__main__":
    unittest.main()
