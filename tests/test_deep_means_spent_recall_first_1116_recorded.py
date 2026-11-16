"""50F+ without the *Destruction* means: the Recall before the escape's Speed dose, recorded.

Owner 2026-11-14 (verbatim): 「50F以降で破壊手段なしの探索は許可しない。敵への対処以前に手段が尽きた
時点で帰還させる。」  The above-emergency layer (ladder_above_emergency, destruction_use
``means_spent_recall_key``) reads Word of Recall on such a floor, but the after-ladder filter
policy_combat ``_flee_sustain_key`` took the read's reason ``return:recall`` for the start of an
escape episode and, with a monster faster than the player about (asleep or not), put the
episode's Speed dose in its place (``emergency:quaff-speed:absorbed-power``): an answer to the
enemies before the Recall.  Fixed: the filter leaves the latched means-spent read as it is
(destruction_use ``means_spent_read_selected``), as it leaves the instant escapes; owner
2026-11-16 「回復だけは帰還より先に」: the filter's heal (``emergency:heal``: the two-action
projection takes the HP to the reserve, a tenth of the maximum) alone still comes first.

Recorded: tests/fixtures/n1c-216-deep-recall-1116.pkl.xz (n1-c life-216's first Castle 64F board,
tests/extract_n1c_216_deep_recall_1116_fixture.py): HP 784/784, a sleeping ミッド・タイタン (+10,
game distance 15) and a sleeping 白衣の高位修行僧 (+10, 10), the player +5, 22 charges of the
absorbed *Destruction*.

DECLARED CONSTRUCTED: the absorbed *Destruction*'s charges are emptied (``current`` 0 in the
recorded magic-eater list), so the floor is a means-spent floor; the heal tests also lower the
board's HP (784 recorded) to 300 (the projection 308 crosses the reserve) and 500 (it does not).
The 即死 test (owner 2026-11-16 「即死ならテレポートを先」) lowers the HP to 100 (the line-of-fire
p95 139 reaches it, deep_teleport ``allows``) and takes the Potion of Healing (slot b) out, so the
emergency ladder's own heal-first rule does not answer; its landing board moves the player to
(3, 97) ten game turns later with no monster in view and one Teleportation scroll fewer.  The live life-216 decision logs
(bot-decisions.jsonl..7, 2026-11-16 18:31-20:57) hold no such board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import deep_teleport, destruction_use
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-deep-recall-1116.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))


def restored(empty=True, hp=None, drop=()):
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    board = copy.deepcopy(CASE["board"])
    if hp is not None:
        board["player"]["hp"] = hp
    board["inventory"] = [item for item in board["inventory"] if item.get("slot") not in drop]
    snapshot = parse_snapshot(board, policy._monrace_knowledge)
    if empty:
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        emptied = tuple(dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)
        assert emptied != rows
        policy._me_device_lists = dict(lists, staff=(turn, emptied))
    return policy, snapshot


class MeansSpentRecallFirstTest(unittest.TestCase):

    def test_the_constructed_board(self):
        policy, snapshot = restored(empty=False)
        self.assertEqual(snapshot.dungeon_level, 64)
        self.assertEqual(snapshot.floor_key[2], 0)
        self.assertTrue(destruction_use.holds_means(policy, snapshot))
        policy, snapshot = restored()
        self.assertTrue(destruction_use.means_spent(policy, snapshot))
        hostiles = policy._physical_hostiles(snapshot)
        self.assertTrue(hostiles and all(m.asleep for m in hostiles))
        self.assertTrue(any(m.speed > snapshot.player.speed for m in hostiles))

    def test_recall_is_read_before_the_speed_dose(self):
        policy, snapshot = restored()
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("re", destruction_use.MEANS_SPENT_REASON))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)

    def test_heal_before_the_recall_when_the_projection_crosses_the_reserve(self):
        policy, snapshot = restored(hp=300)
        hostiles = policy._physical_hostiles(snapshot)
        reserve = snapshot.player.max_hp // 10
        self.assertLessEqual(snapshot.player.hp - policy._predicted_damage(snapshot, hostiles, turns=2),
                             reserve)
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "emergency:heal")
        self.assertTrue(key.startswith("q"))
        # The return stays latched: the next board reads the Recall.
        self.assertEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)

    def test_recall_when_the_projection_stays_above_the_reserve(self):
        policy, snapshot = restored(hp=500)
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("re", destruction_use.MEANS_SPENT_REASON))

    def test_another_return_read_is_not_the_means_spent_read(self):
        policy, _ = restored()
        policy.last_reason = destruction_use.MEANS_SPENT_REASON
        policy._returning_to_town = True
        policy._last_return_trigger = "emergency-summoner"
        self.assertFalse(destruction_use.means_spent_read_selected(policy))


class InstantDeathTeleportFirstTest(unittest.TestCase):

    def test_teleport_first_then_recall_after_the_landing(self):
        policy, snapshot = restored(hp=100, drop=("b",))
        self.assertTrue(destruction_use.means_spent(policy, snapshot))
        self.assertGreaterEqual(deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp)
        self.assertTrue(deep_teleport.allows(policy, snapshot))
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "emergency:teleport")
        self.assertTrue(key.startswith("r"))
        self.assertTrue(policy._returning_to_town)
        # CONSTRUCTED landing board.
        board = copy.deepcopy(CASE["board"])
        board["player"]["hp"] = 100
        board["turn"] += 10
        board["player"]["y"], board["player"]["x"] = 3, 97
        board["visible_monsters"] = []
        board["inventory"] = [dict(item) for item in board["inventory"] if item.get("slot") != "b"]
        for item in board["inventory"]:
            if item.get("slot") == "d" and item.get("number"):
                item["number"] -= 1
        landed = parse_snapshot(board, policy._monrace_knowledge)
        self.assertFalse(deep_teleport.allows(policy, landed))
        key = policy.choose_key(landed)
        self.assertEqual((key, policy.last_reason), ("re", destruction_use.MEANS_SPENT_REASON))


if __name__ == "__main__":
    unittest.main()
