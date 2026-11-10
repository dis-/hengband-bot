"""n1-b life-367, town, 2026-11-10 20:52: the Mountain 50F is no recall destination.

Owner 2026-11-10 (the deep-dive report's P3, verbatim): 「守護者が T1 の最下層は、*破壊* の有無に
関係なく帰還先にしない。」  The Mountain's last floor is 50F, its guardian 大鷲王『ソロンドール』
(speed +35, summons) is placed there on every generation, and n1-b recalled there 116 times
in a day (decision 11796 here: town:recall-to-alt-dungeon "rgg", the Mountain).

Recorded (tests/extract_mountain_guardian_landing_1110_fixture.py): the town board of decision
11796.  The pins read the departure's destination producer (``_town_recall_destination``),
its landing check (``_recall_destination_safe``) and the guardian valve's choice
(``_pick_alternate_dungeon``) on that board, after the policy observed it through
choose_key; the live decision on this board was the recall itself, which a fresh policy does
not reach before its own town errands (shop travel).
DECLARED CONSTRUCTED: the absorbed power list (the live process had read it; the *Destruction*
row is what the 50F depth gate asks); the skill-exp list (test_sealed_pocket_quest_1105's).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import guardian_landing, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "mountain-guardian-landing-1110.json.xz"
MOUNTAIN, CASTLE, ORC_CAVE = 14, 12, 3
_undo_past_junk = None


def setUpModule():
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class MountainGuardianLandingRecordedTest(unittest.TestCase):
    def setUp(self):
        rows = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        self.raw = json.loads(rows[0])
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(self.raw, self.monrace)
        policy.prime(board)
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        listed = dict(copy.deepcopy(self.raw), turn=self.raw["turn"] - 1,
                      _magic_eater_power_list=power_list("staff", row("*破壊*", 5, current=3, count=3)))
        observe_lists(policy, parse_snapshot(listed, self.monrace))
        self.board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(self.raw), self.monrace))
        policy.choose_key(self.board)
        self.policy = policy

    def test_the_guardian_reads_t1_and_the_landing_is_its_floor(self):
        info = self.policy._dungeon_knowledge[MOUNTAIN]
        self.assertEqual((info.max_depth, self.board.dungeon_recall_depths[MOUNTAIN]), (50, 50))
        self.assertEqual(guardian_landing.guardian_tier(self.policy, self.board, info), threat_tiers.T1)

    def test_the_mountain_is_no_recall_destination(self):
        """Live: town:recall-to-alt-dungeon to the Mountain (the target)."""
        self.assertEqual(self.policy._target_dungeon_id, MOUNTAIN)
        self.assertFalse(self.policy._recall_destination_safe(self.board, MOUNTAIN))
        self.assertEqual(self.policy._town_recall_destination(self.board), (None, MOUNTAIN))
        self.assertTrue(self.policy._recall_refused_only_for_guardian(self.board, MOUNTAIN))

    def test_the_guardian_valve_takes_the_deepest_that_passes(self):
        """Angband first (owner 2026-11-07), here also the deepest landing that passes (70)."""
        self.assertEqual(self.policy._pick_alternate_dungeon(
            self.board, guardian_bounced_dungeon=MOUNTAIN), DUNGEON_ANGBAND)

    def test_a_t3_guardian_floor_stays_a_destination(self):
        """The Orc cave (conquered) and a T3 guardian are untouched."""
        self.assertFalse(guardian_landing.t1_landing(self.policy, self.board, ORC_CAVE, 23))


if __name__ == "__main__":
    unittest.main()
