import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE,
    find_quest_definitions,
    load_quest_knowledge,
)


class QuestKnowledgeTest(unittest.TestCase):
    def test_loads_legacy_quest_one_exact_values(self):
        text = "Q:1:N:Thieves Hideout\nQ:1:Q:6:0:0:0:5:0:42:6\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "QuestDefinitionList.txt"
            path.write_text(text, encoding="utf-8")
            info = load_quest_knowledge(path)[1]
        self.assertEqual((info.name, info.type, info.level, info.flags), ("Thieves Hideout", 6, 5, 6))
        self.assertTrue(info.flags & QUEST_FLAG_ONCE)
        self.assertEqual(info.baseitem_id, 42)

    def test_loads_migrated_jsonc_to_the_same_shape(self):
        text = '''{
          // Future per-quest format
          "id": 1,
          "name": {"en": "Thieves Hideout", "ja": "盗賊の隠れ家"},
          "definition": {
            "type": 6, "level": 5, "dungeon": 0,
            "flags": ["ONCE", "PRESET"], "monraceId": 0,
            "baseitemId": 42,
          },
        }'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "001_thieves.jsonc"
            path.write_text(text, encoding="utf-8")
            info = load_quest_knowledge(Path(directory))[1]
        self.assertEqual((info.name, info.type, info.level, info.flags), ("Thieves Hideout", 6, 5, 6))
        self.assertEqual(info.baseitem_id, 42)

    def test_locator_prefers_legacy_then_falls_back_to_jsonc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "run" / "state.jsonl"
            state.parent.mkdir()
            edit = root / "lib" / "edit"
            quests = edit / "quests"
            quests.mkdir(parents=True)
            jsonc = quests / "001_test.jsonc"
            jsonc.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=state.parent):
                self.assertEqual(find_quest_definitions(state), quests)
                legacy = edit / "QuestDefinitionList.txt"
                legacy.write_text("", encoding="utf-8")
                self.assertEqual(find_quest_definitions(state), legacy)


if __name__ == "__main__":
    unittest.main()
