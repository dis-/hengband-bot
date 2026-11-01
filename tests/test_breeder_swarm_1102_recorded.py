"""breeder-swarm-1102: the recorded n1-c life-098 Software bug swarm (2026-11-02).

n1-c life-098 (Magic-Eater, Lv31, 412 max HP) on 鉄獄24階, random quest 41
(the quest floor's exit is locked), 00:10-00:14: ソフトウェア・バグ (race 246,
4 HP, speed +10, one 1d2 bite, MULTIPLY) grew from 1 to 42.

(a) The breeders were latched as a breakthrough floor (``state 2``), whose
    weakness suppression (``_strategic_subset``: max blow < 5% of max HP) hid
    the bugs biting from every side, and the quest lock leaves the
    breakthrough no exit.  789 decisions beside a bug searched, broke out and
    wandered through 952 bites (HP 412 -> 166, five Potions of Healing).
    Owner rule 「生存処理を優先しなければキャラクタは死亡する。当然の結果。」:
    a weak breeder that strikes from beside the player is fought.

Fixture: tests/fixtures/breeder-swarm-20261102.json.gz
(tests/extract_breeder_swarm_1102_fixture.py).  Every decision is the public
``choose_key``; posted keys go through the production executor port
(test_me_nokey_1031_recorded.PostedKey).
DECLARED RECONSTRUCTED: the capture's policy state holds
``_fixed_quest_speed_attempted`` true (the quest's Potion of Speed was already
drunk); the swarm boards start with the floor latched (their recorded
``search`` / ``breakout:*`` answers are the latch's; the latch itself is not
in the diagnostic policy state).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "breeder-swarm-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SOFTWARE_BUG = 246
QUEST_FLOOR = (1, 24, 41)


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def new_policy(boards):
    policy = loops.new_policy(dict(CASE, boards=boards), CASE["skill"],
                              monraces=CASE["monraces"])
    # DECLARED RECONSTRUCTED (module docstring).
    policy._fixed_quest_speed_attempted = True
    return policy


def board(policy, raw):
    return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)


class PostedSwarmKey(nokey.PostedKey):
    def drive(self, policy, boards):
        return loops.MeStaffLoopsRecordedTest.drive(self, policy, boards)


class BitingSwarmRecordedTest(PostedSwarmKey):
    """(a) beside biting weak breeders on a latched quest floor: melee."""

    def test_recorded_rows_searched_beside_the_biting_bugs(self):
        rows = recorded()
        searched = [raw for raw in CASE["swarm"] if rows[raw["turn"]][0] == "search"]
        self.assertEqual(len(searched), 8)
        policy = new_policy(CASE["swarm"])
        for raw in searched:
            snapshot = board(policy, raw)
            self.assertEqual(snapshot.floor_key, QUEST_FLOOR)
            adjacent = [m for m in snapshot.visible_monsters
                        if m.race_id == SOFTWARE_BUG and m.distance <= 1]
            self.assertGreaterEqual(len(adjacent), 6, raw["turn"])
            self.assertTrue(policy._is_weak_breeder(snapshot, adjacent[0]))
        self.assertTrue(any("ソフトウェア・バグに噛まれた。" in message
                            for raw in searched for message in raw["messages"]))

    def test_latched_quest_floor_melees_the_biting_bugs(self):
        boards = CASE["swarm"][1:]
        policy = new_policy(boards)
        policy._breeder_breakthrough_floor = QUEST_FLOOR
        rows = self.drive(policy, boards)
        for raw, key, reason in rows:
            self.assertEqual(reason, "melee", (raw["turn"], key))
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)


if __name__ == "__main__":
    unittest.main()
