"""Step off a crossing onto the far side, on n1-c life-174's boards (Orc cave 23F, 11-09).

From the notch (18,153)/(18,154) above a poison-puddle room (terrain 233/234) the walk
stepped onto the puddle; there an orc crossbowman in the room came into view, the shot at
it was replaced by the step off the puddle (damaging_ground.leave_first), and the only
safe cell beside was the notch it came from, where the crossbowman is out of view: back
in, back out, until the loop guard stopped the bot at 00:31 and again at 00:36.  Owner
2026-11-09 「渡った先へ出る」: the step off goes to the safe ground across, not back.

Recorded: tests/extract_n1c_174_hazard_loop_1109_fixture.py, for each of four crossings
(two per capture) the notch board and the next board, the player on the puddle as
recorded.  The policy is primed on the notch board and decides it (the real producer
remembers the last safe cell), then decides the puddle board.  Physics from there on
(DECLARED CONSTRUCTED): the puddle board with the player moved by each answered step;
monsters do not move; a melee blow kills the monster struck (it leaves the board).
The walk ends on safe ground or once the hostiles that drew the shots are dead: after
that, exploration on these boards would follow frontiers the live walk had already
explored (the boards hold no record of that walk), which this test does not judge.
The skill-exp cache is DECLARED CONSTRUCTED from the board's level, as in
test_hazard_exit_1104_recorded.  The standstill that leave_first replaces is read
through a spy on damaging_ground.step_off_key (it still decides).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot import damaging_ground
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-174-hazard-loop-1109.json.gz"
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
FIRE = "f"
BOARDS = 8


class HazardCrossing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.crossings = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def walk(self, notch, puddle):
        """(policy, notch position, rows of (position, hurts, standstill seen, key, reason))."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(notch), self.monrace))
        policy._skill_exp_cache = (0, 0, notch["player"]["level"], None)
        seen = []
        step_off = damaging_ground.step_off_key

        def spy(policy_, snapshot, key):
            seen.append(key)
            return step_off(policy_, snapshot, key)

        def decide(raw):
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            seen.clear()
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            return board, key, seen[-1] if seen else None

        rows = []
        with patch.object(damaging_ground, "step_off_key", spy):
            board, _, _ = decide(notch)
            start = board.player.position
            raw = copy.deepcopy(puddle)
            for _ in range(BOARDS):
                board, key, standstill = decide(raw)
                here = board.player.position
                hurts = damaging_ground.hurts_here(policy, board)
                rows.append((here, hurts, standstill, key, policy.last_reason))
                if not hurts:
                    break
                raw = self.move(raw, board, key)
                if not raw["visible_monsters"]:
                    break
        return policy, start, rows

    @staticmethod
    def move(raw, board, key):
        raw = copy.deepcopy(raw)
        raw["turn"] += 10
        raw["messages"] = []
        offset = STEPS.get((key or "").lstrip("\x1b"))
        if offset is None:
            return raw
        here = board.player.position
        target = Position(here.y + offset[0], here.x + offset[1])
        grid = board.grid_at(target)
        if grid is not None and grid.has_monster:
            raw["visible_monsters"] = [m for m in raw["visible_monsters"]
                                       if (m["y"], m["x"]) != (target.y, target.x)]
            for cell in raw["grid_map"]["cells"]:
                if (cell["y"], cell["x"]) == (target.y, target.x):
                    cell.pop("m", None)
        elif grid is not None and grid.passable:
            raw["player"]["y"], raw["player"]["x"] = target.y, target.x
        return raw

    def test_the_shot_on_the_puddle_becomes_a_step_across(self):
        for index, (notch, puddle) in enumerate(self.crossings):
            with self.subTest(crossing=index):
                _, start, rows = self.walk(notch, puddle)
                here, hurts, standstill, key, reason = rows[0]
                self.assertTrue(hurts, here)
                self.assertEqual((standstill or "")[:1], FIRE, rows[0])
                self.assertEqual(reason, damaging_ground.STEP_REASON)
                offset = STEPS[key]
                self.assertNotEqual(Position(here.y + offset[0], here.x + offset[1]), start)
                # Into the room, away from the notch row.
                self.assertEqual(offset[0], 1, rows[0])

    def test_the_crossing_reaches_the_far_side_without_coming_back(self):
        for index, (notch, puddle) in enumerate(self.crossings):
            with self.subTest(crossing=index):
                _, start, rows = self.walk(notch, puddle)
                entered = rows[0][0]
                positions = [row[0] for row in rows]
                # Safe ground across, or the hostiles shot at are dead from the room side.
                self.assertTrue(not rows[-1][1] or rows[-1][4] == "melee", rows)
                self.assertGreaterEqual(positions[-1].y, 21, rows)
                self.assertNotIn(start, positions, rows)
                self.assertEqual(positions.count(entered), 1, rows)
                self.assertLessEqual(len({p for p in positions}), 6, rows)
                # No standstill is answered on the puddle on the way.
                for here, hurts, _, key, _ in rows:
                    if hurts:
                        command = (key or "").lstrip("\x1b")[:1]
                        self.assertNotIn(command, damaging_ground.STANDSTILLS, (here, key))


if __name__ == "__main__":
    unittest.main()
