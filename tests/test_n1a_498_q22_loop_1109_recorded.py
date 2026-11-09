"""A sleeping orc shaman is no reason to retake the Q22 hold (n1-a life-498, 11-09).

Quest 22 (Orc Camp), Lv22.  The bot held the one-entry cell (9,58), where nothing
was in view.  After the quiet opening hold the placement sweep stepped west to
(9,57); from there a sleeping orc shaman (race 162, the first priority target) was
in view at (11,38), 20 cells away, and retake-hold stepped back east, where it was
out of view again: 4/6 until the loop guard stopped the bot, three times in 35 s
(the restarted bot rebuilt the hold, held 80 quiet turns and repeated it).  Both
moves came from _quest_strategy_may_leave_hold and its negation, which counted the
sleeping shaman as an active mover.  Owner 2026-11-09 「眠る敵では戻らない」: a
sleeping mobile enemy is no reason to return to the hold; the sweep goes on, closes
on it and kills it by the sweep's rules.  Awake enemies still are, and so is a
strong sleeper (owner 2026-11-07: a strong monster is kept away from even asleep).

Recorded: tests/extract_n1a_498_q22_loop_1109_fixture.py, every decision of the three
bot processes with its board.  Each run is replayed from a fresh policy primed on the
run's first board, every board through public choose_key: runs 2 and 3 are restarted
processes, so this is exactly the live construction (the hold is rebuilt from the
position, the 80 quiet turns are counted by the real producer).  Run 1 is the tail of a
longer process: DECLARED CONSTRUCTED, its replay starts fresh on the tail's first board
(the hill-orc wave fought at the hold) and must reproduce the recorded decisions up to
the first sweep step as well.  The skill-exp cache is DECLARED CONSTRUCTED from the
board's level (as in test_n1c_174_hazard_loop_1109_recorded); the character calibration
is the capture's own sidecar.

Physics from the first board at (9,57) on (DECLARED CONSTRUCTED): that board with the
player moved by each answered step; the monsters keep their cells and stay asleep;
other commands only advance the turn.  The visibility flags stay those of (9,57).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "n1a-498-q22-loop-1109.json.gz"
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
HOLD = Position(9, 58)
SWEEP_STEP = Position(9, 57)
SHAMAN = 162
STRONG = 653
RETAKE = "quest-strategy:retake-hold"
SWEEP = "quest-strategy:placement-sweep"
ENGAGE = "quest-strategy:sweep-engage-mobile"
WALK = 12


class Q22SleepingShaman(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def board(self, raw):
        raw = copy.deepcopy(raw)
        raw["grid_map"] = copy.deepcopy(self.data["grid_maps"][raw["grid_map"]])
        return raw

    def fresh(self, first):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        calibration = Path(directory.name) / "character-calibration.json"
        calibration.write_text(json.dumps(self.data["calibration"]), encoding="utf-8")
        policy.prime(parse_snapshot(copy.deepcopy(first), self.monrace))
        policy._skill_exp_cache = (0, 0, first["player"]["level"], None)
        return policy

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return board, str(key), policy.last_reason

    def replay(self, run):
        """(policy, rows of (recorded, decided), the raw (9,57) board or None)."""
        boards = [self.board(raw) for raw in run["boards"]]
        policy = self.fresh(boards[0])
        rows = []
        for recorded, raw in zip(run["decisions"], boards):
            if recorded["reason"].startswith("periodic:skill-exp"):
                continue  # the query the constructed skill-exp cache answers
            board, key, reason = self.decide(policy, raw)
            rows.append(((recorded["key"], recorded["reason"]), (key, reason)))
            if board.player.position == SWEEP_STEP:
                return policy, rows, raw
        return policy, rows, None

    @staticmethod
    def move(raw, board, key):
        raw = copy.deepcopy(raw)
        raw["turn"] += 10
        raw["messages"] = []
        offset = STEPS.get(key.lstrip("\x1b"))
        if offset is None:
            return raw
        here = board.player.position
        target = Position(here.y + offset[0], here.x + offset[1])
        grid = board.grid_at(target)
        if grid is not None and grid.passable and not grid.has_monster:
            raw["player"]["y"], raw["player"]["x"] = target.y, target.x
        return raw

    def test_recorded_runs_reach_the_first_sweep_step(self):
        for run in self.data["runs"]:
            with self.subTest(capture=run["capture"]):
                _, rows, raw = self.replay(run)
                self.assertIsNotNone(raw)
                # Every board before (9,57) decides as recorded: the wave fought at
                # the hold (run 1), the quiet hold and the first sweep step west.
                for recorded, decided in rows[:-1]:
                    self.assertEqual(decided, recorded)
                self.assertEqual(rows[-2][0], ("4", SWEEP))
                self.assertEqual(rows[-1][0], ("6", RETAKE))

    def test_sleeping_shaman_in_view_does_not_retake_the_hold(self):
        for run in self.data["runs"]:
            with self.subTest(capture=run["capture"]):
                _, rows, raw = self.replay(run)
                board = parse_snapshot(raw, self.monrace)
                (shaman,) = board.visible_monsters
                self.assertEqual((shaman.race_id, shaman.asleep), (SHAMAN, True))
                key, reason = rows[-1][1]
                self.assertNotEqual(reason, RETAKE)
                self.assertEqual(reason, ENGAGE)
                offset = STEPS[key]
                self.assertLess(offset[1], 0, key)  # on west, toward the shaman

    def test_the_sweep_closes_on_the_shaman_without_coming_back(self):
        for run in self.data["runs"]:
            with self.subTest(capture=run["capture"]):
                policy, _, raw = self.replay(run)
                shaman = Position(raw["visible_monsters"][0]["y"],
                                  raw["visible_monsters"][0]["x"])
                start = shaman.distance_to(SWEEP_STEP)
                positions, reasons = [], []
                for _ in range(WALK):
                    board, key, reason = self.decide(policy, raw)
                    positions.append(board.player.position)
                    reasons.append(reason)
                    raw = self.move(raw, board, key)
                self.assertNotIn(RETAKE, reasons, reasons)
                self.assertNotIn(HOLD, positions, positions)
                self.assertIn(22, policy._quest_strategy_post_wave_light_attempted)
                final = Position(raw["player"]["y"], raw["player"]["x"])
                self.assertLess(shaman.distance_to(final), start - 6, (positions, reasons))

    def at_sweep_step(self, run):
        """A policy replayed up to (not through) the first (9,57) board, and that board."""
        boards = [self.board(raw) for raw in run["boards"]]
        policy = self.fresh(boards[0])
        for recorded, raw in zip(run["decisions"], boards):
            if recorded["reason"].startswith("periodic:skill-exp"):
                continue
            if Position(raw["player"]["y"], raw["player"]["x"]) == SWEEP_STEP:
                return policy, raw
            self.decide(policy, raw)
        self.fail("no sweep step")

    def test_an_awake_shaman_still_retakes_the_hold(self):
        # DECLARED CONSTRUCTED: the recorded (9,57) board with the shaman awake.
        policy, raw = self.at_sweep_step(self.data["runs"][1])
        for monster in raw["visible_monsters"]:
            monster["asleep"] = False
        _, key, reason = self.decide(policy, raw)
        self.assertEqual((key, reason), ("6", RETAKE))

    def test_a_strong_sleeper_still_retakes_the_hold(self):
        # DECLARED CONSTRUCTED: the recorded (9,57) board with a sleeping 巨大首なし
        # (race 653, n1-b life-341's strong sleeper) in the shaman's cell.  Owner
        # 2026-11-07: a strong monster is kept away from even asleep.
        policy, raw = self.at_sweep_step(self.data["runs"][1])
        raw["visible_monsters"][0].update(race_id=STRONG, level=self.monrace[STRONG].level)
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        (monster,) = board.visible_monsters
        self.assertTrue(monster.asleep)
        self.assertTrue(policy._material_melee_fight(board, monster))
        _, key, reason = self.decide(policy, raw)
        self.assertEqual((key, reason), ("6", RETAKE))


if __name__ == "__main__":
    unittest.main()
