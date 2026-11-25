"""The sensed-T1 approach walks to a cell where the use is not refused for its place (n1-b life-411, 1118).

Recorded (tests/fixtures/n1b-411-t1-walk-approach-1118.jsonl.gz: the capture
~/hengbot-soak/n1-b/life-411/captures/20261118-212951-loop-detected/state.jsonl, turns
7411511-7411528): Castle 65F (the dungeon's last floor), build bot-54196e30b, the Magic-Eater Lv50
with Recall counting down.  Two T1s known by telepathy alone (デイドラ・ホワイト・ドラゴン, index 47,
and ストーム・ワイアーム, index 49, the use's subject), awake, the player inside their sensing radius;
the floor's guardian 皇帝『レイザーク』 (index 13, T2 alone, so kept: destruction_use
``_guardian_kept``) at (17,61).  At (10,73) the wyrm at (23,73) was 13 off, in reach, but the
guardian stood 15 off, inside the worst radius 17: the use was refused (``_spared_in_circle``),
``approach_owns`` gave the board to the sensed leave, whose walk stepped '9' to (9,74), 14 off; there
the approach owned the board again and stepped '1' back: until the loop detector (21:29:51).  The
ping-pong guard left it alone (the leave walk is a survival reason, and the combat layer's walks do not
read the left cells).  Now the approach's walk and its ownership read one goal, a cell with the subject
in the sure radius and nothing to keep in the worst radius (destruction_use ``use_cell``): on both
boards the approach walks on east toward (11,77).  DECLARED RECONSTRUCTED: the absorbed *Destruction*
list row (22 charges at 95%; the capture carries no list).  DECLARED CONSTRUCTED: the board without the
guardian (the use is due at (10,73)), its last shown cell forgotten as well (monster_memory.KEPT_GUARDIAN,
n1-c life-222 2026-11-25: a kept guardian out of detection is judged at its last shown cell).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_use, me_capability, monster_memory, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-t1-walk-approach-1118.jsonl.gz"
LEFT_IN_REACH = 7411524   # (10,73): recorded sensed-t1:walk '9'
STEPPED_BACK = 7411528    # (9,74): recorded sensed-t1:approach-destruction '1', back into (10,73)
GUARDIAN_INDEX = 13
SUBJECT_INDEX = 49


def _without_guardian(raw):
    raw = copy.deepcopy(raw)
    raw["detected_monsters"] = [row for row in raw["detected_monsters"] if row["index"] != GUARDIAN_INDEX]
    return raw


class T1WalkApproachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, last, edit=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        for raw in self.boards:
            if raw["turn"] == last and edit is not None:
                raw = edit(raw)
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == last:
                return policy, board
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("no board %d" % last)

    def decide(self, last, edit=None):
        policy, board = self.replay(last, edit)
        key = policy.choose_key(board)
        return policy, board, key, policy.last_reason

    def test_the_use_is_refused_for_the_guardian_in_reach(self):
        policy, board = self.replay(LEFT_IN_REACH)
        self.assertEqual(board.player.position, Position(10, 73))
        subject = next(m for m in board.detected_monsters if m.index == SUBJECT_INDEX)
        self.assertTrue(destruction_use.in_sure_radius(board, subject))
        spared = destruction_use.spared_positions(policy, board)
        self.assertEqual(spared, [Position(17, 61)])
        self.assertFalse(destruction_use.use_cell(board, subject, spared))
        self.assertTrue(destruction_use.use_cell(board, subject, spared, centre=Position(11, 77)))

    def test_in_reach_the_approach_walks_on_instead_of_the_leave(self):
        _, board, key, reason = self.decide(LEFT_IN_REACH)
        # Recorded: sensed-t1:walk '9' (the leave), then the approach walked back.
        self.assertEqual(reason, "sensed-t1:approach-destruction")
        self.assertEqual(key, "9")

    def test_out_of_reach_the_approach_does_not_step_back(self):
        _, board, key, reason = self.decide(STEPPED_BACK)
        self.assertEqual(board.player.position, Position(9, 74))
        # Recorded: sensed-t1:approach-destruction '1', back into (10,73).
        self.assertEqual(reason, "sensed-t1:approach-destruction")
        self.assertEqual(key, "3")

    def test_without_the_guardian_the_use_is_due_in_reach(self):
        policy, board = self.replay(LEFT_IN_REACH, _without_guardian)
        monster_memory.forget_floor(policy, monster_memory.KEPT_GUARDIAN)
        policy.choose_key(board)
        reason = policy.last_reason
        self.assertTrue(reason.startswith(destruction_use.REASON), reason)

    def test_approach_owns_reads_the_walk(self):
        policy, board = self.replay(LEFT_IN_REACH)
        _, strong = threat_tiers._sensed_strong(policy, board)
        self.assertTrue(threat_tiers.approach_owns(policy, board, strong))


if __name__ == "__main__":
    unittest.main()
