"""Recorded pins for the 2026-09-16 fixed-quest ammunition stockout."""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _parse_items
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import STORE_HOME, STORE_WEAPON, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
FIXTURE = ROOT / "tests/fixtures/quest-carry-departure-20260916.jsonl.gz"
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")
LIVE_BLOCKED_DECISION = ("1", "town:blocked:departure-unsatisfiable")
SUPPLIER_ROWS = (45, 53, 64, 68, 86, 104, 122, 126, 130, 148)
KNOWLEDGE_ROWS = (79, 141)


def recorded_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class QuestCarryDepartureRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def policy(self) -> HengbotPolicy:
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

    def test_fixture_is_the_byte_faithful_recorded_window(self):
        with gzip.open(FIXTURE, "rb") as stream:
            frozen = stream.read()
        provenance = PROVENANCE.read_text(encoding="utf-8")
        expected_hash = next(
            line.split(":", 1)[1].strip()
            for line in provenance.splitlines()
            if line.startswith("Decompressed sha256:")
        )
        rows = recorded_rows()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected_hash)
        self.assertEqual(len(rows), 150)
        self.assertEqual(
            (rows[0]["turn"], rows[-1]["turn"]),
            (3_038_685, 3_043_494),
        )

    def drive_recorded_stockout(self):
        rows = recorded_rows()
        policy = self.policy()
        decisions = []
        for index in sorted((*SUPPLIER_ROWS, *KNOWLEDGE_ROWS)):
            row = rows[index]
            if row["type"] == "knowledge":
                self.assertTrue(policy.consume_home_knowledge(tuple(
                    _parse_items(row["knowledge"]["items"])
                )))
                continue
            snapshot = parse_snapshot(row, self.monrace)
            decisions.append((snapshot.turn, policy.choose_key(snapshot), policy.last_reason))
        return policy, rows, decisions

    def test_recorded_stockout_releases_ordinary_departure_at_blocked_board(self):
        policy, rows, decisions = self.drive_recorded_stockout()
        final = parse_snapshot(rows[-1], self.monrace)

        # The capture starts after unrelated calibration/equipment state was
        # created.  Wall those owners only after the real store/Home observers
        # above have produced the ammunition stockout on this policy instance.
        with (
            patch.object(policy, "_home_available", return_value=False),
            patch.object(policy, "_equipment_departure_ready", return_value=True),
            patch.object(policy, "_town_claims_active", return_value=False),
        ):
            dump_key = policy.choose_key(final)
            decisions.append((final.turn, dump_key, policy.last_reason))
            key = policy.choose_key(final)
            replay = (str(key), policy.last_reason)
            values = policy._town_departure_conjuncts(final)

        print(f"replay={replay!r} live={LIVE_BLOCKED_DECISION!r}")
        self.assertEqual(replay, ("rca", "town:recall-to-angband"))
        self.assertEqual(LIVE_BLOCKED_DECISION, (
            "1", "town:blocked:departure-unsatisfiable",
        ))
        self.assertTrue(values["quest_carry_ready"])
        self.assertTrue(all(values.values()))
        self.assertNotIn(
            "town:blocked:departure-unsatisfiable",
            [reason for _turn, _key, reason in decisions] + [replay[1]],
        )
        self.assertEqual(policy.procurement_requirements(final), [{
            "item": "Quest launcher ammunition",
            "current": 95,
            "target": 99,
            "missing": 4,
        }])

    def test_satisfiable_shortfall_still_routes_to_weapon_smith(self):
        policy = self.policy()
        rows = recorded_rows()
        final = parse_snapshot(rows[-1], self.monrace)
        stocked = parse_snapshot(rows[52], self.monrace)
        purchase = policy._quest_carry_purchase(
            replace(stocked, inventory=final.inventory),
            policy._carry_procurement_strategy(final),
        )
        self.assertIsNotNone(purchase)
        self.assertEqual((stocked.store.store_type, purchase.count), (
            STORE_WEAPON, 95,
        ))

        key = policy.choose_key(final)
        self.assertEqual((str(key), policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertIn("quest-ranged-kit", policy._town_claim_categories)

    def test_fixed_quest_entry_refuses_recorded_ninety_five_bolts(self):
        policy = self.policy()
        final = parse_snapshot(recorded_rows()[-1], self.monrace)

        self.assertFalse(policy._fixed_quest_ready_for_travel(final, 31))
        readiness = policy.fixed_quest_readiness_state()
        self.assertEqual((readiness["verdict"], readiness["reason"]), (
            False, "strategy-force",
        ))
        self.assertEqual(
            readiness["strategy_force"]["carries"][
                "throwing_items.launcher_ammo"
            ],
            {"measured": 95, "required": 99, "ready": False},
        )


if __name__ == "__main__":
    unittest.main()
