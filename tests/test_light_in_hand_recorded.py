"""Replay the C4-A lightless departure (issue #82) through the production policy.

Fixture rows are copied as-is from two soak captures of the same character:

* line 0: c4a-loops-20261016/20261019-101730-exit-no-marker state row 0
  (turn 995536, Yeek cave level 13), the first recorded row after decision
  4644 ``rhb`` ``town:recall-to-yeek-cave`` (turn 994876).  The worn Brass
  lantern has 3898 turns, the pack holds no oil and no torch; decision 4644
  recorded ``procurement_requirements`` ``[]``.
* line 1: c4a-loops-20261016/20261019-111025-no-key-exhausted state row 3,
  the ``~9`` Home knowledge row: a Feanorian lamp, four flasks of oil and four
  torches.

DECLARED CONSTRUCTED: the departure board is line 0 moved to the town floor
(decision 4644 ``floor`` 0/0) with the Word of Recall read at departure and the
Teleport scroll read on the floor restored (decision 4644 retention rows 10 and
15); the Home at decision 4644 is the line-1 list (decision 4644
``catalog_tval_counts`` 39: 6 = the worn lantern + the five Home lights); the
policy runtime ``_equipment_optimization_last_depth`` 19 (decision 4644
``optimization_depth``) and target dungeon 2 (``over_extension``).  In the
individual tests: a flask carried from the Home stack, and in the controls the
Home lamp worn or carried.
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

from hengbot.cli import _consume_response_sequence, _parse_items
from hengbot.model import SV_LITE_FEANOR, TVAL_LITE
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import FOOD_STOCK_TARGET, OIL_TARGET
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "light-in-hand-20261019.jsonl.gz"
SHA256 = "7ba65b7d4ee864129eb6a9988dcb541f905e6c64ce45b3be68073e960dcbbd2d"


class LightInHandRecordedTest(unittest.TestCase):
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

    def _board(self):
        policy = _policy(self.directory, self.monrace)
        _decoded, snapshots = _consume_response_sequence(
            [self.lines[0]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        row = snapshots[-1]
        self.assertEqual((row.turn, row.floor_key[:2]), (995536, (2, 13)))
        home = json.loads(self.lines[1])
        self.assertEqual(home["knowledge"]["category"], "home")
        self.home = tuple(_parse_items(
            home["knowledge"]["items"], protocol=home.get("protocol_version")
        ))
        # DECLARED CONSTRUCTED: see the module docstring.
        policy.consume_home_knowledge(self.home)
        policy._equipment_optimization_last_depth = 19
        policy._target_dungeon_id = 2
        restored = {"h": 10, "g": 15}
        board = replace(
            row, floor_key=(0, 0, 0), town_flag=True,
            inventory=type(row.inventory)(
                replace(item, count=restored[item.slot])
                if item.slot in restored else item
                for item in row.inventory
            ),
        )
        worn = next(item for item in board.equipment if item.is_light)
        self.assertTrue(worn.is_lantern and worn.known and worn.fuel == 3898)
        self.assertFalse(any(
            item.is_oil or item.is_light for item in board.inventory
        ))
        return policy, board

    def _home_item(self, predicate):
        return next(item for item in self.home if predicate(item))

    def _home_lamp(self):
        return self._home_item(
            lambda item: item.tval == TVAL_LITE and item.sval == SV_LITE_FEANOR
        )

    def _with_carried(self, board, item):
        return replace(board, inventory=type(board.inventory)(
            [*board.inventory, item]
        ))

    def test_recorded_departure_board_requires_oil_for_the_lantern(self):
        policy, board = self._board()
        self.assertTrue(any(
            owned.origin == "home"
            and owned.item.tval == TVAL_LITE
            and owned.item.sval == SV_LITE_FEANOR
            and owned.exploration_legal
            for owned in policy._equipment_catalog.items
        ))
        self.assertFalse(policy._owns_usable_permanent_light(board))
        oil = policy._supply_ledger(board, policy._planned_depth())["oil"]
        self.assertEqual(
            (oil.count, oil.required_departure, oil.obtainable),
            (0, OIL_TARGET, True),
        )
        self.assertEqual(policy.procurement_requirements(board), [{
            "item": "Flasks of oil", "current": 0, "target": OIL_TARGET,
            "missing": OIL_TARGET,
        }])
        self.assertTrue(policy._oil_below_departure_target(board))
        home_oil = self._home_item(lambda item: item.is_oil)
        self.assertEqual(home_oil.count, 4)
        self.assertEqual(
            [match.rung_id for match in
             policy._matching_live_purchase_rungs(board, home_oil)],
            ["legacy:oil"],
        )

    def test_recorded_carried_oil_stays_with_the_lamp_in_home(self):
        policy, board = self._board()
        home_oil = self._home_item(lambda item: item.is_oil)
        flask = replace(home_oil, slot="p")
        board = self._with_carried(board, flask)
        self.assertFalse(policy._home_deposit_candidate(flask, board))
        self.assertEqual(
            policy._retention_reservation_baseline_detail(board, flask),
            (4, "supply-ledger:oil"),
        )

    def test_recorded_spare_torches_back_the_lantern(self):
        policy, board = self._board()
        torch = self._home_item(lambda item: item.is_torch)
        self.assertEqual(
            policy._torch_carry_requirement(board, torch, None),
            (FOOD_STOCK_TARGET, 0),
        )

    def test_control_worn_home_lamp_waives_oil_and_torches(self):
        policy, board = self._board()
        lamp = replace(self._home_lamp(), slot="light")
        board = replace(board, equipment=type(board.equipment)(
            lamp if item.is_light else item for item in board.equipment
        ))
        self._assert_permanent_light_waives(policy, board)

    def test_control_carried_home_lamp_waives_oil_and_torches(self):
        policy, board = self._board()
        board = self._with_carried(board, replace(self._home_lamp(), slot="p"))
        self._assert_permanent_light_waives(policy, board)

    def _assert_permanent_light_waives(self, policy, board):
        self.assertTrue(policy._owns_usable_permanent_light(board))
        oil = policy._supply_ledger(board, policy._planned_depth())["oil"]
        self.assertEqual((oil.required_return, oil.required_departure), (0, 0))
        self.assertEqual(policy.procurement_requirements(board), [])
        self.assertFalse(policy._oil_below_departure_target(board))
        torch = self._home_item(lambda item: item.is_torch)
        self.assertEqual(
            policy._torch_carry_requirement(board, torch, None), (0, 0)
        )
        flask = replace(self._home_item(lambda item: item.is_oil), slot="q")
        board = self._with_carried(board, flask)
        self.assertTrue(policy._home_deposit_candidate(flask, board))
        self.assertEqual(
            policy._retention_reservation_baseline_detail(board, flask),
            (0, None),
        )


if __name__ == "__main__":
    unittest.main()
