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

Owner 2026-11-11 (「回復と悲観側のずれを全部」: each carried Potion of Healing counts 300 in the
supply plan): one ハヤブサ judged alone from contact now reads T2 with the recorded pack (two
Healing drunk over six turns), so the sensed T1 leave and its *Destruction* no longer happen on
these boards (``test_one_hawk_is_a_t2_with_the_recorded_healing``).  The leave pins below run
with the Potions of Healing taken out of every board (DECLARED CONSTRUCTED, ``no_healing``), where
a lone hawk is the T1 the live process read.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.cli import _PolicyObserverScope
from hengbot.model import SV_POTION_HEALING, TVAL_POTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "sensed-t1-approach-1110.json.xz"
KI43 = (1146, 1147)
MAP = row("周辺感知", 5, current=3, count=3)
DESTRUCTION = row("*破壊*", 5, current=3, count=3)
_undo_past_junk = None


def no_healing(raw):
    """DECLARED CONSTRUCTED: the Potions of Healing out of the pack, letters re-given."""
    inventory = raw["inventory"]
    inventory[:] = [item for item in inventory
                    if not (item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_HEALING)]
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)


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

    def decide(self, *rows, change=None):
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
            if change is not None:
                change(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            decided.append((policy.choose_key(board), policy.last_reason))
            previous = policy.last_reason
        return policy, board, decided

    # Re-driven 2026-11-12 (t3-survival-1112 D, the game's spell odds: the innate ROCKET only in
    # the 2 x freq share): one ハヤブサ judged alone from contact reads T3 (its free margin 129,
    # inside the reserve 250 of B, which a decided reading enters as T2), with or without the
    # Potions of Healing, so no sensed T1 is left or gone to on these boards: the hawk in reach
    # is shot (decision 12806, live *Destruction*) and the visit ends by the recall it was on.
    # The approach itself is pinned on n1-b life-377 (test_n1b_377_approach_loot_1112_recorded).

    def test_the_sensed_hawks_are_gone_to_not_left(self):
        """Live: sensed-t1:teleport "rf" (a Teleportation counted as an escape)."""
        policy, board, decided = self.decide(MAP, DESTRUCTION, change=no_healing)
        self.assertEqual(decided[0][1], "me-power:new-floor:map-area")
        self.assertEqual(decided[6][1], "ranged:fire-target")  # live 12806: *Destruction*
        self.assertFalse([reason for _key, reason in decided if reason.startswith("sensed-t1:")])
        self.assertEqual(decided[-1][1], "return:recall")

    def test_without_the_means_the_leave_is_as_before(self):
        _, board, decided = self.decide(MAP, change=no_healing)
        self.assertFalse([reason for _key, reason in decided if reason.startswith("sensed-t1:")])
        self.assertEqual(decided[-1][1], "return:recall")

    def test_one_hawk_is_a_t2_with_the_recorded_healing(self):
        policy, board, decided = self.decide(MAP)
        self.assertFalse([reason for _, reason in decided if reason.startswith("sensed-t1:")])
        hawk = next(m for m in board.detected_monsters if m.race_id in KI43)
        with _PolicyObserverScope(policy):
            alone = threat_tiers.assess(policy, board, [hawk], contact=True)
            self.assertEqual((alone.tier, alone.free_margin, alone.reserve),
                             (threat_tiers.T3, 129, 250))
            raw = copy.deepcopy(self.raws[-1])
            no_healing(raw)
            bare = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            hawk = next(m for m in bare.detected_monsters if m.race_id in KI43)
            self.assertEqual(threat_tiers.assess(policy, bare, [hawk], contact=True).tier,
                             threat_tiers.T3)


if __name__ == "__main__":
    unittest.main()
