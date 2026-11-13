"""Sensed loot no walk reaches, walled in: Stone to Mud melts the way in (sealed_loot).

Owner 2026-11-13 「価値に関係なく溶かす」.  n1-c life-205 (Orc cave 23F, 13:10-13:18): three detected
items lay in small walled rooms whose only side open to the corridor was a row of traps the
walk does not cross; the explore and the secret-door search ran out and the stuck escape read
Recall at 13:18:29 (decision 4529, 'rk').  Asked first on that escape, with nothing seen or
sensed, the melt now walks to the nearest wall of the rooms and melts it, the absorbed power
before the wand, its walls counted against the uses carried.

Recorded: tests/fixtures/sealed-loot-melt-1113.jsonl.gz
(tests/extract_sealed_loot_melt_1113_fixture.py).  Each case replays the last 40 boards in a
fresh policy; on the last, the stuck count stands at its limit as it did live (DECLARED
CONSTRUCTED: the replayed window is shorter than the live count's 60 boards).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
from unittest import mock

from hengbot import retreat_enclosure, sealed_loot
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT
from tests.support import recorded


FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "sealed-loot-melt-1113.jsonl.gz"
FIXTURE_SHA256 = "52d3aaf19c66ccfee1a9af1aaa38f222504644fc2a1adb92df46a13fd1921634"
# The life's ~f skill list (tests/fixtures/n1c-loot-rules-1113.jsonl.gz, ``skill-knowledge``).
SKILL_FIXTURE = FIXTURES / "n1c-loot-rules-1113.jsonl.gz"
# DECLARED CONSTRUCTED: the player beside the wall the route melts ((19,87), upper left room).
BESIDE_THE_WALL = (20, 88)
STONE_TO_MUD = (65, 6)


class SealedLootMelt1113RecordedTest(recorded.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.boards = [row["board"] for row in rows if row["role"] == "board"]
        listed = next(row["list"] for row in rows if row["role"] == "wand-list")
        cls.wand_list = {"wand": (listed[0], tuple(listed[1]))}
        cls.sensed = next(row["monster"] for row in rows if row["role"] == "sensed")
        cls.live = next(row for row in rows if row["role"] == "live")
        with gzip.open(SKILL_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.skill = next(json.loads(line)["board"] for line in stream if '"skill-knowledge"' in line)
        cls.monrace = load_monrace_knowledge(recorded.EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(recorded.EDIT / "BaseitemDefinitions.jsonc")

    def stuck(self, *, absorbed=False):
        """The policy after the window, its stuck count at the limit, and the last board."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy.consume_skill_knowledge(self.skill)
        policy._skill_exp_request_key = lambda snapshot: None
        for raw in self.boards[:-1]:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                policy.confirm_key_posted(key)
        if absorbed:
            policy._me_device_lists = dict(self.wand_list)
        policy._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        policy._move_repeat = 0  # the window's own boards never answered its steps
        raw = copy.deepcopy(self.boards[-1])
        self.assertEqual(raw["turn"], self.live["turn"])
        return policy, raw

    def decide(self, policy, raw):
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
        return key, policy.last_reason

    def test_the_stuck_escape_walks_to_the_rooms_wall_instead_of_reading_recall(self):
        policy, raw = self.stuck()
        self.assertEqual((self.live["reason"], self.live["key"]), ("stuck:recall-escape", "rk"))
        key, reason = self.decide(policy, raw)
        self.assertEqual((key, reason), ("8", sealed_loot.REASON))
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), ["8"])

    def test_the_walk_holds_the_stuck_count_for_the_next_board(self):
        policy, raw = self.stuck()
        key, _reason = self.decide(policy, raw)
        policy.confirm_key_posted(key)
        streak = policy._stuck_escape_streak
        self.assertEqual(self.decide(policy, self.later(raw)), ("8", sealed_loot.REASON))
        self.assertEqual(policy._stuck_escape_streak, streak)

    def test_beside_the_wall_the_absorbed_power_melts_it_first(self):
        policy, raw = self.stuck(absorbed=True)
        raw["player"]["y"], raw["player"]["x"] = BESIDE_THE_WALL
        self.assertEqual(self.decide(policy, raw),
                         ("mBg7", sealed_loot.REASON + ":absorbed-power"))

    def test_without_the_power_the_wand_melts_it(self):
        policy, raw = self.stuck()
        raw["player"]["y"], raw["player"]["x"] = BESIDE_THE_WALL
        key, reason = self.decide(policy, raw)
        self.assertEqual(reason, sealed_loot.REASON)
        wand = next(item for item in raw["inventory"]
                    if (item["tval"], item["sval"]) == STONE_TO_MUD)
        self.assertEqual(key, "a" + wand["slot"] + "7")

    def test_the_absorbed_power_alone_counts_its_uses(self):
        """Declared constructed: the wand taken out, the absorbed power's uses (the life's
        ~f list) alone cover the route's wall."""
        policy, raw = self.stuck(absorbed=True)
        raw["inventory"] = [item for item in raw["inventory"]
                            if (item["tval"], item["sval"]) != STONE_TO_MUD]
        raw["player"]["y"], raw["player"]["x"] = BESIDE_THE_WALL
        self.assertEqual(self.decide(policy, raw),
                         ("mBg7", sealed_loot.REASON + ":absorbed-power"))

    def test_with_no_means_the_escape_reads_recall_as_live(self):
        policy, raw = self.stuck()
        raw["inventory"] = [item for item in raw["inventory"]
                            if (item["tval"], item["sval"]) != STONE_TO_MUD]
        self.assertEqual(self.decide(policy, raw), ("rk", "stuck:recall-escape"))

    def test_more_walls_than_uses_reads_recall(self):
        """Declared constructed: the route made one wall longer than the 44 wand charges."""
        policy, raw = self.stuck()
        route = retreat_enclosure.melt_route

        def longer(*args):
            found = route(*args)
            return None if found is None else (found[0], 45)

        with mock.patch.object(retreat_enclosure, "melt_route", longer):
            self.assertEqual(self.decide(policy, raw), ("rk", "stuck:recall-escape"))

    def test_a_sensed_hostile_keeps_the_escape(self):
        """Declared constructed: the life's sensed スケイヴン added to the board."""
        policy, raw = self.stuck()
        raw["detected_monsters"] = [dict(self.sensed)]
        key, reason = self.decide(policy, raw)
        self.assertNotEqual(reason, sealed_loot.REASON)


if __name__ == "__main__":
    import unittest
    unittest.main()
