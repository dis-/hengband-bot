"""50F+: the player's own teleport only on 即死 by the monsters with a line of fire (owner 2026-11-14).

Owner 2026-11-14 (verbatim): 「50F以降のテレポートの条件を厳しくする。深い階層のテレポートには
即死抽選があるためである。射線の通っている敵の合計予測被害95%が現在HPを上回るとき=即死のとき
のみ。当てはまらない時は破壊または近寄って破壊を試みる。」  deep_teleport owns it.

Recorded: tests/fixtures/escape-los-1114.jsonl.gz (tests/extract_escape_los_1114_fixture.py),
n1-c life-207, ガラスの城 60F, one fresh policy per case replaying the case's boards through the
public ``choose_key``.  DECLARED CONSTRUCTED: the depth gate walled off, as
tests/test_escape_line_of_fire_1114_recorded; and the absorbed *Destruction* list (6 of 9 charges at
95%) shown before the first board -- the live character held the power and used it on these
floors (16:51:19-16:51:24 emergency:destruction:absorbed-power four times), which the fresh process
has not listed.

* 1651, 7824683 (16:51:24, the live emergency:teleport): ヘル・ワイアーム and others known only by
  detection, the 即死 test's next-action p95 at or over HP 640, none with a line of fire (the sum
  of those with one: 0) -- the walk toward *Destruction* instead of Teleportation.
* 1654, 7836462 (16:54:01, the live emergency:teleport): テレサ beside the player; the sum of the
  monsters with a line of fire, 528, is under HP 542 -- *Destruction* instead.
* 1654, 7836533 (16:54:03, the live emergency:teleport): three ティンダロスの猟犬 and a 黒衣の高位修行僧
  in view, the sum of those with a line of fire, 512, reaches HP 500 -- Teleportation as before.
* 1654, 7836301 (the arrival, 16:53:58): the flee rung's relocation read (flee:scroll on the fresh
  process without the rule) gives way to the walk toward *Destruction*.
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

from hengbot import deep_teleport, instant_death, threat_tiers
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "escape-los-1114.jsonl.gz"
FIXTURE_SHA256 = "bd7a897acf9b3bb2a5f604dcc053cda87023989d3ec762d72f23f2a8e1fdbab3"
EDIT = Path(r"C:\hengband\lib\edit")
DESTRUCTION_LIST = {"kind": "staff", "rows": [{"name": "*破壊*", "current": 6, "max": 9,
                                               "fail": 5, "success": 95}]}


class DeepTeleportRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.cases = {}
        for row in rows:
            cls.cases.setdefault(row["role"], []).append(row["board"])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def decide(self, role, turn):
        """(policy, the board of ``turn``, its reason) after replaying the boards before it."""
        boards = self.cases[role]
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for index, raw in enumerate(boards):
                snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
                if index == 0:
                    observe_lists(policy, replace(snapshot, turn=snapshot.turn - 1,
                                                  magic_eater_power_list=DESTRUCTION_LIST))
                key = policy.choose_key(snapshot)
                if raw["turn"] == turn:
                    return policy, snapshot, policy.last_reason
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(turn)

    def test_sensed_only_instant_death_walks_to_destruction(self):
        policy, snapshot, reason = self.decide("1651", 7824683)
        self.assertEqual(snapshot.dungeon_level, 60)
        self.assertTrue(instant_death.instant_death(policy, snapshot).next_action)
        self.assertFalse([m for m in snapshot.visible_monsters if m.hostile])
        self.assertEqual(deep_teleport.fire_p95(policy, snapshot), 0)
        self.assertFalse(deep_teleport.allows(policy, snapshot))
        self.assertEqual(reason, threat_tiers.APPROACH_REASON)

    def test_a_beside_monster_under_the_hp_is_destroyed(self):
        policy, snapshot, reason = self.decide("1654", 7836462)
        self.assertEqual((deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp), (528, 542))
        self.assertEqual(reason, "emergency:destruction" + deep_teleport.DESTRUCTION_SUFFIX
                         + ":absorbed-power")
        # Asked before the ladder's read is watched (``_issue_emergency_consumable``): no
        # Teleportation read is awaited on the next board.
        self.assertIsNone(policy._emergency_consumable_issue_watch)

    def test_the_fire_sum_over_the_hp_still_teleports(self):
        policy, snapshot, reason = self.decide("1654", 7836533)
        self.assertEqual((deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp), (512, 500))
        self.assertTrue(deep_teleport.allows(policy, snapshot))
        self.assertEqual(reason, "emergency:teleport")

    def test_the_flee_read_gives_way_to_the_walk(self):
        policy, snapshot, reason = self.decide("1654", 7836301)
        self.assertLess(deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp)
        self.assertEqual(reason, threat_tiers.APPROACH_REASON)

    def test_above_50f_the_rule_does_not_apply(self):
        policy, snapshot, _ = self.decide("1654", 7836462)
        shallow = replace(snapshot, floor_key=(snapshot.floor_key[0], 49, 0))
        self.assertTrue(deep_teleport.allows(policy, shallow))
        self.assertIsNone(deep_teleport.substitute(policy, shallow))


if __name__ == "__main__":
    unittest.main()
