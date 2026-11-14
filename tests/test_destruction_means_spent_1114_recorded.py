"""50F+ without the *Destruction* means: Recall at once, before any enemy is answered (owner 2026-11-14).

Owner 2026-11-14 (verbatim): 「50F以降で破壊手段なしの探索は許可しない。敵への対処以前に手段が尽きた
時点で帰還させる。」  destruction_use.means_spent_recall_key reads Recall on a 50F+ floor without the
means (``holds_means``: a staff or absorbed power at 80%+ with a charge; owner 2026-11-04 「杖と取り込ん
だ力だけ」, a scroll is no means), and ``gap_here`` keeps the floor a gap so the return stays latched.
The departure side was already the rule (policy._missing_required_abilities adds the *Destruction*
label for 50F+ without the means; tests/test_destruction_dive_permission_1104_recorded: no 50F+
destination without it, and the fallback's own choice).

Recorded: tests/fixtures/escape-los-1114.jsonl.gz (tests/extract_escape_los_1114_fixture.py), n1-c
life-207, ガラスの城 60F 16:51:19-16:51:25, one fresh policy replaying the boards through the public
``choose_key``.  DECLARED CONSTRUCTED: the depth gate walled off (as the other 1114 tests), and the
absorbed *Destruction* list shown before the first board -- 1 of 9 charges at 95%; the live character
used the power on 7824621 (emergency:destruction:absorbed-power) -- and on the board after that use
the list shown again with 0 charges (the charge it spent).  On that board (7824627) nothing hostile is
in view and none is awake within the sure radius: the live and the replayed character explored on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import destruction_use
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "escape-los-1114.jsonl.gz"
FIXTURE_SHA256 = "bd7a897acf9b3bb2a5f604dcc053cda87023989d3ec762d72f23f2a8e1fdbab3"
EDIT = Path(r"C:\hengband\lib\edit")
USE, AFTER = 7824621, 7824627


def destruction_list(current):
    return {"kind": "staff", "rows": [{"name": "*破壊*", "current": current, "max": 9,
                                       "fail": 5, "success": 95}]}


class DestructionMeansSpentRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [row["board"] for row in map(json.loads, stream) if row["role"] == "1651"]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def replay(self, *, spent=True):
        """(policy, the board after the use, its reason, the use's reason)."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        used = None
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for index, raw in enumerate(self.boards):
                snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
                if index == 0:
                    observe_lists(policy, replace(snapshot, turn=snapshot.turn - 1,
                                                  magic_eater_power_list=destruction_list(1)))
                if raw["turn"] == AFTER and spent:
                    observe_lists(policy, replace(snapshot, turn=snapshot.turn - 1,
                                                  magic_eater_power_list=destruction_list(0)))
                key = policy.choose_key(snapshot)
                if raw["turn"] == USE:
                    used = policy.last_reason
                if raw["turn"] == AFTER:
                    return policy, snapshot, policy.last_reason, used
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(AFTER)

    def test_the_spent_means_reads_recall_at_once(self):
        policy, snapshot, reason, used = self.replay()
        self.assertEqual(used, "emergency:destruction:absorbed-power")
        self.assertEqual(snapshot.dungeon_level, 60)
        self.assertFalse([m for m in snapshot.visible_monsters if m.hostile])
        self.assertFalse(destruction_use.holds_means(policy, snapshot))
        self.assertEqual(reason, destruction_use.MEANS_SPENT_REASON)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)
        # The floor stays a gap, so the return is the trigger's own on the next boards too.
        self.assertTrue(policy._should_start_town_return(snapshot))
        self.assertEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)

    def test_before_any_enemy_is_answered(self):
        """DECLARED CONSTRUCTED: the arrival board (7824431, 41 hostiles in view; the live
        character used its absorbed *Destruction* there) with the list shown at 0 charges."""
        raw = self.boards[0]
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
        observe_lists(policy, replace(snapshot, turn=snapshot.turn - 1,
                                      magic_eater_power_list=destruction_list(0)))
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            policy.choose_key(snapshot)
        self.assertGreater(len([m for m in snapshot.visible_monsters if m.hostile]), 10)
        self.assertEqual(policy.last_reason, destruction_use.MEANS_SPENT_REASON)
        self.assertEqual(policy._last_return_trigger, destruction_use.MEANS_SPENT_TRIGGER)

    def test_with_a_charge_left_the_floor_is_explored(self):
        policy, snapshot, reason, _ = self.replay(spent=False)
        self.assertTrue(destruction_use.holds_means(policy, snapshot))
        self.assertNotEqual(reason, destruction_use.MEANS_SPENT_REASON)
        self.assertFalse(policy._returning_to_town)


if __name__ == "__main__":
    unittest.main()
