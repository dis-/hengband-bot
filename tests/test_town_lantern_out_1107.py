"""A worn unidentified lantern seen out in town is refilled, not swapped back in.

n1-b life-330 (2026-11-06 21:53:50-21:54:14, town:blocked:owner-retired-burst):
the worn 真鍮のランタン {並, Q34} went out in town (「明かりが消えてしまった！」,
light_radius 0) while four flasks of oil were carried.  ``_light_refill_item``
refused an unidentified lantern below the dungeon, so wield-light put a torch
on; the equipment optimizer, reading the unidentified lantern's fuel as merely
unknown, took the torch off and equipped the dark lantern again.  The two
alternated 26 times until the equipment-txn owner retired three times.

Board rows: tests/fixtures/optimizer-lamp-20261019.jsonl.gz rows 0-4 (a town
board, ~f skill list, board, the ~9 Home list, board).  DECLARED CONSTRUCTED:
the light slot holds the unidentified Q34 lantern (light_radius 0 with
「明かりが消えてしまった！」), the recorded worn torch moves to the pack with 3300
turns, the empty known lantern of pack slot m is left out, and the Home lights
are removed so only the carried torch and lantern compete; the oil variants add
four flasks to the pack.  The torch-worn rows put the torch back in the light
slot (light_radius 1) and the lantern in the pack, the board after wield-light.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
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
Q34_LANTERN = {
    "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 1,
    "damage_dice": {"num": 1, "sides": 1}, "fully_known": False,
    "inscription": "Q34", "is_artifact": False, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": False, "known_flags": [], "light_turns": 0,
    "name": "真鍮のランタン {並, Q34}", "pval": 0, "slot": "light", "sval": 1,
    "to_a": 0, "to_d": 0, "to_h": 0, "tval": 39, "weight": 50,
    "pseudo_feeling": "average",
}


class TownLanternOutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
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

    def _rows(self, *, lantern_worn, oil):
        rows = []
        for line in self.lines[:5]:
            row = json.loads(line)
            if row.get("type") == "player_turn":
                torch = next(item for item in row["equipment"] if item["slot"] == "light")
                torch.update(light_turns=3300, name="松明(3300ターンの寿命)")
                pack = [item for item in row["inventory"] if item.get("slot") != "m"]
                if oil:
                    flask = copy.deepcopy(next(item for item in pack if item["tval"] == 70))
                    flask.update(count=4, name="4個の油つぼ", tval=77, sval=0, light_turns=7500)
                    pack.insert(0, flask)
                lantern = dict(Q34_LANTERN)
                if lantern_worn:
                    row["equipment"] = [
                        lantern if item["slot"] == "light" else item
                        for item in row["equipment"]
                    ]
                    pack.append(dict(torch))
                    row["player"]["light_radius"] = 0
                    row["messages"] = ["明かりが消えてしまった！"]
                else:
                    pack.append(lantern)
                    row["player"]["light_radius"] = 1
                for index, item in enumerate(pack):
                    item["slot"] = chr(ord("a") + index)
                row["inventory"] = pack
            if row.get("knowledge", {}).get("category") == "home":
                row["knowledge"]["items"] = [
                    item for item in row["knowledge"]["items"] if item.get("tval") != 39
                ]
            rows.append(json.dumps(row, ensure_ascii=False))
        return rows

    def _replay(self, rows):
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
        return [(action.kind, action.target_slot) for action in session.plan.actions]

    def test_lantern_seen_out_with_oil_carried_is_refilled_in_town(self):
        decisions = self._replay(self._rows(lantern_worn=True, oil=True))
        # Live: ('wg', 'wield-light') put the torch on.
        key, reason = decisions[-1]
        self.assertEqual(reason, "refill-light")
        self.assertIn("F", key)

    def test_without_oil_the_torch_is_not_traded_back_for_the_dark_lantern(self):
        lantern_worn = self._replay(self._rows(lantern_worn=True, oil=False))
        self.assertNotEqual(lantern_worn[-1][1], "refill-light")
        decisions = self._replay(self._rows(lantern_worn=False, oil=False))
        # Live: ('tg', 'equipment-transaction:takeoff') then ('wj',
        # 'equipment-transaction:equip') put the dark lantern back on.
        self.assertNotIn(
            "equipment-transaction:takeoff", [reason for _key, reason in decisions]
        )
        self.assertIsNone(self._transaction_actions())


if __name__ == "__main__":
    unittest.main()
