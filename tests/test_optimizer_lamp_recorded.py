"""Replay the C4-A Home Feanorian lamp that the optimizer never chose (issue #86).

Fixture rows (copied as-is, raw encoding):

  0-4: state rows 0-4 of c4a-loops-20261016/20261019-111025-no-key-exhausted
       (life 14, Level 24, in town, turn 1068217): board, ~f skill list,
       board, the ~9 Home list, board.  Worn 松明 with 0 turns, an empty
       真鍮のランタン in pack slot m.  Home holds フェアノールのランプ (sval 2)
       and 暗視の松明 (+1赤外線視力) beside three plain torches.
  5:   state row 0 of c4a-loops-20261016/20261019-101730-exit-no-marker
       (turn 995536): the worn 真鍮のランタン with 3898 turns the character
       departed with at decision 4644 (no oil).

Recorded decision 7 of the 111025 restart at turn 1068217:
``equipment-transaction:travel-home`` key ``\\x1b`n(.`` toward target loadout
4767118d3bb15871, whose first action withdraws home:6e94dd272b55f172:0, the
+1 infravision torch.  The pval-1 torch "dominated" the lamp in the catalog
prune (the light subtype was not part of the dominance key), so the lamp was
never a search candidate; with the lantern worn the same prune left only the
lantern and torches, and the lantern was kept.

DECLARED CONSTRUCTED: the character calibration (the dump file is not in the
capture; numbers from the captured board, light selection does not read them),
and in the lantern tests the row-5 lantern worn on the town board (pack slot m
emptied).  The no-lamp controls remove the lamp row from the Home list.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import CharacterCalibration
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "optimizer-lamp-20261019.jsonl.gz"
SHA256 = "6d51067c50ee9b865f7480fe34cd61f5fe36881d6cb88ade1b8a47c98f976f7d"
LAMP = "home:ff2b3ffaa208a881:0"
INFRAVISION_TORCH = "home:6e94dd272b55f172:0"
WORN_LANTERN = "equipped:cf9cbd9f667b29b6:0"
TRAVEL_HOME = ("\x1b`n(.", "equipment-transaction:travel-home")
LAMP_NAME = "フェアノールのランプ"


class OptimizerLampRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = gzip.decompress(data).decode("utf-8").splitlines()
        assert len(cls.lines) == 6
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)
        self.policy._crossarea_fundraising_enforced = True
        player = parse_snapshot(json.loads(self.lines[0]), {}).player
        # DECLARED CONSTRUCTED: calibration constants of the captured character.
        self.policy._character_calibration = CharacterCalibration(
            race_id=player.race_id,
            class_id=player.class_id,
            personality_id=player.personality_id,
            level=player.level,
            stat_cur=tuple(player.printed_stat_cur_key),
            base_stats=tuple(player.stat_max),
            base_hp=player.max_hp,
            base_ac_bonus=0,
            intrinsic_abilities=frozenset(),
        )
        self.policy._character_calibration_loaded = True

    def _rows(self, *, worn_lantern=False, lamp_at_home=True):
        rows = [json.loads(line) for line in self.lines[:5]]
        lantern = next(
            item for item in json.loads(self.lines[5])["equipment"]
            if item["slot"] == "light"
        )
        for row in rows:
            if worn_lantern and row.get("type") == "player_turn":
                # DECLARED CONSTRUCTED: the departure lantern of row 5 worn.
                row["equipment"] = [
                    lantern if item["slot"] == "light" else item
                    for item in row["equipment"]
                ]
                row["inventory"] = [
                    item for item in row["inventory"] if item.get("slot") != "m"
                ]
            if (
                not lamp_at_home
                and row.get("knowledge", {}).get("category") == "home"
            ):
                # DECLARED CONSTRUCTED: a Home list without the lamp.
                row["knowledge"]["items"] = [
                    item for item in row["knowledge"]["items"]
                    if item.get("name") != LAMP_NAME
                ]
        return [json.dumps(row, ensure_ascii=False) for row in rows]

    def _replay(self, rows):
        """Feed the rows; return the decision on the last board (row 4)."""
        decisions = []
        for line in rows:
            _decoded, snapshots = _consume_response_sequence(
                [line], self.policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=self.directory / "knowledge.jsonl",
            )
            if json.loads(line).get("type") != "player_turn":
                continue
            key = self.policy.choose_key(snapshots[-1])
            self.policy.confirm_key_posted(key)
            decisions.append((key, self.policy.last_reason))
        return decisions

    def _transaction_actions(self):
        session = self.policy._equipment_transaction_session
        if session is None:
            return None
        return [
            (action.kind, action.item_id, action.target_slot)
            for action in session.plan.actions
        ]

    def _catalog_light(self, item_id):
        return next(
            item for item in self.policy._equipment_catalog.items
            if item.id == item_id
        )

    def test_fixture_is_the_recorded_town_board_and_home_list(self):
        rows = [json.loads(line) for line in self.lines]
        self.assertEqual(
            [row.get("turn") for row in rows],
            [1068217] * 5 + [995536],
        )
        board = parse_snapshot(rows[0], {})
        light = next(item for item in board.equipment if item.is_light)
        self.assertTrue(light.is_torch)
        self.assertEqual(light.fuel, 0)
        home = {item["name"] for item in rows[3]["knowledge"]["items"]}
        self.assertIn(LAMP_NAME, home)
        self.assertIn("暗視の松明 (+1赤外線視力)(2500ターンの寿命) {+赤;明}", home)
        departure = parse_snapshot(rows[5], {})
        lantern = next(item for item in departure.equipment if item.is_light)
        self.assertTrue(lantern.is_lantern)
        self.assertEqual(lantern.fuel, 3898)

    def test_recorded_town_board_withdraws_the_home_lamp(self):
        decisions = self._replay(self._rows())
        self.assertEqual(decisions[-1], TRAVEL_HOME)
        # 3cb276a3: [('withdraw', INFRAVISION_TORCH, None),
        #            ('equip', INFRAVISION_TORCH, 'light')], target loadout
        #            4767118d3bb15871 (the recorded one).
        self.assertEqual(
            self._transaction_actions(),
            [("withdraw", LAMP, None), ("equip", LAMP, "light")],
        )
        self.assertEqual(self._catalog_light(LAMP).item.name, LAMP_NAME)

    def test_worn_lantern_withdraws_the_home_lamp_before_departure(self):
        decisions = self._replay(self._rows(worn_lantern=True))
        # 3cb276a3: ('\x1b`n%.', 'shop:travel'), no equipment transaction;
        # the lantern stays worn and the lamp stays at Home.
        self.assertEqual(decisions[-1], TRAVEL_HOME)
        self.assertEqual(
            self._transaction_actions(),
            [
                ("withdraw", LAMP, None),
                ("takeoff", WORN_LANTERN, "light"),
                ("equip", LAMP, "light"),
                ("deposit", WORN_LANTERN, None),
            ],
        )

    def test_control_without_the_lamp_the_infravision_torch_is_withdrawn(self):
        decisions = self._replay(self._rows(lamp_at_home=False))
        self.assertEqual(decisions[-1], TRAVEL_HOME)
        self.assertEqual(
            self._transaction_actions(),
            [
                ("withdraw", INFRAVISION_TORCH, None),
                ("equip", INFRAVISION_TORCH, "light"),
            ],
        )

    def test_control_without_the_lamp_the_worn_lantern_is_kept(self):
        decisions = self._replay(
            self._rows(worn_lantern=True, lamp_at_home=False)
        )
        self.assertNotEqual(decisions[-1][1], TRAVEL_HOME[1])
        self.assertIsNone(self._transaction_actions())


if __name__ == "__main__":
    unittest.main()
