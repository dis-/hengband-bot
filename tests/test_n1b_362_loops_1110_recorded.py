"""n1-b life-362 2026-11-10: two loop stops on the Orc cave's 23rd floor (build bot-f6b56516a).

Recorded: tests/fixtures/n1b-362-loops-1110/ (tests/extract_n1b_362_loops_1110_fixtures.py).
Every decision is the public ``choose_key`` of a policy built as the live one
(tests.support.recorded._policy: the terrain, monster and dungeon definitions of the game).

The floor: a corridor of 低温帯 (COLD_ZONE, terrain 228, COLD_PUDDLE) leads from (36,49) to a
room of 帯電帯 (230) whose open doors (42,41) and (43,42) were held by black ogres (race 262).
hp-mp-processor.cpp deals COLD_PUDDLE damage to whoever stands there every 10 game turns
(``deal_damege_by_feat``: 3000-5000 / 100 times the cold damage rate); the player resists cold
but has no immunity.  monster-info.cpp ``monster_can_cross_terrain`` keeps a monster without
cold immunity off COLD_PUDDLE ground, so the ogres (no IM_COLD) stayed at their doors.

A, 09:32:08 loop-detected: on the corridor each shot at an ogre (``fr1``) was replaced by the
step off (damaging_ground.leave_first).  From (39,43) the ogre on the door (42,41) was in view
and the step went '9'; from (38,44) the wall hid it, telepathy still showed it
(``detected_monsters``), the grid's monster mark (in view only) was clear, the door looked a
free safe cell and the step went '1' back, until the loop guard.  The step off now keeps off
every cell a monster is known to stand on.
DECLARED RECONSTRUCTION: the policy is primed on the ring's board of the player on (36,49), the
last safe cell before the corridor, and decides every ring board from there.  DECLARED
CONSTRUCTED (the walk): from the loop board the player follows the decided moves; the ogres
stay where they are (the cold zone) and are sensed only once the player has stepped away.

"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import damaging_ground
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from tests.support.recorded import EDIT, _policy


FIXTURES = Path(__file__).with_name("fixtures") / "n1b-362-loops-1110"
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
STEP_OFF = damaging_ground.STEP_REASON
HUNT = "esp-threat:hunt-weak"
COLD_ZONE = 228
DOOR, OGRE = Position(42, 41), 262
HIDDEN, SHOWN = Position(38, 44), Position(39, 43)          # A's loop cells
WEAK_CELL, MEDIUM_CELL = Position(34, 53), Position(34, 52)  # B's loop cells
A_HIDDEN_TURN, A_SHOWN_TURN = 5136421, 5136424
B_FIRST_HUNT, B_BACK, B_WALK = 5136614, 5136619, 5136568


def case(name):
    return json.loads(lzma.decompress((FIXTURES / f"{name}.json.xz").read_bytes()))


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def cells(rows):
    return [(row["y"], row["x"]) for row in rows]


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.cases = {name: case(name) for name in "ab"}

    def board(self, name, turn):
        """The last ring board of ``turn`` (the one the recorded decision of the turn saw)."""
        return copy.deepcopy([raw for raw in self.cases[name]["boards"] if raw["turn"] == turn][-1])

    def recorded(self, name, turn):
        rows = [row for row in self.cases[name]["decisions"] if row["turn"] == turn]
        return rows[-1]["key"], rows[-1]["reason"]

    def policy(self, first):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(first), self.monrace))
        # The captured process already held the skill list.
        policy.consume_skill_knowledge({
            "player": {"level": first["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return board, key

    def replay_to(self, name, turn):
        """The policy after deciding every ring board before ``turn``'s last one."""
        boards = self.cases[name]["boards"]
        policy = self.policy(boards[0])
        last = max(index for index, raw in enumerate(boards) if raw["turn"] == turn)
        for raw in boards[:last]:
            self.decide(policy, raw)
        return policy

    def walk(self, policy, raw, decisions):
        """DECLARED CONSTRUCTED: the player follows its moves, the monsters stay where they are
        (none of them may enter the cold zone) and, once the player has moved, are sensed only."""
        raw = copy.deepcopy(raw)
        rows = []
        for _ in range(decisions):
            board, key = self.decide(policy, raw)
            rows.append((board.player.position, key, policy.last_reason,
                         damaging_ground.hurts_here(policy, board)))
            raw["turn"] += 5
            raw["messages"] = []
            offset = STEPS.get((key or "").lstrip("\x1b"))
            if offset is None:
                continue
            target = Position(board.player.position.y + offset[0], board.player.position.x + offset[1])
            # Dirt (terrain 88, no REMEMBER) leaves the board out of view; the policy's
            # floor memory still holds it.
            grid = board.grid_at(target) or policy._remembered_grids.get(target)
            if grid is not None and grid.passable and not grid.has_monster:
                raw["player"]["y"], raw["player"]["x"] = target.y, target.x
                raw["detected_monsters"] = raw["detected_monsters"] + raw["visible_monsters"]
                raw["visible_monsters"] = []
                for cell in raw["grid_map"]["cells"]:
                    cell.pop("m", None)
        return rows


class StepOffSensedOccupantRecordedTest(Replay):
    def test_recorded_alternation(self):
        hidden, shown = self.board("a", A_HIDDEN_TURN), self.board("a", A_SHOWN_TURN)
        self.assertEqual((here(hidden), here(shown)), (HIDDEN, SHOWN))
        for raw in (hidden, shown):
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            self.assertEqual(board.grid_at(here(raw)).terrain_id, COLD_ZONE)
        self.assertNotIn((DOOR.y, DOOR.x), cells(hidden["visible_monsters"]))
        self.assertIn((DOOR.y, DOOR.x, OGRE),
                      [(m["y"], m["x"], m["race_id"]) for m in hidden["detected_monsters"]])
        self.assertIn((DOOR.y, DOOR.x), cells(shown["visible_monsters"]))
        self.assertEqual(self.recorded("a", A_HIDDEN_TURN), ("1", STEP_OFF))
        self.assertEqual(self.recorded("a", A_SHOWN_TURN), ("9", STEP_OFF))

    def test_the_step_off_never_turns_to_a_door_held_out_of_sight(self):
        policy = self.replay_to("a", A_HIDDEN_TURN)
        board, key = self.decide(policy, self.board("a", A_HIDDEN_TURN))
        self.assertEqual(policy.last_reason, STEP_OFF)
        offset = STEPS[key]
        step = Position(HIDDEN.y + offset[0], HIDDEN.x + offset[1])
        self.assertNotEqual(step, SHOWN)
        self.assertGreater(step.distance_to(DOOR), HIDDEN.distance_to(DOOR))
        # The board where the ogre is in view steps the same way.
        _board, key = self.decide(policy, self.board("a", A_SHOWN_TURN))
        self.assertEqual((key, policy.last_reason), ("9", STEP_OFF))

    def test_the_walk_reaches_safe_ground_without_turning_back(self):
        policy = self.replay_to("a", A_HIDDEN_TURN)
        rows = self.walk(policy, self.board("a", A_HIDDEN_TURN), 12)
        positions = [row[0] for row in rows]
        first_safe = next(index for index, row in enumerate(rows) if not row[3])
        self.assertEqual(len(set(positions[:first_safe + 1])), first_safe + 1, rows)
        self.assertNotIn(SHOWN, positions[:first_safe + 1], rows)


if __name__ == "__main__":
    unittest.main()
