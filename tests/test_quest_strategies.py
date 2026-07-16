import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import HengbotPolicy
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
        directory = Path(__file__).parents[1] / "strategy" / "quests"
        profiles = load_quest_strategies(directory)
        self.assertIsNone(HengbotPolicy(quest_strategies=profiles).approved_quest_strategy(1))
        text = (directory / "QUEST_1.jsonc").read_text(encoding="utf-8").replace('"approved": false', '"approved": true')
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_1.jsonc").write_text(text, encoding="utf-8")
            approved = load_quest_strategies(Path(temp))
        self.assertEqual(HengbotPolicy(quest_strategies=approved).approved_quest_strategy(1), approved[1])

    def test_locator_walks_up_from_state_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = root / "strategy" / "quests"
            strategies.mkdir(parents=True)
            state = root / "run" / "state.jsonl"
            state.parent.mkdir()
            with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.cwd", return_value=state.parent):
                self.assertEqual(find_quest_strategies(state), strategies)


if __name__ == "__main__":
    unittest.main()
