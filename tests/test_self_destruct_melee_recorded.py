"""Pins the recorded adjacent material self-destruct threat and safe controls.

The one-row gzip fixture is the raw protocol-3 board from decision 1995.
The policy checkpoint is absent from the capture. DECLARED CONSTRUCTED: the
protocol-3 skill-exp cache is set to the captured level (7), allowing the real
public policy path to reach combat selection without its observation-only
skill-list request. The ordinary and harmless-explosion controls are
DECLARED CONSTRUCTED by changing only the loaded race blow/damage knowledge.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import dataclasses
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import MonsterState
from hengbot.monrace_knowledge import MonsterBlow, load_monrace_knowledge
from hengbot.policy import WAIT_KEY
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "self-destruct-melee-20261018.jsonl.gz"
FIXTURE_SHA256 = "a23a682d56b89b3086f549872c12e323f51bf89b284c9599262087d7d6c717a5"
RECORDED_DECISION = {"decision_sequence": 1995, "turn": 159544, "key": "7", "reason": "melee"}
RACE_ID = 1090


class SelfDestructMeleeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == 1
        cls.row = json.loads(cls.lines[0])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _decide(self, *, race_knowledge=None, monster_damage=None):
        knowledge = dict(self.monrace)
        if race_knowledge is not None:
            knowledge[RACE_ID] = race_knowledge
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, knowledge)
            policy._skill_exp_cache = (0, 0, 7, None)
            _decoded, snapshots = _consume_response_sequence(
                self.lines,
                policy,
                lambda _key: True,
                knowledge,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            self.assertEqual(len(snapshots), 1)
            board = snapshots[-1]
            if monster_damage is not None:
                monster = board.visible_monsters[0]
                board.visible_monsters[0] = dataclasses.replace(
                    monster, max_melee_damage=monster_damage
                )
            key = policy.choose_key(board)
            return key, policy.last_reason, board, policy

    def test_recorded_material_exploder_is_not_meleed(self):
        self.assertEqual(
            (RECORDED_DECISION["key"], RECORDED_DECISION["reason"]),
            ("7", "melee"),
        )
        key, reason, board, policy = self._decide()
        self.assertEqual(board.turn, RECORDED_DECISION["turn"])
        self.assertEqual((board.player.hp, board.player.max_hp), (177, 177))
        monster = board.visible_monsters[0]
        self.assertEqual((monster.race_id, monster.distance), (RACE_ID, 1))
        knowledge = policy._monrace_knowledge[RACE_ID]
        self.assertTrue(any(blow.method == "EXPLODE" for blow in knowledge.blows))
        threat = policy.threat_prediction(board, [monster], turns=3)["monsters"][0]
        self.assertTrue(threat["self_destructs_on_melee"])
        self.assertEqual(threat["operational_melee_prediction"], 81)
        self.assertTrue(policy._material_melee_engagement(board, monster))
        self.assertEqual((key, reason), (WAIT_KEY, "threat:wait"))
        self.assertNotEqual((key, reason), ("7", "melee"))

    def test_ordinary_monster_is_still_meleed(self):
        ordinary = dataclasses.replace(
            self.monrace[RACE_ID],
            blows=(MonsterBlow("HIT", "SHATTER", 15, 8),),
        )
        key, reason, _board, _policy_instance = self._decide(
            race_knowledge=ordinary
        )
        self.assertEqual((key, reason), ("7", "emergency:cornered-attack"))

    def test_harmless_self_destructing_monster_keeps_melee_behavior(self):
        harmless = dataclasses.replace(
            self.monrace[RACE_ID],
            max_melee_damage=1,
            blows=(MonsterBlow("EXPLODE", "SHATTER", 1, 1),),
        )
        key, reason, board, policy = self._decide(
            race_knowledge=harmless, monster_damage=1
        )
        threat = policy.threat_prediction(
            board, [board.visible_monsters[0]], turns=3
        )["monsters"][0]
        self.assertTrue(threat["self_destructs_on_melee"])
        self.assertLess(threat["operational_melee_prediction"], board.player.hp * 0.5)
        self.assertFalse(
            policy._material_melee_engagement(board, board.visible_monsters[0])
        )
        self.assertEqual((key, reason), ("7", "melee"))


if __name__ == "__main__":
    unittest.main()
