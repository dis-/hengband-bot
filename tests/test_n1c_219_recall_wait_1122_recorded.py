"""n1-c life-219's last minute on Angband 80F (2026-11-22 05:56:03-05:56:13), recorded: the ranged
breeders one *Destruction* did not clear, and the T1 known only by telepathy during the countdown.

1. Owner 2026-11-22 (verbatim) 「群れの数に関わらず破壊対象とする。1度で消しきれないなら帰還を読む。」:
   混沌 (race 815: MULTIPLY, KILL_WALL, BR_CHAO) bred back after the first absorbed *Destruction*
   (decision 14393, turn 2751382) and the bot stacked eight more in about four seconds (the
   second at 14398, turn 2751421), read the Recall with none left (14418) and died to the swarm
   and 『マダム・デビ』 during its countdown.  Now a ranged breeder on 50F+ is a target whatever the
   group's size (threat_tiers ``_sensed_strong``), and once a use has landed among them and they
   are shown again (destruction_use ``comeback_races``) the Recall is read
   (``breeder_comeback_recall_key``, the above-emergency layer); their races are no sensed T1
   meanwhile, so the charges left guard the countdown.

2. Owner 2026-11-22 「撃つ」 (the 11-01 「勝てない敵が射程内にいればいつでも使って良い」 takes a monster
   known only by detection with a line of fire): decisions 14437-14443, the *Destruction* spent,
   the Recall counting down, 『マダム・デビ』 (T1 alone, awake) 10 off seen only by the telepathy;
   the bot waited or healed and she breathed confusion, nether and chaos.  Now the absorbed
   Teleport Away is aimed at a cell whose beam passes her (me_powers ``sensed_threat_key``,
   ``beam_cell``): the player's line to her own cell (34,27) stops at the wall (36,22) her breath
   went round, so the cursor goes to (34,26) and PROJECT_THRU carries the beam through her.

Recorded: tests/fixtures/n1c-219-recall-wait-1122.jsonl.gz (extract_n1c_219_recall_wait_1122_fixture)
and the town-arrival checkpoint of tests/fixtures/n1c-219-death-1122.pkl.xz (05:54:32: 9 of 9
absorbed *Destruction*, the absorbed wand of Teleport Other 50 of 50 at 95%).
DECLARED CONSTRUCTED: the checkpoint predates the dive, so (1) its map memory (an earlier 80F
visit's, the same grid region) is dropped and this floor's boards are fed in order through the
decisions; (2) for item 2 the absorbed *Destruction* is emptied (the live floor spent its nine:
the decision log reads it missing from 14418 on).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import destruction_use, me_powers, threat_tiers
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.me_device_attacks_input import compile_device
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURES = Path(__file__).with_name("fixtures")
CASE = pickle.loads(lzma.decompress((FIXTURES / "n1c-219-death-1122.pkl.xz").read_bytes()))
with gzip.open(FIXTURES / "n1c-219-recall-wait-1122.jsonl.gz", "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
UNMAKER, DEBBY = 815, 1032
MET, FIRST_USE, SECOND_USE = 2751340, 2751382, 2751421
LANDING, DEBBY_IN_FIRE, DEBBY_LAST = 2751660, 2751714, 2751726
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")
COMEBACK = "breeder-comeback:recall"
SENT_AWAY = "me-power:sensed-t1-in-line:teleport-away"


def restored(*, destruction_spent=False):
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    policy._remembered_grid_region = None
    if destruction_spent:
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        policy._me_device_lists = dict(lists, staff=(turn, tuple(
            dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)))
    return policy


def drive(policy, first, last):
    """[(turn, key, reason)] of the recorded boards from ``first`` to ``last``."""
    decided, previous = [], None
    for turn in sorted(BOARDS):
        if not first <= turn <= last:
            continue
        raw = copy.deepcopy(BOARDS[turn])
        if previous is not None:
            raw["_completed_operation_owner"] = previous
        key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        decided.append((turn, key, policy.last_reason))
        if key:
            policy.confirm_key_posted(key)
        previous = policy.last_reason if key else None
    return decided


class BreederComebackRecallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = restored()
        cls.decided = drive(cls.policy, MET, SECOND_USE)

    def test_the_first_use_lands_among_the_unmakers(self):
        self.assertIn((FIRST_USE, *DESTRUCTION), self.decided)
        board = parse_snapshot(copy.deepcopy(BOARDS[FIRST_USE]), self.policy._monrace_knowledge)
        self.assertTrue(destruction_use.ranged_breeder(self.policy, UNMAKER))
        self.assertGreaterEqual(
            sum(monster.race_id == UNMAKER
                for monster in (*board.visible_monsters, *board.detected_monsters)), 7)

    def test_no_second_use_but_the_recall(self):
        after = [(turn, key, reason) for turn, key, reason in self.decided if turn > FIRST_USE]
        # Recorded: the second absorbed *Destruction* at 14398 (turn 2751421), eight in all.
        self.assertFalse([row for row in after if row[2].startswith("emergency:destruction")], after)
        recalls = [row for row in after if row[2] == COMEBACK]
        self.assertTrue(recalls, after)
        self.assertLessEqual(recalls[0][0], SECOND_USE)
        self.assertEqual(self.decided[-1][1:], ("rh", COMEBACK))

    def test_the_unmakers_back_are_no_sensed_t1(self):
        board = self.policy._with_grid_memory(parse_snapshot(
            copy.deepcopy(BOARDS[SECOND_USE]), self.policy._monrace_knowledge))
        self.assertEqual(destruction_use.comeback_races(self.policy, board), frozenset({UNMAKER}))
        _, strong = threat_tiers._sensed_strong(self.policy, board)
        self.assertFalse([monster for monster in strong if monster.race_id == UNMAKER])


class SensedT1TeleportAwayTest(unittest.TestCase):
    def decide(self, turn):
        policy = restored(destruction_spent=True)
        return policy, drive(policy, LANDING, turn)[-1]

    def test_debby_in_fire_is_sent_away(self):
        for turn in (DEBBY_IN_FIRE, DEBBY_LAST):
            with self.subTest(turn=turn):
                policy, (_, key, reason) = self.decide(turn)
                # Recorded: return:wait-recall '5' (14439), return:wait-recall '5' (14443).
                self.assertEqual((key, reason), ("mCn@34,26", SENT_AWAY))
                # The production executor port: the rod of Teleport Away, the cursor to (34,26).
                _, (step,) = compile_device(key, reason)
                self.assertEqual((step.kind, step.sval, step.goal), ("rod", 13, (34, 26)))
                board = parse_snapshot(copy.deepcopy(BOARDS[turn]), policy._monrace_knowledge)
                self.assertTrue(destruction_use.means_spent(policy, board))
                self.assertTrue(board.player.recalling)
                debby = next(m for m in board.detected_monsters if m.race_id == DEBBY)
                self.assertEqual(debby.position, Position(34, 27))
                self.assertFalse(board.visible_monsters)

    def test_the_aimed_cell_beam_passes_her(self):
        policy = restored(destruction_spent=True)
        board = parse_snapshot(copy.deepcopy(BOARDS[DEBBY_IN_FIRE]), policy._monrace_knowledge)
        here, there = board.player.position, Position(34, 27)
        self.assertIsNone(me_powers.beam_direction(policy, board, here, there))
        self.assertEqual(me_powers.beam_cell(policy, board, here, there), Position(34, 26))

    def test_control_with_the_means_held_no_teleport_away(self):
        policy = restored()
        _, key, reason = drive(policy, LANDING, DEBBY_IN_FIRE)[-1]
        self.assertNotEqual(reason, SENT_AWAY)


if __name__ == "__main__":
    unittest.main()
