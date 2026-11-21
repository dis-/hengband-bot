"""The approach to *Destruction* walks to the monster the use asks about (n1-c life-216, 80F).

n1-c life-216 (Magic-Eater Lv 50), Angband 80F, 2026-11-17 08:46-08:47, loop-detected.  Since the
owner's 2026-11-17 「両方の条件を外して直して」 a sleeping T1 and one whose sensing radius the player
stands outside are *Destruction*'s targets, and the approach walks toward them.  Two T1s were
sensed: an awake ファナティック・ウォーモンガー (race 1227) at (27,69), 13-14 cells off, and a sleeping
1188 at (16,78), 20 off, the more dangerous from contact.  The walk aimed at the nearest cell within
13 of either (1227's), but the use asks about the most dangerous of the monsters it leaves
(destruction_use ``reach_subject``: 1188), so at (36,77), 1227 in reach, the use declined;
``approach_owns`` (any target in reach and the use refused) gave the board up, the remembered
approach stepped toward 1188, and on the next board the walk turned back to 1227's radius:
'1' (36,79)->(37,78), '7' ->(36,77), '3' ->(37,78), '9' ->(36,79), until the loop detector.

The fix (threat_tiers ``approach_subject``): the walk, its ownership and the remembered walk read
the one monster the use asks about.  Since n1-b life-413 (2026-11-22, the 80F livelocks) a subject
with no known way into its reach is passed over for the next most dangerous one with a way (the use
fires when any one of the leaving hostiles is in the sure radius, owner 2026-11-17 Q1
「脅威のどれか1体が半径13以内なら使う」): at (36,77), where the sleeper has no way, the subject is the
warmonger in reach and the use fires, so the round does not begin.

Recorded (tests/fixtures/approach-subject-20261117.json.gz, see
tests/extract_approach_subject_1117_fixture.py): the 43 player-turn boards up to turn 4552007,
decided in order through one policy's ``choose_key``.  DECLARED RECONSTRUCTED: the absorbed
*Destruction* list row (22 charges at 95%; the capture keeps the racial power list only).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_capability, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "approach-subject-20261117.json.gz"
ROUND = {4551994: Position(36, 79), 4552000: Position(37, 78), 4552002: Position(36, 77),
         4552007: Position(37, 78)}
WARMONGER, SLEEPER = 1227, 1188
FIRST_APPROACH = 4551949  # the approach toward a sleeping 881 at (36,70), 16 cells off


class ApproachSubjectRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.rows = cls.replay()

    @classmethod
    def replay(cls):
        directory = TemporaryDirectory()
        cls.directory = directory
        policy = _policy(Path(directory.name), cls.monrace)
        first = parse_snapshot(copy.deepcopy(cls.data["boards"][0]), cls.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        rows = {}
        for raw in cls.data["boards"]:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.monrace))
            key = policy.choose_key(board)
            strong = threat_tiers._sensed_strong(policy, board)[1]
            targets = threat_tiers._approach_targets(policy, board, strong) if strong else []
            subject = threat_tiers.approach_subject(policy, board, targets) if targets else None
            rows[board.turn] = (board.player.position, key, policy.last_reason,
                                subject.race_id if subject is not None else None)
            if key:
                policy.confirm_key_posted(key)
        return rows

    def test_the_record_rounds_the_three_cells_by_the_approach(self):
        recorded = {row["turn"]: row for row in self.data["decisions"]}
        for turn, cell in ROUND.items():
            row = recorded[turn]
            self.assertEqual(Position(row["position"]["y"], row["position"]["x"]), cell)
            self.assertEqual(row["reason"], threat_tiers.APPROACH_REASON)
        self.assertEqual([recorded[turn]["key"] for turn in ROUND], ["1", "7", "3", "9"])
        self.assertEqual(self.data["decisions"][-1]["reason"], "loop-detected")

    def test_the_use_asks_about_the_sleeper_where_it_has_a_way(self):
        self.assertEqual(self.rows[4551994][3], SLEEPER, self.rows[4551994])

    def test_without_a_way_to_the_sleeper_the_warmonger_in_reach_is_destroyed(self):
        """At (36,77) the sleeper has no known way; the warmonger, in reach, is the subject and
        the use fires (recorded: the approach stepped '3' back, the round's third move)."""
        position, key, reason, subject = self.rows[4552002]
        self.assertEqual(position, Position(36, 77))
        self.assertEqual(subject, WARMONGER)
        self.assertTrue(reason.startswith("emergency:destruction"), self.rows[4552002])
        self.assertNotEqual(self.rows[4552007][2], threat_tiers.APPROACH_REASON, self.rows[4552007])

    def test_the_approach_still_walks_where_it_can(self):
        """Owner 2026-11-17: a sleeping T1 out of reach is gone to (the walk toward 881)."""
        self.assertEqual(self.rows[FIRST_APPROACH][2], threat_tiers.APPROACH_REASON,
                         self.rows[FIRST_APPROACH])


if __name__ == "__main__":
    unittest.main()
