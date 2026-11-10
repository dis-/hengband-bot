"""The walk to a hunted target's shown cell ends beside it (hunt_target.route_key).

Recorded n1-b life-335, Magic-Eater, Angband 24F, RANDOM quest 41, target
『アルベリヒ』 (race 419, INVISIBLE and TPORT), 2026-11-07 09:00:30-09:00:35: the
target was meleed at (31,51) from (31,50) and vanished; hunt:detected-target then read
'2' at (31,50) and '8' at (32,50) -- both beside the remembered (31,51) -- until the
loop detector stopped the bot.  The goal "a cell within 1 of the shown cell" never
counts the player's own cell, and no board certified the cell empty because an
INVISIBLE race is never seen gone.  Boards: tests/fixtures/detected-hunt-335-1107.json.xz
(tests/extract_detected_hunt_1107_fixtures.py), every decision through choose_key.

n1-b life-334 04:57:52 and life-335 09:03:55: two sleeping Black ogres 8-9 away, or a
Yeek 14 away, in sight made the walk yield to seek-loot, which stepped out of their
sight, and the walk stepped in again.

DECLARED CONSTRUCTED: the sleeping and awake non-target hostiles added to the recorded
(30,49) board of the walk.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import hunt_target
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "detected-hunt-335-1107.json.xz"
TARGET_RACE = 419
SHOWN = (31, 51)
WALK_TURN = 1835609  # (30,49), recorded hunt:detected-target '3'
LOOP_FIRST_TURN = 1835613  # (31,50), recorded '2'; then (32,50) '8', ...
BLACK_OGRE = 262  # 黒オーガ (Black ogre)
YEEK_RACE = 52  # Blue yeek


class DetectedHuntWalkRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.boards = [json.loads(line) for line in payload["boards"]]
        cls.skill = payload["skill"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        policy = HengbotPolicy(monrace_knowledge=self.races)
        policy.prime(parse_snapshot(copy.deepcopy(self.boards[0]), self.races))
        self.policy = policy
        self.before_walk = None
        self.decisions = {}
        for raw in self.boards:
            if raw["turn"] == WALK_TURN:
                self.before_walk = copy.deepcopy(policy)
            self.decisions[raw["turn"]] = self.decide(policy, raw)

    def decide(self, policy, raw):
        policy.consume_skill_knowledge({**self.skill, "player": {"level": raw["player"]["level"]}})
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.races))
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return key, policy.last_reason

    def board(self, turn):
        return next(raw for raw in self.boards if raw["turn"] == turn)

    def test_the_target_was_shown_beside_the_loop_cells(self):
        self.assertEqual(self.policy._monrace_knowledge.get(TARGET_RACE).flags & {"INVISIBLE"},
                         {"INVISIBLE"})
        self.assertEqual(self.decisions[WALK_TURN], ("3", hunt_target.REASON))

    def test_beside_the_shown_cell_the_walk_waits_once_and_gives_the_cell_up(self):
        loop = [turn for turn in self.decisions if turn >= LOOP_FIRST_TURN]
        self.assertGreater(len(loop), 6)
        first, *rest = loop
        self.assertEqual(self.decisions[first], ("s", hunt_target.ARRIVED_REASON))
        for turn in rest:
            self.assertNotIn(self.decisions[turn][1],
                             (hunt_target.REASON, hunt_target.ARRIVED_REASON), turn)
        visit = getattr(self.policy, hunt_target.MEMORY)
        self.assertEqual((visit.race, visit.position), (TARGET_RACE, None))

    def _with_monster(self, race, distance, asleep):
        raw = copy.deepcopy(self.board(WALK_TURN))
        y, x = raw["player"]["y"], raw["player"]["x"] - distance  # DECLARED: along the row
        monster = {"index": 900, "race_id": race, "y": y, "x": x, "asleep": asleep,
                   "confused": False, "fast": False, "fearful": False, "friendly": False,
                   "health": "unhurt", "invulnerable": False, "level": None,
                   "name": "constructed", "pet": False, "slow": False, "stunned": False}
        raw["visible_monsters"] = [monster]
        return raw

    def test_a_sleeping_or_distant_other_hostile_does_not_stop_the_walk(self):
        for race, distance, asleep in ((BLACK_OGRE, 8, True), (YEEK_RACE, 14, False)):
            with self.subTest(race=race, distance=distance, asleep=asleep):
                policy = copy.deepcopy(self.before_walk)
                raw = self._with_monster(race, distance, asleep)
                board = parse_snapshot(copy.deepcopy(raw), self.races)
                self.assertTrue(any(m.race_id == race for m in board.visible_monsters))
                self.assertEqual(self.decide(policy, raw), ("3", hunt_target.REASON))

    def test_an_awake_hostile_within_hunt_range_still_owns_the_board(self):
        policy = copy.deepcopy(self.before_walk)
        _key, reason = self.decide(policy, self._with_monster(YEEK_RACE, 5, False))
        self.assertNotEqual(reason, hunt_target.REASON)


if __name__ == "__main__":
    unittest.main()
