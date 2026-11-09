"""A monster shown only by detection keeps its cell in the routes unless it is beside the player.

``_build_grid_index`` removed the cell of every monster in ``detected_monsters`` from the
walkable index.  Telepathy reaches MAX_PLAYER_SIGHT (20, monster-update.cpp), so at that
edge one step showed and hid a far monster, its cell left the index and came back, and
loot and explore re-planned their shortest routes on every board (n1-a life-492
2026-11-07 06:06:57, seek-loot '4'/'6' between (27,113) and (27,112) while a 洞窟オーク
18-20 away came and went; n1-b life-335 06:51 Labyrinth 18F, stuck:seek-stairs '7' and
explore '3' between (14,11) and (13,10) with race 227 at (14,31) at the edge).

Recorded board: n1-b life-335 turn 1835622 at (32,50), seek-loot toward (54,52) through
the corridor (34,55)-(35,54)-(36,53) (fixture detected-hunt-335-1107, decided through
choose_key from the first recorded board).
DECLARED CONSTRUCTED: a detected (out of view) 洞窟オーク added on the corridor 4 cells
away, or beside the player.  The life-492 boards are not replayed: a fresh policy started
inside the capture does not have the loot memory the live bot walked with.
DECLARED WALL: ニーベルング族の王『アルベリヒ』 (race 419) was shown awake beside the player at
turn 1835600 and is out of sight on the board; owner 2026-11-09 「起きた敵も最後の位置を覚える」
keeps it at its last cell (sleeper_reach_memory, sleeper_loot_block), which refuses the loot.
These pins are about the detected orc's cell, so that memory is walled off after the replay.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import sleeper_loot_block, sleeper_reach_memory
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from test_esp_threat_rest_recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "detected-hunt-335-1107.json.xz"
BOARD_TURN = 1835622
CORRIDOR_CELL = (36, 53)
BESIDE_CELL = (33, 50)
CAVE_ORC = 126


class DetectedRouteCellsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.skill = payload["skill"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        boards = [json.loads(line) for line in payload["boards"]]
        policy = HengbotPolicy(monrace_knowledge=cls.races)
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), cls.races))
        for raw in boards:
            if raw["turn"] == BOARD_TURN:
                cls.raw = raw
                break
            key, _reason = cls.decide(policy, raw)
            if key:
                policy.confirm_key_posted(key)
        # DECLARED WALL (module docstring): the remembered awake Alberich.
        setattr(policy, sleeper_reach_memory.MEMORY, None)
        setattr(policy, sleeper_loot_block.MEMORY, None)
        cls.before = policy

    @classmethod
    def decide(cls, policy, raw):
        policy.consume_skill_knowledge({**cls.skill, "player": {"level": raw["player"]["level"]}})
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.races))
        return policy.choose_key(board), policy.last_reason

    def with_detected(self, cell):
        raw = copy.deepcopy(self.raw)
        raw["detected_monsters"] = list(raw.get("detected_monsters", [])) + [{
            "index": 901, "race_id": CAVE_ORC, "y": cell[0], "x": cell[1], "asleep": False,
            "confused": False, "fast": False, "fearful": False, "friendly": False,
            "health": "unhurt", "invulnerable": False, "level": None, "name": "constructed",
            "pet": False, "slow": False, "stunned": False, "esp": True, "detected": False}]
        return raw

    def test_the_recorded_board_walks_to_the_loot(self):
        policy = copy.deepcopy(self.before)
        self.assertEqual(self.decide(policy, self.raw), ("6", "seek-loot"))
        self.assertIn(CORRIDOR_CELL, policy._floor_t)
        self.assertIn(BESIDE_CELL, policy._floor_t)

    def test_a_far_detected_monster_keeps_its_cell_and_the_route(self):
        policy = copy.deepcopy(self.before)
        self.assertEqual(self.decide(policy, self.with_detected(CORRIDOR_CELL)), ("6", "seek-loot"))
        self.assertIn(CORRIDOR_CELL, policy._floor_t)

    def test_a_detected_monster_beside_the_player_leaves_the_route(self):
        policy = copy.deepcopy(self.before)
        self.decide(policy, self.with_detected(BESIDE_CELL))
        self.assertNotIn(BESIDE_CELL, policy._floor_t)


if __name__ == "__main__":
    unittest.main()
