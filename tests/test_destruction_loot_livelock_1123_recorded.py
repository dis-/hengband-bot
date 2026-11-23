"""destruction_loot's place walk and fetch hold across the board the T1 reading is lost on (1123).

The measurement C:/hengband-backups/pdca/deep-efficiency-effect-1123/REPORT.md: 11 of the 12
``livelock:recall-escape`` visit ends on Angband 80F/82-95F after the 11-22 deep fixes were
destruction-loot:place / destruction-loot:fetch (owner 2026-11-17 「価値の高い品は先に拾ってから
撃つ」) against explore.  Two of them, recorded (tests/extract_destruction_loot_livelock_1123_fixtures.py):

- n1-c life-221 (Angband 80F, 11:42): at (11,96) the sensed group (a dozen 268s, 422s, 569s,
  608s and the sleeping 1225) read T1, the sensed T1 approach owned it (threat_tiers
  ``sensed_t1_destruction_key``) and destruction_loot, the pile at (5,82) inside the use's worst
  radius, stepped '6' toward its clean place (11,98).  At (11,97) four of the group were past the
  telepathy's range, the group read T1 no more, and the approach was not remembered (only its
  walk and its use were: threat_tiers ``APPROACH_MEMORY``), so nothing asked the committed place
  and explore stepped '4' straight back; four rounds, then the livelock's Recall (4405279).
- n1-b life-416 (Angband 95F, 15:13): the same with the fetch, '3' from (10,63) toward the pile
  at (13,66), and explore's '7' back from (11,64) (the ordinary loot walk, which would continue a
  committed fetch, was blocked there by a summoner); the livelock's Recall at 4074861.

Now destruction_loot's answer for the approach is remembered as the approach's walk is
(threat_tiers ``_remember_loot_step``), so on the next board the remembered approach asks the
committed place or fetch again: one decision on both cells, until the use or the plan's own
bounds (destruction_loot ``DECISIONS_MAX``).

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): one staff
row of *Destruction*, 22 charges at 95% (as tests/test_n1c_217_approach_loot_1119_recorded.py).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_loot, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
N1C = FIXTURES / "destruction-loot-livelock-n1c-221-1123.jsonl.gz"
N1B = FIXTURES / "destruction-loot-livelock-n1b-416-1123.jsonl.gz"
ESCAPE = "livelock:recall-escape"


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class DestructionLootLivelockRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.decided = {"n1c": cls.drive(_boards(N1C)), "n1b": cls.drive(_boards(N1B))}

    @classmethod
    def drive(cls, boards):
        directory = TemporaryDirectory()
        try:
            policy = _policy(Path(directory.name), cls.monrace)
            first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(boards[0]), cls.monrace))
            policy.prime(first)
            policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
            decided = []
            for raw in boards:
                board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.monrace))
                policy._me_device_lists = {"staff": (board.turn, ({
                    "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
                    "max": 22, "fail": 5, "success": 95},))}
                key = policy.choose_key(board)
                decided.append((board.turn, board.player.position, key, policy.last_reason))
                if key:
                    policy.confirm_key_posted(key)
            return decided
        finally:
            directory.cleanup()

    def at(self, name, turn):
        return next(row for row in self.decided[name] if row[0] == turn)

    def test_n1c_the_place_walk_holds_on_both_cells(self):
        # Recorded: destruction-loot:place '6' at (11,96), explore '4' at (11,97), alternating.
        for turn in (4405254, 4405262, 4405269, 4405275):
            _, position, key, reason = self.at("n1c", turn)
            self.assertEqual(position, Position(11, 96))
            self.assertEqual((key, reason), ("6", destruction_loot.PLACE_REASON), turn)
        for turn in (4405259, 4405266, 4405272, 4405279):
            _, position, key, reason = self.at("n1c", turn)
            self.assertEqual(position, Position(11, 97))
            self.assertEqual((key, reason), ("6", destruction_loot.PLACE_REASON), turn)

    def test_n1b_the_fetch_holds_on_both_cells(self):
        # Recorded: destruction-loot:fetch '3' at (10,63), explore '7' at (11,64), alternating.
        for turn in (4074842, 4074847, 4074852, 4074857):
            _, position, key, reason = self.at("n1b", turn)
            self.assertEqual(position, Position(10, 63))
            self.assertEqual((key, reason), ("3", destruction_loot.FETCH_REASON), turn)
        for turn in (4074844, 4074849, 4074855, 4074858):
            _, position, key, reason = self.at("n1b", turn)
            self.assertEqual(position, Position(11, 64))
            self.assertEqual((key, reason), ("3", destruction_loot.FETCH_REASON), turn)

    def test_no_livelock_recall(self):
        for name in ("n1c", "n1b"):
            self.assertNotIn(ESCAPE, [row[3] for row in self.decided[name]], name)


if __name__ == "__main__":
    unittest.main()
