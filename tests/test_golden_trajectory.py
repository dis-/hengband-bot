from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position
from hengbot.policy import HengbotPolicy, QUEST_STATUS_TAKEN

import test_policy as fixture
from absorbing_state_catalog import TownWorld
from trajectory_harness import (
    checkpoint_rows,
    decision_window,
    drive_trajectory,
    replay_checkpoint_decision,
    replay_incident,
)


class GoldenOpeningWorld(TownWorld):
    """Small extension of the shared town physics for Q34 acceptance/entry."""

    def __init__(self, snapshot, torch):
        super().__init__(snapshot, entrance=fixture.STORE_GENERAL, stock=[torch])
        self.scan_issued = False
        self.scan_consumed = False
        self.purchase_composed = False
        self.accepted = False
        self.on_quest_floor = False

    def deliver_events(self, policy):
        if self.pending_home_knowledge:
            policy.consume_home_knowledge(())
            self.pending_home_knowledge = False
            self.scan_consumed = True
        super().deliver_events(policy)

    def apply(self, key):
        if key.startswith("~9"):
            self.scan_issued = True
        if "p" in key:
            self.purchase_composed = True
        super().apply(key)
        if not self.accepted and "q" in key and self.position == Position(11, 10):
            self.accepted = True
        if self.accepted and key.startswith(">"):
            self.on_quest_floor = True

    def snapshot(self, decision):
        snap = super().snapshot(decision)
        quest = snap.quests[34]
        grids = dict(snap.grids)
        if self.accepted:
            grids[Position(11, 10)] = replace(
                grids[Position(11, 10)], building_special=-1,
                has_quest_enter=True, quest_id=34,
            )
            quest = replace(quest, status=QUEST_STATUS_TAKEN)
        return replace(
            snap,
            grids=grids,
            quests={34: quest},
            floor_key=(0, 5, 34) if self.on_quest_floor else snap.floor_key,
            town_flag=not self.on_quest_floor,
            store=None if self.on_quest_floor else snap.store,
        )

    def progress_fingerprint(self):
        pack = tuple((item.tval, item.sval, item.count) for item in self.inventory)
        return (self.gold, self.position, self.depth, pack, self.scan_consumed,
                self.accepted, self.on_quest_floor)


class GoldenOpeningTrajectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.ApprovedQuestStrategyExecutionTest.setUpClass()

    def build(self):
        if not hasattr(fixture.ApprovedQuestStrategyExecutionTest, "profiles"):
            fixture.ApprovedQuestStrategyExecutionTest.setUpClass()
        helper = fixture.ApprovedQuestStrategyExecutionTest()
        policy = helper._policy()
        # The real Q34 roster is tiny and stable.  Pin it here so the fresh-birth
        # trajectory never depends on a source checkout or generated data file.
        policy._quest_knowledge[34] = replace(
            policy._quest_knowledge[34],
            placed_monsters=((107, 2), (174, 1), (243, 1)),
        )
        opening = helper._measured_q34_opening()
        weapon = replace(opening.equipment[0], damage_dice_num=6, damage_dice_sides=6)
        supplies = [
            fixture.item("b", fixture.TVAL_POTION, fixture.SV_POTION_SPEED, count=2),
            fixture.item("c", fixture.TVAL_POTION, fixture.SV_POTION_HEALING, count=3),
        ]
        opening = replace(
            opening,
            player=replace(opening.player, hp=100, max_hp=100, main_hand_blows=4,
                           melee_skill=100),
            inventory=supplies,
            equipment=[weapon],
        )
        torch = fixture.store_item(
            "a", fixture.TVAL_LITE, fixture.SV_LITE_TORCH,
            name="torch", count=99, price=1,
        )
        return policy, GoldenOpeningWorld(opening, torch)

    def test_fresh_birth_reaches_q34_strategy_in_order_and_within_bounds(self):
        policy, world = self.build()
        milestones = (
            ("home scan issued", 1, lambda p, w, r, k: w.scan_issued),
            ("home scan consumed", 2, lambda p, w, r, k: w.scan_consumed),
            ("initial purchase composed", 8, lambda p, w, r, k: w.purchase_composed),
            ("q34 approach", 12, lambda p, w, r, k: r.startswith("fixedquest:request")),
            ("acceptance posted", 14, lambda p, w, r, k: w.accepted),
            ("strategy execution engaged", 18,
             lambda p, w, r, k: w.on_quest_floor and 34 in p._quest_navigators),
        )
        result = drive_trajectory(
            policy, world, decisions=30, milestones=milestones,
            owner_bound=8, pair_bound=6,
        )
        self.assertEqual([name for name, _ in result.milestones],
                         [name for name, _bound, _predicate in milestones])
        self.assertEqual(
            sum(reason == "home:request-knowledge-scan"
                for reason, _key in result.transcript),
            1,
        )


class IncidentConverterTest(unittest.TestCase):
    FIXTURES = Path(__file__).parent / "fixtures"

    def test_missing_fixture_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError) as caught:
                replay_incident(HengbotPolicy, Path(directory) / "missing.jsonl",
                                forbidden_pair=("opening-q34:wait", "5"))
        self.assertIn("required frozen incident fixture", str(caught.exception))

    def test_malformed_window_is_not_a_silent_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                list(checkpoint_rows(path))

    def test_today_opening_stall_telemetry_is_pinned(self):
        """Pin the measured incident window; the golden test supplies replay."""
        path = self.FIXTURES / "golden-trajectory-opening-stall.jsonl"
        rows = decision_window(
            path,
            start="2026-08-18T18:14:00", end="2026-08-18T18:20:59",
            reason="opening-q34:wait",
        )
        self.assertGreaterEqual(len(rows), 100)
        measured = rows[0]["fixedquest_readiness"]["strategy_force"]
        self.assertEqual(measured["dps"]["measured"], 0.0)
        self.assertEqual(measured["failed"], ["dps", "speed_potions", "heal_potions"])

    def test_today_decision_110_checkpoint(self):
        row, pair = replay_checkpoint_decision(
            HengbotPolicy,
            self.FIXTURES / "golden-trajectory-decision-110.jsonl.gz", 110,
            forbidden_pair=("opening-q34:wait", "5"),
        )
        self.assertEqual(row["decision_index"], 110)
        self.assertEqual(row["decision_snapshot"]["player_position"], [32, 119])
        self.assertIsNone(row["scan_entry_state"]["_store_entry_wait_owner"])
        self.assertTrue(pair[0].startswith("fixedquest:request"), pair)


if __name__ == "__main__":
    unittest.main()
