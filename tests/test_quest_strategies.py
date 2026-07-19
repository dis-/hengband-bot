import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.policy import HengbotPolicy
from hengbot.policy import FIXED_QUEST_ALLOWLIST
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import find_quest_strategies, load_quest_strategies


class QuestStrategiesTest(unittest.TestCase):
    def test_missing_directory_is_empty(self):
        self.assertEqual(load_quest_strategies(Path("definitely-missing")), {})

    def test_malformed_is_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "QUEST_1.jsonc").write_text("{ bad", encoding="utf-8")
            with patch("sys.stderr") as stderr:
                self.assertEqual(load_quest_strategies(Path(directory)), {})
            self.assertTrue(stderr.write.called)

    def test_example_round_trip_and_approval_gate(self):
        # QUEST_1 ships USER-APPROVED (2026-07-17), so the accessor returns
        # it; flipping the flag back off must hide it again — the gate is the
        # flag, nothing else.
        directory = Path(__file__).parents[1] / "strategy" / "quests"
        profiles = load_quest_strategies(directory)
        self.assertEqual(
            HengbotPolicy(quest_strategies=profiles).approved_quest_strategy(1),
            profiles[1],
        )
        text = (directory / "QUEST_1.jsonc").read_text(encoding="utf-8").replace('"approved": true', '"approved": false')
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_1.jsonc").write_text(text, encoding="utf-8")
            unapproved = load_quest_strategies(Path(temp))
        self.assertIsNone(HengbotPolicy(quest_strategies=unapproved).approved_quest_strategy(1))

    def test_locator_walks_up_from_state_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = root / "strategy" / "quests"
            strategies.mkdir(parents=True)
            state = root / "run" / "state.jsonl"
            state.parent.mkdir()
            with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.cwd", return_value=state.parent):
                self.assertEqual(find_quest_strategies(state), strategies)

    def test_reworked_quest_profiles_pin_approved_and_torch_quantities(self):
        directory = Path(__file__).parents[1] / "strategy" / "quests"
        profiles = load_quest_strategies(directory)
        self.assertTrue(profiles[1].approved)
        self.assertEqual(profiles[1].engagement_plan["hold_position"], [8, 3])
        self.assertIn("西の部屋へ寄らず", profiles[1].engagement_plan["opening"])
        self.assertEqual(profiles[1].required_force["min_hp"], 36)
        self.assertEqual(profiles[1].required_force["min_expected_dps"], 28)
        self.assertEqual(profiles[1].required_force["no_healing_tier"]["min_hp"], 88)
        # Approval state is pinned against strategy/approved.json by
        # test_shipped_drafts_match_real_quest_data — no hardcoded duplicate
        # here (Q34 was user-approved via the Phase 4 pipeline on 2026-07-17).
        self.assertEqual(profiles[34].required_force["throwing_items"]["lit_torch"], 20)
        throwing_points = profiles[34].engagement_plan["throwing_points"]
        self.assertEqual(
            [
                (
                    point["race_id"], point["target"], point["stand"],
                    point["direction"], point["recovery_cells"],
                )
                for point in throwing_points
            ],
            [
                (243, [7, 15], [7, 13], 6,
                 [[7, 14], [7, 15], [7, 16], [7, 17], [7, 18]]),
                (107, [9, 11], [11, 11], 8, [[10, 11], [9, 11]]),
                (107, [11, 9], [9, 9], 2, [[10, 9], [11, 9]]),
            ],
        )
        q2_force = profiles[2].required_force
        self.assertEqual(q2_force["launcher"], {"ammo": "bolt", "equipped": True})
        self.assertEqual(q2_force["throwing_items"], {"bolt": 45})
        self.assertEqual(q2_force["required_scrolls"], {"light": 6, "teleport": 2})
        self.assertEqual(q2_force["utility_tools"], {"wall_breach": 1})

    def test_reward_routing_covers_every_rewarded_allowlisted_quest(self):
        # The reward latch coordinates are a reviewed hard-code; every entry
        # must exist among the town map's parsed reward glyphs, and every
        # allowlisted quest must either have an entry or be a documented
        # no-floor-reward quest (14: direct payment, 28: none). Q34's missing
        # entry silently skipped its reward pickup (user-caught 2026-07-17).
        from hengbot.policy import FIXED_QUEST_REWARD_POSITIONS
        from hengbot.town_maps import find_town_map, parse_town_map

        state = Path(__file__).parents[1] / "jsonlog" / "bot-state-fixed.jsonl"
        maps = {}
        for town_index in (1, 2):
            source = find_town_map(town_index, state)
            if source is None:
                self.skipTest(f"town map {town_index} source is not available")
            maps[town_index - 1] = parse_town_map(source)
        for quest_id, (town_id, positions) in FIXED_QUEST_REWARD_POSITIONS.items():
            with self.subTest(quest_id=quest_id):
                self.assertTrue(positions <= maps[town_id].reward_positions)
        documented_no_reward = {14, 28}
        for quest_id in FIXED_QUEST_ALLOWLIST:
            with self.subTest(quest_id=quest_id):
                self.assertTrue(
                    quest_id in FIXED_QUEST_REWARD_POSITIONS
                    or quest_id in documented_no_reward
                )

    def test_shipped_drafts_match_real_quest_data(self):
        edit = Path(r"C:\hengband\lib\edit")
        definitions = edit / "QuestDefinitionList.txt"
        if not definitions.is_file():
            self.skipTest("real Hengband lib/edit is not available")
        directory = Path(__file__).parents[1] / "strategy" / "quests"
        quests = load_quest_knowledge(definitions)
        required = {
            "quest_id", "name", "approved", "approved_note",
            "engagement_plan", "priority_targets", "consumable_plan",
            "abort_conditions", "required_force", "generated_by", "generated_at",
        }
        paths = sorted(directory.glob("QUEST_*.jsonc"))
        self.assertEqual(
            {int(path.stem.removeprefix("QUEST_")) for path in paths},
            set(FIXED_QUEST_ALLOWLIST),
        )
        # approved:true is a USER decision recorded in approved_note — this
        # pin fails if a generator or fixer flips a profile silently. The
        # authoritative list lives in strategy/approved.json, written only by
        # the Phase 4 approval pipeline (scripts/strategy_approval.mjs).
        approved_file = json.loads(
            (directory.parent / "approved.json").read_text(encoding="utf-8")
        )
        user_approved = set(approved_file["approved"])
        for path in paths:
            with self.subTest(path=path.name):
                data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
                self.assertTrue(required <= data.keys())
                quest_id = int(path.stem.removeprefix("QUEST_"))
                self.assertEqual(data["approved"], quest_id in user_approved)
                if data["approved"]:
                    self.assertTrue(data["approved_note"])
                self.assertEqual(data["quest_id"], quest_id)
                info = quests[quest_id]
                hold = data["engagement_plan"]["hold_position"]
                if info.battlefield is None:
                    self.assertIsNone(hold)
                else:
                    position = tuple(hold)
                    terrain = info.battlefield.terrain.get(position)
                    if data["approved"]:
                        self.assertIn(terrain, {"floor", "shallow_water"})
                    else:
                        self.assertIsNotNone(terrain)
                    if data["approved"] and info.battlefield.chokepoints:
                        self.assertIn(position, info.battlefield.chokepoints)
                roster_ids = {r_idx for r_idx, _ in info.threat_roster}
                self.assertLessEqual(set(data["priority_targets"]), roster_ids)
                force = data["required_force"]
                throwing_items = force.get("throwing_items", {})
                self.assertIsInstance(throwing_items, dict)
                for quantity in throwing_items.values():
                    self.assertIsInstance(quantity, int)
                    self.assertNotIsInstance(quantity, bool)
                    self.assertGreaterEqual(quantity, 0)
                no_healing = force.get("no_healing_tier")
                if no_healing is not None:
                    self.assertGreaterEqual(no_healing["min_hp"], force["min_hp"])


if __name__ == "__main__":
    unittest.main()
