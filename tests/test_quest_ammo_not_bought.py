"""Recorded pins for the Q31 Weapon Smith ammunition miss."""

from __future__ import annotations

from dataclasses import replace
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.ammo_carry import ammo_carry_plan, is_plain_store_ammo
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _parse_items
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import STORE_WEAPON, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = (
    ROOT / "tests/fixtures/"
    "quest-ammo-not-bought-turns-3025481-3026062.jsonl.gz"
)
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")
LIVE = {
    3_025_841: ("\x1b", "shop:observe-and-leave"),
    3_025_849: ("\x1b`n'.", "shop:travel"),
}


class QuestAmmoNotBoughtPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = [json.loads(line) for line in stream]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def policy(self):
        return HengbotPolicy(
            monrace_knowledge=self.monrace,
            dungeon_knowledge=load_dungeon_knowledge(
                EDIT / "DungeonDefinitions.jsonc"
            ),
            quest_knowledge=load_quest_knowledge(EDIT / "quests"),
            quest_strategies=load_quest_strategies(ROOT / "strategy/quests"),
            baseitem_costs=load_baseitem_costs(
                EDIT / "BaseitemDefinitions.jsonc"
            ),
            exploration_ledger_path=Path(self.temp.name) / "exploration.json",
        )

    @classmethod
    def recorded(cls, turn, record_type):
        return next(
            row for row in cls.rows
            if row["turn"] == turn and row["type"] == record_type
        )

    def drive_observed_smith(self, *, carried_plain=86):
        policy = self.policy()
        knowledge = self.recorded(3_025_481, "knowledge")
        self.assertTrue(policy.consume_home_knowledge(tuple(
            _parse_items(knowledge["knowledge"]["items"])
        )))
        inside = parse_snapshot(
            self.recorded(3_025_841, "store"), self.monrace
        )
        outside = parse_snapshot(
            self.recorded(3_025_849, "player_turn"), self.monrace
        )
        if carried_plain != 86:
            inside = replace(inside, inventory=[
                replace(item, count=carried_plain)
                if item.slot == "l" else item
                for item in inside.inventory
            ])
            outside = replace(outside, inventory=[
                replace(item, count=carried_plain)
                if item.slot == "l" else item
                for item in outside.inventory
            ])
        inside_key = policy.choose_key(inside)
        outside_key = policy.choose_key(outside)
        return policy, inside, outside, inside_key, outside_key

    def test_fixture_is_byte_faithful_recorded_window(self):
        with gzip.open(FIXTURE, "rb") as stream:
            frozen = stream.read()
        expected = next(
            line.split(":", 1)[1].strip()
            for line in PROVENANCE.read_text(encoding="utf-8").splitlines()
            if line.startswith("Decompressed sha256:")
        )
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected)
        self.assertEqual(len(self.rows), 25)
        self.assertEqual(
            (self.rows[0]["turn"], self.rows[-1]["turn"]),
            (3_025_481, 3_026_062),
        )

    def test_recorded_selector_values_close_the_ten_bolt_shortfall(self):
        snapshot = parse_snapshot(
            self.recorded(3_025_841, "store"), self.monrace
        )
        policy = self.policy()
        ware = next(item for item in snapshot.store.items if item.letter == "o")
        plain = next(item for item in snapshot.inventory if item.slot == "l")
        power = next(item for item in snapshot.inventory if item.slot == "m")
        launcher = policy._equipped_launcher(snapshot)
        plan = ammo_carry_plan(snapshot, launcher, 99)
        strategy = policy._carry_procurement_strategy(snapshot)
        target = policy._quest_carry_target_for_item(
            snapshot, ware, strategy.required_force
        )
        needs = [
            need.category for need in policy._enumerate_town_needs(snapshot)
            if need.store_type == STORE_WEAPON
        ]
        matches = policy._matching_live_purchase_rungs(snapshot, ware)

        self.assertEqual((plain.count, power.count), (86, 3))
        self.assertEqual(plan.reservations, (("m", 3), ("l", 86)))
        self.assertEqual(target, ("launcher_ammo", 89, 99))
        self.assertEqual(policy._purchase_quantity(snapshot, ware), 10)
        self.assertEqual((ware.price, snapshot.player.gold), (3, 6781))
        self.assertEqual(policy._fundraising_kit_reserve(snapshot), 80)
        self.assertGreaterEqual(snapshot.player.gold - ware.price * 10, 80)
        self.assertTrue(is_plain_store_ammo(ware))
        self.assertEqual((plain.inscription, ware.inscription), ("", ""))
        self.assertTrue(policy._store_item_stacks_with_inventory(plain, ware))
        self.assertEqual([match.rung_id for match in matches], [
            "quest:carry", "tail:ammo",
        ])
        self.assertEqual(needs, ["quest-ranged-kit", "ammo"])

    def test_recorded_public_replay_diverges_to_composed_ten_bolt_buy(self):
        policy, _inside, _outside, inside_key, outside_key = (
            self.drive_observed_smith()
        )

        self.assertEqual(inside_key, LIVE[3_025_841][0])
        self.assertEqual((outside_key, policy.last_reason), (
            "5", "shop:one-shot-buy",
        ))
        self.assertNotEqual(outside_key, LIVE[3_025_849][0])
        self.assertEqual(policy._store_visit.operation_key, "po10\r\r\x1b")
        print(
            "turn=3025849 replay=('5', 'shop:one-shot-buy') "
            f"live={LIVE[3_025_849]!r} operation='po10\\r\\r\\x1b'"
        )

    def test_counterboard_two_stack_total_99_does_not_buy(self):
        policy, _inside, _outside, inside_key, outside_key = (
            self.drive_observed_smith(carried_plain=96)
        )

        self.assertEqual(inside_key, LIVE[3_025_841][0])
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertNotEqual(outside_key, "5")
        self.assertIsNone(
            None if policy._store_visit is None
            else policy._store_visit.operation_key
        )

    def test_q31_remains_blocked_by_free_action_after_ammo_is_satisfied(self):
        policy = self.policy()
        snapshot = parse_snapshot(
            self.recorded(3_025_841, "store"), self.monrace
        )
        satisfied = replace(snapshot, inventory=[
            replace(item, count=96) if item.slot == "l" else item
            for item in snapshot.inventory
        ])

        self.assertFalse(policy._fixed_quest_ready_for_travel(satisfied, 31))
        readiness = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual(
            readiness["carries"]["throwing_items.launcher_ammo"],
            {"measured": 99, "required": 99, "ready": True},
        )
        self.assertEqual(
            readiness["resists"],
            {"ready": False, "required": ["free_action"]},
        )
        self.assertEqual(readiness["failed"], ["resists"])


if __name__ == "__main__":
    unittest.main()
