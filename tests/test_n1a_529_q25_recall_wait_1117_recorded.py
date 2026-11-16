"""Quest 25 on n1-a life-529 (2026-11-17 00:10:37-00:10:51): the Recall wait's rests beside the pack, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-a/life-529/captures/20261117-001053-exit-no-marker,
build bot-945ab02d2; battle phase 2, Ipsissimus, rallying):

 * On the look-out [5,2] the summons closed round the player; at decision 36515 the Healing
   potions were down to two and Word of Recall was read (``quest25:restock-recall``, owner
   2026-11-16 「隘路で迎え撃ち尽きる前に帰還」).
 * Recall active, the plan's wait (``_recall_wait``, owner 2026-11-09 「段をやめ射線外で待つ」):
   the start stair unreachable, [5,2] out of the casters' fire, damaged -- a rest ('R&\\r',
   ``quest25:rest-out-of-fire``) with eight beside, at 36516, 36518, 36521, 36526, 36528 and
   36530 (HP 732 -> 479).  A rest spends the turn (cmd-move.cpp do_cmd_rest: 100 energy) and the
   pack's blows land on it.  The player died at 36547, 125 game turns (12 ticks) after the read;
   the Recall takes 15-35 ticks (spells-world.cpp recall_player).

The rule: the wait stops the phase's steps, not the blow at an enemy beside; the rest is for a
board without one.

Recorded: tests/fixtures/n1a-529-q25-recall-wait-1117.json.gz
(tests/extract_n1a_529_q25_recall_wait_1117_fixture.py, copies of the captures in
C:/hengband-backups/pdca/captures/n1a-529-death-1117): the process's boards (its ring: decisions
36454-36547) and the battle record.  Each board is decided by a fresh policy restoring the record
through the real path (tests/test_n1b_382_q25_patrol_owner_1113_recorded ``new_policy``) and
answering through the public ``choose_key``.

DECLARED: the record is the one the process left at the death (00:10:51: phase 2 and rallying as
on these boards), its turn set to the decided board's and its ``fire_rest`` (the rest of decision
36530) cleared.  The character is a warrior: no magic-eater lists.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.model import parse_snapshot
from hengbot.policy_constants import REST_MACRO
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-529-q25-recall-wait-1117.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

LOOKOUT = (5, 2)
RECALL_READ = 36515
RESTS = (36516, 36518, 36521, 36526, 36528, 36530)
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def _index(sequence):
    return next(index for index, row in enumerate(CASE["second"]["recorded"])
                if row["sequence"] == sequence)


def decide(sequence, edit=None, answer=None):
    """(key, reason, snapshot) of a fresh policy on the recorded board ``sequence``; ``answer``
    (policy, snapshot) in place of the public ``choose_key``."""
    index = _index(sequence)
    case = dict(CASE, second=dict(boards=CASE["second"]["boards"][index:],
                                  recorded=CASE["second"]["recorded"][index:]))
    record = copy.deepcopy(CASE["battle_record"])
    record["battle"]["fire_rest"] = None   # DECLARED (module note)
    raw = copy.deepcopy(case["second"]["boards"][0])
    if edit is not None:
        edit(raw)
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), {}, record, case)
        snapshot = parse_snapshot(raw, policy._monrace_knowledge)
        key = (policy.choose_key if answer is None else
               (lambda board: answer(policy, board)))(snapshot)
        return key, policy.last_reason, snapshot


class TheRecordingTest(unittest.TestCase):

    def test_recall_read_then_rests_beside_the_pack(self):
        row = CASE["second"]["recorded"][_index(RECALL_READ)]
        self.assertEqual((row["key"], row["reason"]), ("rh", battle.RESTOCK_RECALL_REASON))
        for sequence in RESTS:
            index = _index(sequence)
            board, row = CASE["second"]["boards"][index], CASE["second"]["recorded"][index]
            self.assertEqual((row["key"], row["reason"]), (REST_MACRO, battle.FIRE_REST_REASON))
            self.assertEqual((board["player"]["y"], board["player"]["x"]), LOOKOUT)
            beside = [monster for monster in board["visible_monsters"]
                      if max(abs(monster["y"] - LOOKOUT[0]), abs(monster["x"] - LOOKOUT[1])) <= 1]
            self.assertGreaterEqual(len(beside), 5, sequence)
        record = CASE["battle_record"]["battle"]
        self.assertEqual(record["phase"], battle.phase_index("ipsissimus"))
        last = CASE["second"]["recorded"][-1]
        self.assertEqual(last["turn"] - CASE["second"]["recorded"][_index(RECALL_READ)]["turn"], 125)


class RecallWaitBesideThePackTest(unittest.TestCase):

    def test_each_recorded_rest_is_a_blow_at_one_beside(self):
        for sequence in RESTS:
            key, reason, snapshot = decide(sequence)
            self.assertTrue(snapshot.player.recalling, sequence)
            self.assertEqual(reason, battle.MELEE_REASON, (sequence, key))
            self.assertIn(key, DIRECTIONS, sequence)
            dy, dx = DIRECTIONS[key]
            here = snapshot.player.position
            self.assertTrue(any((monster.position.y, monster.position.x) == (here.y + dy, here.x + dx)
                                for monster in snapshot.visible_monsters if monster.hostile),
                            (sequence, key))

    def test_with_none_beside_the_damaged_wait_still_rests(self):
        # DECLARED CONSTRUCTED control: the recorded rests' boards without the monsters beside
        # [5,2] (the rest of the pack still in view and on the way to the start stair) -- the
        # wait's rest (owner 2026-11-09 「射線の外へ下がって発動を待つ」), unchanged.  The wait itself
        # is asked (``_recall_wait``), as the rung order reaches it on these boards.
        def none_beside(raw):
            raw["visible_monsters"] = [
                monster for monster in raw["visible_monsters"]
                if max(abs(monster["y"] - LOOKOUT[0]), abs(monster["x"] - LOOKOUT[1])) > 1]

        for sequence in RESTS:
            key, reason, snapshot = decide(sequence, none_beside, battle._recall_wait)
            self.assertTrue(snapshot.player.recalling, sequence)
            self.assertEqual((key, reason), (REST_MACRO, battle.FIRE_REST_REASON), sequence)


if __name__ == "__main__":
    unittest.main()
