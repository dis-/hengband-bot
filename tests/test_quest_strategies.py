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
        # pin fails if a generator or fixer flips a profile silently.
        user_approved = {1, 14}  # approved 2026-07-17 (measured-force gates)
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
                    self.assertEqual(info.battlefield.terrain.get(position), "floor")
                    if info.battlefield.chokepoints:
                        self.assertIn(position, info.battlefield.chokepoints)
                roster_ids = {r_idx for r_idx, _ in info.threat_roster}
                self.assertLessEqual(set(data["priority_targets"]), roster_ids)


if __name__ == "__main__":
    unittest.main()
