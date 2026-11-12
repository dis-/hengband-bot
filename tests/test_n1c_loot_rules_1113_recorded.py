"""The owner's 2026-11-13 answers on n1-c's left loot and early returns, pinned on its boards.

Recorded: tests/fixtures/n1c-loot-rules-1113.jsonl.gz (tests/extract_n1c_loot_rules_1113_fixture.py).
Each case restarts a policy on the case's boards (a fresh process: its floor memory is what
those boards showed it).

1. 「遠い品は拾ってよい」 (summoner_far_loot): life-200 Angband 49F, the remembered summoners'
   block held seven items 4-9 cells away with nothing in sight (live: explore, then Recall).
2. 「射線にT1が入っていない=感知しただけはカウントしない」 (threat_tiers.counts_as_escape):
   life-205 Angband 46F, two sensed-T1 teleports at full HP with nothing in sight made the two
   escapes that read Recall (21:35:57 and 21:37:22).
3. 「価値の低い品を捨てて拾う」 (full_pack_exchange): life-205 Angband 62F quest 46, 23 of 23
   slots and every floor item blocked as pack-full for 449 boards.
4. 「その品の方へ探索を寄せる。また、経路が見つからない時に周辺感知を使う」 (loot_frontier, me_powers
   ``loot-unreachable``): life-205 Angband 30F, two items with no known route for a minute and a
   half while the explore went elsewhere; after STEER_AFTER_BOARDS boards of it the explore's new
   goal is the frontier nearest them.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from hengbot import full_pack_exchange, loot_frontier, me_powers, summoner_far_loot, threat_tiers
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-loot-rules-1113.jsonl.gz"
FIXTURE_SHA256 = "91edbe7c87d62be4976a60a09bcb69d8c203e7f995ff38393a2ce8d6fdc8f72e"
EDIT = Path(r"C:\hengband\lib\edit")


class N1cLootRules1113RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.cases = {}
        for row in rows:
            if "board" in row and row["role"] != "skill-knowledge":
                cls.cases.setdefault(row["role"], []).append(row["board"])
        cls.skill = next(row["board"] for row in rows if row["role"] == "skill-knowledge")
        cls.lists = next(row["lists"] for row in rows if row["role"] == "me-lists")
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def policy(self):
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy.consume_skill_knowledge(self.skill)
        # The windows are short of the process's own ~f cycle (the skill list above).
        policy._skill_exp_request_key = lambda snapshot: None
        return policy

    def replay(self, policy, boards):
        for raw in boards:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                policy.confirm_key_posted(key)

    def test_far_items_are_taken_with_only_a_remembered_summoner(self):
        boards = self.cases["summoner"]
        policy = self.policy()
        self.replay(policy, boards[:-1])
        snapshot = parse_snapshot(copy.deepcopy(boards[-1]), self.monrace)
        self.assertEqual(snapshot.turn, 3143260)
        self.assertFalse([m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                          if m.hostile])
        remembered = summoner_far_loot.remembered_summoners(policy, snapshot)
        self.assertTrue(remembered)
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "seek-loot")
        target = policy._loot_target
        self.assertGreaterEqual(min(game_distance(target, m.position) for m in remembered),
                                summoner_far_loot.FAR_LOOT_DISTANCE)
        # The items near a remembered summoner stay blocked.
        for position in policy._loot_candidates(snapshot):
            self.assertFalse(summoner_far_loot.near(policy, snapshot, position))

    def test_a_sensed_t1_out_of_the_line_of_fire_is_no_escape(self):
        boards = self.cases["sensed"]
        policy = self.policy()
        self.replay(policy, boards[:47])
        snapshot = parse_snapshot(copy.deepcopy(boards[47]), self.monrace)
        self.assertEqual(snapshot.turn, 1880831)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        self.assertEqual(policy.last_reason, "sensed-t1:teleport")
        self.assertEqual(snapshot.player.hp, snapshot.player.max_hp)
        self.assertFalse(getattr(policy, threat_tiers.IN_LINE_OF_FIRE))
        self.replay(policy, boards[48:49])
        self.assertEqual(policy._dive_emergencies, 0)

    def full_pack(self, here=None):
        raw = copy.deepcopy(self.cases["full-pack"][0])
        if here is not None:
            raw["player"]["y"], raw["player"]["x"] = here.y, here.x
        policy = self.policy()
        policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
        snapshot = parse_snapshot(raw, self.monrace)
        self.assertEqual(len(snapshot.inventory), 23)
        return policy, snapshot

    def test_a_full_pack_walks_to_the_dearer_floor_item(self):
        policy, snapshot = self.full_pack()
        spare = full_pack_exchange.spare(policy, snapshot)
        self.assertEqual((spare.tval, spare.sval, spare.count), (18, 3, 9))  # the second bolt stack
        self.assertEqual(full_pack_exchange.pile_value(policy, snapshot, Position(37, 36)), 1020)
        key = policy._normal_loot_key(snapshot, policy._strategic_hostiles(snapshot))
        self.assertEqual((key, policy.last_reason), ("9", full_pack_exchange.SEEK_REASON))

    def test_on_the_pile_the_spare_is_destroyed(self):
        """Declared constructed: the same board with the player moved onto the pile."""
        policy, snapshot = self.full_pack(Position(37, 36))
        key = policy._normal_loot_key(snapshot, policy._strategic_hostiles(snapshot))
        self.assertEqual(policy.last_reason, full_pack_exchange.DESTROY_REASON)
        self.assertIsNotNone(key)

    def steered(self):
        """The 30F window replayed; the last board is the explore's new plan (turn 1764727)."""
        boards = self.cases["unreachable"]
        policy = self.policy()
        self.replay(policy, boards[:-1])
        snapshot = parse_snapshot(copy.deepcopy(boards[-1]), self.monrace)
        self.assertEqual(snapshot.turn, 1764727)
        return policy, snapshot

    def test_unreachable_loot_steers_the_explore_to_its_frontier(self):
        """Live and main: the explore's next goal east of (5,176), away from the items."""
        policy, snapshot = self.steered()
        self.assertEqual({(p.y, p.x) for p in policy._known_loot} & {(16, 147), (19, 136)},
                         {(16, 147), (19, 136)})
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("1", "explore"))
        self.assertEqual(policy._explore_goal_identity.position, Position(5, 162))

    def test_unreachable_loot_asks_the_absorbed_mapping(self):
        policy, snapshot = self.steered()
        mapping = next(power for power in me_powers.POWERS
                       if power.effect == me_powers.MAP_AREA and power.kind == "staff")
        self.assertIn("loot-unreachable", mapping.triggers)
        memory = me_powers.FloorMemory(snapshot.floor_key, snapshot.turn)
        ctx = me_powers.Context(policy, snapshot, me_powers.FLOOR, memory)
        self.assertTrue(me_powers.TRIGGERS["loot-unreachable"].due(ctx, mapping))


if __name__ == "__main__":
    unittest.main()
