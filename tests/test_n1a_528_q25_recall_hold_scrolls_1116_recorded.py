"""Quest 25 on n1-a life-528 (2026-11-16 13:13:13): the recall hold and the forbidden scrolls, recorded.

The board (the last process's decision 44, build bot-0f3b00a68; phase 2, Ipsissimus): HP 282 of
1056, below the plan's HP line (QUEST_25 ``abort_conditions.hp_ratio`` 0.40), no Healing potion,
the ghost tyrannosaurus, a gargoyle and a pattern ghost beside or near the player, and fifteen
Teleportation scrolls in the pack that the plan may not read up to phase 3 (owner 2026-11-12,
quest_no_teleport ``q25_hall_forbids``).  The ONCE floor's hold (once_quest_recall ``held``) read
the scrolls against ``recall_below_teleports`` 5 and kept the emergency Recall back; the character
fought on and died at decision 49.

The rule (owner 2026-11-16, verbatim 「使えない間は巻物を数えない」): while the floor forbids reading
them the scrolls keep no recall held, and the HP line decides as for a plan that reads none; from
the phase they may be read again (after the tome), they count as before.

Recorded: tests/fixtures/n1a-528-q25-death-1116.json.gz
(tests/extract_n1a_528_q25_death_1116_fixture.py).  A fresh policy restores the record through the
real path and decides the board through the public ``choose_key``.  DECLARED: the record is the one
the last process left (13:13:13, phase 2), its turn set to the first board's; the skill knowledge
is the last process's.  The character is a warrior: no magic-eater lists.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import once_quest_recall, quest25_battle as battle, quest_no_teleport
from hengbot.model import SV_SCROLL_TELEPORT, TVAL_SCROLL, parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-528-q25-death-1116.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BOARD = 44   # the last process's decision: HP 282, the Teleport Other rod zapped


def decide(record=None):
    index = next(i for i, row in enumerate(CASE["second"]["recorded"]) if row["sequence"] == BOARD)
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), {}, record, CASE)
        snapshot = parse_snapshot(copy.deepcopy(CASE["second"]["boards"][index]),
                                  policy._monrace_knowledge)
        key = policy.choose_key(snapshot)
        return policy, snapshot, key, policy.last_reason, once_quest_recall.held(policy, snapshot)


class TheRecordingTest(unittest.TestCase):

    def test_below_the_line_with_fifteen_forbidden_scrolls(self):
        policy, snapshot, _key, _reason, _held = decide()
        self.assertEqual(snapshot.player.hp, 282)
        self.assertTrue(quest_no_teleport.q25_hall_forbids(policy, snapshot))
        scrolls = sum(item.count for item in snapshot.inventory
                      if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_TELEPORT)
        self.assertEqual(scrolls, 15)


class HoldTest(unittest.TestCase):

    def test_forbidden_scrolls_keep_no_recall_held(self):
        _policy, _snapshot, key, reason, held = decide()
        self.assertFalse(held)
        self.assertEqual(reason, "emergency:recall-quest-fail")
        self.assertTrue(key.startswith("r"), key)

    def test_control_from_the_phase_after_the_tome_the_scrolls_count(self):
        # DECLARED CONSTRUCTED control: the same board with the battle past the tome (the scrolls
        # may be read again): fifteen scrolls hold the recall as before.
        record = copy.deepcopy(CASE["battle_record"])
        record["battle"]["phase"] = battle.phase_index("corpse-masses")
        policy, snapshot, _key, reason, held = decide(record)
        self.assertFalse(quest_no_teleport.q25_hall_forbids(policy, snapshot))
        self.assertTrue(held)
        self.assertNotEqual(reason, "emergency:recall-quest-fail")


if __name__ == "__main__":
    unittest.main()
