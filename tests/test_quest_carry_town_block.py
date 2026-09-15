from __future__ import annotations

from dataclasses import replace
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.ammo_carry import ammo_carry_plan
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _parse_items
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import STORE_HOME, STORE_WEAPON, StoreState, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = ROOT / "tests/fixtures/quest-carry-town-block-20260915.jsonl.gz"
ROUND3_FIXTURE = (
    ROOT / "tests/fixtures/quest-carry-town-block-r3-20260915.jsonl.gz"
)


class QuestCarryTownBlockPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.rows = [json.loads(line) for line in stream]
        with gzip.open(ROUND3_FIXTURE, "rt", encoding="utf-8") as stream:
            self.round3_rows = [json.loads(line) for line in stream]

    def policy(self):
        return HengbotPolicy(
            monrace_knowledge=self.monrace,
            dungeon_knowledge=load_dungeon_knowledge(
                EDIT / "DungeonDefinitions.jsonc"
            ),
            quest_knowledge=load_quest_knowledge(EDIT / "quests"),
            quest_strategies=load_quest_strategies(ROOT / "strategy/quests"),
            baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
            exploration_ledger_path=Path(self.temp.name) / "exploration.json",
        )

    def recorded(self, turn, record_type):
        return next(
            row for row in self.rows
            if row["turn"] == turn and row["type"] == record_type
        )

    def round3_recorded(self, turn, record_type):
        return next(
            row for row in self.round3_rows
            if row["turn"] == turn and row["type"] == record_type
        )

    def drive_recorded_exhaustion(self):
        policy = self.policy()
        home = parse_snapshot(self.recorded(2871154, "store"), self.monrace)
        self.assertEqual(str(policy.choose_key(home)), "\x1b")
        knowledge = self.recorded(2871154, "knowledge")
        self.assertTrue(
            policy.consume_home_knowledge(
                tuple(_parse_items(knowledge["knowledge"]["items"]))
            )
        )
        smith = parse_snapshot(self.recorded(2873348, "store"), self.monrace)
        self.assertEqual(smith.store.store_type, STORE_WEAPON)
        self.assertEqual(str(policy.choose_key(smith)), "\x1b")
        outside = parse_snapshot(
            self.recorded(2873354, "player_turn"), self.monrace
        )
        needs = policy._departure_blocking_town_needs(outside)
        return policy, smith, outside, needs

    def test_recorded_home_and_store_exhaustion_waives_only_town_departure(self):
        policy, smith, outside, needs = self.drive_recorded_exhaustion()
        launcher = policy._equipped_launcher(outside)
        self.assertEqual(ammo_carry_plan(outside, launcher, 99).carried_count, 28)
        self.assertIsNone(policy._quest_carry_purchase(smith,
                                                       policy._carry_procurement_strategy(smith)))
        self.assertEqual(needs, [])
        self.assertEqual(
            policy._abandoned_quest_carry_requirements,
            {"throwing_items.launcher_ammo":
             "all-suppliers-visited-without-affordable-stock"},
        )
        self.assertTrue(policy._town_departure_conjuncts(outside)["quest_carry_ready"])
        self.assertNotEqual(policy.last_reason,
                            "town:blocked:no-actionable-claim-owner")

        self.assertFalse(policy._fixed_quest_ready_for_travel(outside, 31))
        readiness = policy.fixed_quest_readiness_state()["strategy_force"]
        strategy = policy.approved_quest_strategy(31)
        self.assertEqual(readiness["carries"]["throwing_items.launcher_ammo"],
                         {"measured": 28, "required": 99, "ready": False})
        self.assertEqual(readiness["resists"],
                         {"ready": False, "required": ["free_action"]})

        # This character's only dungeon-to-town transition in the state log is
        # 2864676 -> 2864686.  Replay those recorded boards at monotonic turns
        # on the same policy; only their historical turn numbers are advanced.
        dungeon = replace(
            parse_snapshot(self.recorded(2864676, "player_turn"), self.monrace),
            turn=outside.turn + 1,
        )
        dungeon_key = policy.choose_key(dungeon)
        self.assertIsNotNone(dungeon_key)
        arrival = replace(
            parse_snapshot(self.recorded(2864686, "player_turn"), self.monrace),
            turn=outside.turn + 2,
        )
        arrival_key = policy.choose_key(arrival)
        self.assertEqual(
            (str(arrival_key), policy.last_reason),
            ("\x1b`n(.", "shop:travel"),
        )
        self.assertEqual(policy._abandoned_quest_carry_requirements, {})
        status = policy._quest_carry_status(
            arrival, strategy.required_force
        )["throwing_items.launcher_ammo"]
        retry = policy._quest_carry_obtainability(
            arrival, strategy, "throwing_items.launcher_ammo", status
        )
        self.assertEqual(retry.stores, (STORE_WEAPON,))
        self.assertTrue(retry.obtainable)
        self.assertEqual(
            policy._town_visit_ledger.store_visits.get(STORE_HOME, 0), 0
        )

    def test_fresh_purchasable_page_keeps_ammo_claim_actionable(self):
        policy = self.policy()
        home = parse_snapshot(self.recorded(2871154, "store"), self.monrace)
        self.assertEqual(str(policy.choose_key(home)), "\x1b")
        knowledge = self.recorded(2871154, "knowledge")
        policy.consume_home_knowledge(
            tuple(_parse_items(knowledge["knowledge"]["items"]))
        )
        raw = self.recorded(2873348, "store")
        smith = parse_snapshot(raw, self.monrace)
        plain = next(item for item in smith.inventory if item.slot == "n")
        shelf = next(item for item in smith.store.items if item.letter == "p")
        purchasable = replace(
            shelf,
            damage_dice_num=plain.damage_dice_num,
            damage_dice_sides=plain.damage_dice_sides,
            known_flags=plain.known_flags,
        )
        smith = replace(smith, store=StoreState(
            store_type=smith.store.store_type,
            items=tuple(purchasable if item is shelf else item
                        for item in smith.store.items),
        ))
        selected = policy._quest_carry_purchase(
            smith, policy._carry_procurement_strategy(smith)
        )
        self.assertIsNotNone(selected)
        self.assertTrue(policy._ammo_purchase_preserves_plan(smith, selected))
        policy.choose_key(smith)
        outside = parse_snapshot(
            self.recorded(2873354, "player_turn"), self.monrace
        )
        needs = policy._departure_blocking_town_needs(outside)
        self.assertNotIn("throwing_items.launcher_ammo",
                         policy._abandoned_quest_carry_requirements)
        self.assertIn(STORE_WEAPON, {need.store_type for need in needs})

    def test_remote_home_scan_exhaustion_abandons_ammo_without_town_stop(self):
        policy = self.policy()
        outside = parse_snapshot(
            self.round3_recorded(2873626, "player_turn"), self.monrace
        )
        self.assertEqual(
            (str(policy.choose_key(outside)), policy.last_reason),
            ("~9\x1b\x1b", "home:request-knowledge-scan"),
        )
        knowledge = self.round3_recorded(2873626, "knowledge")
        self.assertEqual(len(knowledge["knowledge"]["items"]), 63)
        self.assertTrue(policy.consume_home_knowledge(tuple(
            _parse_items(knowledge["knowledge"]["items"])
        )))
        self.assertTrue(policy._home_knowledge_current)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        self.assertIsNone(
            policy._home_ammo_top_up(outside, include_deferred=True)
        )
        self.assertEqual(
            policy._town_visit_ledger.store_visits.get(STORE_HOME, 0), 0
        )

        decisions = []
        for turn in (2873665, 2873722, 2873952):
            store = parse_snapshot(
                self.round3_recorded(turn, "store"), self.monrace
            )
            decisions.append((str(policy.choose_key(store)), policy.last_reason))
        self.assertEqual(decisions, [
            ("\x1b", "shop:observe-and-leave"),
            ("\x1b", "shop:observe-and-leave"),
            ("\x1b", "shop:observe-and-leave"),
        ])

        recorded_stop = parse_snapshot(
            self.round3_recorded(2873956, "player_turn"), self.monrace
        )
        stop_key = policy.choose_key(recorded_stop)
        self.assertEqual(
            policy._abandoned_quest_carry_requirements,
            {"throwing_items.launcher_ammo":
             "all-suppliers-visited-without-affordable-stock"},
        )
        self.assertTrue(
            policy._town_departure_conjuncts(recorded_stop)["quest_carry_ready"]
        )
        self.assertNotEqual(
            policy.last_reason, "town:blocked:departure-unsatisfiable"
        )
        self.assertEqual(
            (str(stop_key), policy.last_reason),
            ("\x1b`n(.", "shop:travel"),
        )
        self.assertFalse(policy._fixed_quest_ready_for_travel(recorded_stop, 31))

    def test_remote_scan_with_matching_plain_ammo_routes_home_first(self):
        policy = self.policy()
        outside = parse_snapshot(
            self.round3_recorded(2873626, "player_turn"), self.monrace
        )
        self.assertEqual(
            (str(policy.choose_key(outside)), policy.last_reason),
            ("~9\x1b\x1b", "home:request-knowledge-scan"),
        )
        knowledge = self.round3_recorded(2873626, "knowledge")
        home_items = list(_parse_items(knowledge["knowledge"]["items"]))
        plain = next(
            item for item in outside.inventory
            if item.slot == ammo_carry_plan(
                outside, policy._equipped_launcher(outside), 99
            ).plain_slot
        )
        home_items.append(replace(plain, slot="z", count=71))
        self.assertTrue(policy.consume_home_knowledge(tuple(home_items)))
        self.assertIsNotNone(
            policy._home_ammo_top_up(outside, include_deferred=True)
        )

        key = policy.choose_key(outside)
        self.assertEqual((str(key), policy.last_reason),
                         ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._abandoned_quest_carry_requirements, {})


if __name__ == "__main__":
    unittest.main()
