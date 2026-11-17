"""A shot at a summoner behind a glass wall is not taken (n1-c life-216, 1118).

Glass (TerrainDefinitions.jsonc GLASS_WALL / PERMANENT_GLASS_WALL: LOS, no PROJECTION) is seen
through and stops every bolt, arrow and ball (projection-path-calculator.cpp:94).

Recorded (tests/fixtures/n1c-216-glass-caster-1118.jsonl.gz: the last board, turn 6121006, of
~/hengbot-soak/n1-c/life-216/captures/20261118-011059-loop-detected/state.jsonl, copied to
C:/hengband-backups/pdca/captures/n1c-216-glass-caster-1118): the Glass castle's 60F, build
c2c293b34.  From (8,163) the player sees through the glass wall at (9,165) the 死の騎士 (12,171),
三上山の『大ムカデ』 (12,170), アブドゥル・アルハザード (14,172) and the others; both named casting a
summon.  ``summoner:ranged-kill:named-caster`` fired ``fi*p33336666t5`` / ``fi*p3333366t5``
40 times (policy ``_offset_fire_aim`` read the arrow's path as the line of sight) and every bolt
stopped on the glass.  DECLARED RECONSTRUCTED: the visit's summon memory
(the two casters, named in the recorded messages at turns 6120718 and 6120757).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import line_of_fire, me_ranged_first, summon_response
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import RANGED_MAX_DISTANCE
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-glass-caster-1118.jsonl.gz"
CASTERS = (597, 1088)        # 死の騎士, 三上山の『大ムカデ』
GLASS = Position(9, 165)


class GlassCasterShotRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.loads(stream.readline())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(copy.deepcopy(self.raw), self.monrace)
        self.policy.prime(board)
        self.policy._skill_exp_cache = (0, 0, board.player.level, self.policy._town_visit_epoch)
        self.board = self.policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(self.raw), self.monrace))
        memory = summon_response._memory(self.policy)
        for monster in self.board.visible_monsters:
            if monster.race_id in CASTERS:
                memory.casters.add(summon_response._plain_name(monster.name))

    def casters(self):
        return [monster for monster in self.board.visible_monsters if monster.race_id in CASTERS]

    def test_the_arrow_path_stops_on_the_glass(self):
        for monster in self.casters():
            path = line_of_fire.player_path(self.policy, self.board, self.board.player.position,
                                            monster.position, RANGED_MAX_DISTANCE)
            self.assertEqual(path[-1], GLASS, monster.name)

    def test_no_shot_at_the_casters_behind_the_glass(self):
        self.assertTrue(self.casters())
        self.assertIsNone(summon_response.caster_shot_key(self.policy, self.board),
                          self.policy.last_reason)

    def test_no_aimed_power_at_the_casters_behind_the_glass(self):
        for monster in self.casters():
            self.assertFalse(me_ranged_first._clear_projection(self.policy, self.board, monster),
                             monster.name)


if __name__ == "__main__":
    unittest.main()
