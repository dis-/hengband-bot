"""Pins the recorded exploding-earthquake threat and its controls.

The one-row gzip fixture is the raw protocol-3 board from decision 1995
(Yeek cave 1F, HP 177/177, race 1090 awake and adjacent, every other
neighbour of the player a mineral wall).  Hengband zeroes an EXPLODE blow's
own damage, but a hitting SHATTER explosion starts an earthquake at the
monster (monster-attack-switcher.cpp); a collapsed player grid with no empty
neighbour to dodge to takes the 200 direct hit (spell-kind/earthquake.cpp).

The policy checkpoint is absent from the capture. DECLARED CONSTRUCTED: the
protocol-3 skill-exp cache is set to the captured level (7), allowing the real
public policy path to reach combat selection without its observation-only
skill-list request.  The escape-scroll board is DECLARED CONSTRUCTED by adding
one Phase Door scroll to the raw inventory; the race controls are DECLARED
CONSTRUCTED by changing only the loaded race blow knowledge; the surface
control is DECLARED CONSTRUCTED by moving the parsed board to level 0.
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
from hengbot.model import SV_SCROLL_PHASE_DOOR, TVAL_SCROLL
from hengbot.monrace_knowledge import MonsterBlow, load_monrace_knowledge
from hengbot.monster_melee_evaluator import add_earthquake_damage
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

    def _decide(self, *, race_knowledge=None, lines=None):
        knowledge = dict(self.monrace)
        if race_knowledge is not None:
            knowledge[RACE_ID] = race_knowledge
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, knowledge)
            policy._skill_exp_cache = (0, 0, 7, None)
            _decoded, snapshots = _consume_response_sequence(
                self.lines if lines is None else lines,
                policy,
                lambda _key: True,
                knowledge,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            self.assertEqual(len(snapshots), 1)
            board = snapshots[-1]
            key = policy.choose_key(board)
            return key, policy.last_reason, board, policy

    def _threat(self, policy, board):
        return policy.threat_prediction(
            board, [board.visible_monsters[0]], turns=3
        )

    def test_recorded_earthquake_explosion_is_lethal_not_plain_melee(self):
        self.assertEqual(
            (RECORDED_DECISION["key"], RECORDED_DECISION["reason"]),
            ("7", "melee"),
        )
        key, reason, board, policy = self._decide()
        self.assertEqual(board.turn, RECORDED_DECISION["turn"])
        self.assertEqual((board.player.hp, board.player.max_hp), (177, 177))
        monster = board.visible_monsters[0]
        self.assertEqual((monster.race_id, monster.distance), (RACE_ID, 1))
        self.assertIn(
            MonsterBlow("EXPLODE", "SHATTER", 15, 8),
            policy._monrace_knowledge[RACE_ID].blows,
        )
        # Boxed in: the monster's cell is the only passable neighbour.
        self.assertEqual(
            [
                position
                for position, grid in board.grids.items()
                if position.distance_to(board.player.position) == 1
                and grid.passable
                and not grid.has_monster
            ],
            [],
        )
        prediction = self._threat(policy, board)
        threat = prediction["monsters"][0]
        self.assertTrue(threat["self_destructs_on_melee"])
        self.assertEqual(threat["melee_attacks"], 1)
        # 15d8 less AC (118) plus the 200 direct hit; was 118 / 81.
        self.assertEqual(prediction["total"], 318)
        self.assertEqual(prediction["operational_total"], 269)
        self.assertGreaterEqual(prediction["operational_total"], board.player.hp)
        # No stairs, scroll, recall or open cell: the emergency rung attacks
        # rather than wait for the explosion.
        self.assertEqual((key, reason), ("7", "emergency:cornered-attack"))
        self.assertTrue(policy._emergency_escape_pending)

    def test_recorded_board_with_phase_door_reads_it_instead_of_melee(self):
        row = json.loads(self.lines[0])
        scroll = dict(row["inventory"][1])
        scroll.update(
            slot="n",
            count=1,
            name="Phase Door",
            tval=TVAL_SCROLL,
            sval=SV_SCROLL_PHASE_DOOR,
        )
        row["inventory"].append(scroll)
        key, reason, _board, _policy_instance = self._decide(
            lines=[json.dumps(row, ensure_ascii=False) + "\n"]
        )
        self.assertEqual(reason, "emergency:phase")
        self.assertNotEqual(key, "7")
        self.assertIn("n", key)

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
            blows=(MonsterBlow("EXPLODE", "HURT", 1, 1),),
        )
        key, reason, board, policy = self._decide(race_knowledge=harmless)
        prediction = self._threat(policy, board)
        self.assertTrue(prediction["monsters"][0]["self_destructs_on_melee"])
        self.assertEqual(
            (prediction["total"], prediction["operational_total"]), (1, 1)
        )
        self.assertEqual((key, reason), ("7", "melee"))

    def test_surface_explosion_has_no_earthquake(self):
        _key, _reason, board, policy = self._decide()
        surface = dataclasses.replace(
            board, floor_key=(board.floor_key[0], 0, board.floor_key[2])
        )
        self.assertEqual(surface.dungeon_level, 0)
        prediction = self._threat(policy, surface)
        self.assertEqual(prediction["total"], 118)
        self.assertLess(prediction["operational_total"], board.player.hp)

    def test_each_empty_neighbour_must_collapse_before_the_direct_hit(self):
        boxed = dict(add_earthquake_damage(((0, 1.0),), 0))
        self.assertAlmostEqual(boxed[200], 0.15)
        self.assertAlmostEqual(boxed[0], 0.85)
        self.assertEqual(max(boxed), 200)
        one_exit = dict(add_earthquake_damage(((0, 1.0),), 1))
        self.assertAlmostEqual(one_exit[200], 0.15 * 0.15)
        dodged = sum(
            probability
            for damage, probability in one_exit.items()
            if 10 <= damage <= 40
        )
        self.assertAlmostEqual(dodged, (0.15 - 0.15 * 0.15) * 2 / 3)
        self.assertAlmostEqual(sum(one_exit.values()), 1.0)
        shifted = dict(add_earthquake_damage(((5, 1.0),), 0))
        self.assertAlmostEqual(shifted[205], 0.15)


if __name__ == "__main__":
    unittest.main()
