"""n1-b life-367, the Mountain 50F, 2026-11-10 20:57:23: a T1 known only by detection.

Owner 2026-11-10 (the deep-dive report's P2, verbatim): 「積極的に*破壊*で消しにいく」 (the
question: ハヤブサ (Ki-43, vision 100) and 大鷲王『ソロンドール』 sense the whole floor; 29
sensed-T1 Teleportations on T3 boards, each counted toward the two-escape return).

Recorded (tests/extract_sensed_t1_approach_1110_fixture.py): the arrival (decision 12800,
map-area), five explore steps, a *Destruction* (12806) and decision 12807 (turn 5347005,
629/629 HP), the live sensed-t1:teleport "rf" with four Ki-43 detected 19-20 cells off, none in
view.  Every board through the public choose_key, each carrying the previous decision's
completed owner as the CLI adds it.
DECLARED CONSTRUCTED: the absorbed power list (with and without *Destruction*; the live
process had read it) and the skill-exp list (as the other n1-b pins).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "sensed-t1-approach-1110.json.xz"
KI43 = (1146, 1147)
MAP = row("周辺感知", 5, current=3, count=3)
DESTRUCTION = row("*破壊*", 5, current=3, count=3)
_undo_past_junk = None


def setUpModule():
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class SensedT1ApproachRecordedTest(unittest.TestCase):
    def setUp(self):
        rows = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        self.raws = [json.loads(line) for line in rows]
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def decide(self, *rows):
        """(policy, last board, keys and reasons of every recorded board)."""
        first = self.raws[0]
        policy = _policy(self.root, self.monrace)
        board = parse_snapshot(first, self.monrace)
        policy.prime(board)
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        listed = dict(copy.deepcopy(first), turn=first["turn"] - 1,
                      _magic_eater_power_list=power_list("staff", *rows))
        observe_lists(policy, parse_snapshot(listed, self.monrace))
        decided, previous = [], None
        for raw in self.raws:
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            decided.append((policy.choose_key(board), policy.last_reason))
            previous = policy.last_reason
        return policy, board, decided

    def test_the_sensed_hawks_are_gone_to_not_left(self):
        """Live: sensed-t1:teleport "rf" (a Teleportation counted as an escape).  The hawks are
        19-20 cells off, past the sure radius, and the circle just destroyed has no known way
        toward them: the leave gives way, the circle is mapped (the rung below), and on the
        next boards (DECLARED: the recorded board ten game turns on each) the floor is walked,
        never left."""
        policy, board, decided = self.decide(MAP, DESTRUCTION)
        self.assertEqual(decided[0][1], "me-power:new-floor:map-area")
        self.assertEqual(decided[6][1], "emergency:destruction:absorbed-power")  # live 12806
        self.assertEqual(decided[-1], ("mAj", "me-power:after-destruction:map-area"))
        hawks = [m for m in board.detected_monsters if m.race_id in KI43]
        self.assertTrue(hawks)
        self.assertTrue(all(game_distance(board.player.position, m.position)
                            > destruction_use.GUARANTEED_RADIUS for m in hawks))
        self.assertTrue(threat_tiers.approach_owns(policy, board, hawks))
        previous, reasons = decided[-1][1], []
        for step in range(1, 4):
            raw = dict(copy.deepcopy(self.raws[-1]), turn=self.raws[-1]["turn"] + 10 * step,
                       messages=[], _completed_operation_owner=previous)
            policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, self.monrace)))
            previous = policy.last_reason
            reasons.append(previous)
        self.assertFalse([reason for reason in reasons if reason.startswith("sensed-t1:")
                          and reason != threat_tiers.APPROACH_REASON], reasons)

    def test_without_the_means_the_leave_is_as_before(self):
        _, _, decided = self.decide(MAP)
        self.assertEqual(decided[-1], ("rf", "sensed-t1:teleport"))


if __name__ == "__main__":
    unittest.main()
