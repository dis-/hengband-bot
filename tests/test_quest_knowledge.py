import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE,
    QUEST_FLAG_PRESET,
    find_quest_definitions,
    load_quest_knowledge,
)


class QuestKnowledgeTest(unittest.TestCase):
    def test_loads_legacy_quest_one_exact_values(self):
        text = "Q:$1:N:Thieves Hideout\nQ:1:N:Japanese name\nQ:$1:Q:6:0:0:0:5:0:0:0:6\nQ:1:Q:6:0:0:0:5:0:0:0:6\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "QuestDefinitionList.txt"
            quests = path.parent / "quests"
            quests.mkdir()
            path.write_text("%:quests/001_ThievesHideout.txt\n", encoding="utf-8")
            (quests / "001_ThievesHideout.txt").write_text(text, encoding="utf-8")
            info = load_quest_knowledge(path)[1]
        self.assertEqual((info.name, info.name_en, info.type, info.level, info.flags), ("Japanese name", "Thieves Hideout", 6, 5, 6))
        self.assertTrue(info.flags & QUEST_FLAG_ONCE)
        self.assertEqual((info.dungeon, info.reward_artifact_id), (0, None))

    def test_loads_migrated_jsonc_to_the_same_shape(self):
        text = '''{
          // Future per-quest format
          "id": 1,
          "name": {"en": "Thieves Hideout", "ja": "Japanese name"},
          "definition": {
            "type": "KILL_ALL", "level": 5, "dungeon": 0,
            "flags": ["ONCE", "PRESET"], "monster": 44,
            "reward": {"artifacts": [42, 43]},
          },
        }'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "001_thieves.jsonc"
            path.write_text(text, encoding="utf-8")
            info = load_quest_knowledge(Path(directory))[1]
        self.assertEqual((info.name, info.name_en, info.type, info.level, info.flags), ("Japanese name", "Thieves Hideout", 6, 5, 6))
        self.assertEqual((info.monrace_id, info.reward_artifact_ids), (44, (42, 43)))

    def test_legacy_short_q_line_defaults_flags_to_zero(self):
        text = "Q:8:N:Quest eight\nQ:8:Q:6:0:0:0:10:0:0:2\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "QuestDefinitionList.txt"
            quests = path.parent / "quests"
            quests.mkdir()
            path.write_text("", encoding="utf-8")
            (quests / "008_Quest.txt").write_text(text, encoding="utf-8")
            info = load_quest_knowledge(path)[8]
        self.assertEqual((info.level, info.dungeon, info.flags), (10, 2, 0))

    def test_legacy_random_quest_file_loads_each_quest_id(self):
        text = (
            "Q:40:N:Quest forty\nQ:40:Q:7:0:0:0:50:0:0:1\n"
            "Q:49:N:Quest forty-nine\nQ:49:Q:7:0:0:0:6:0:0:1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "QuestDefinitionList.txt"
            quests = path.parent / "quests"
            quests.mkdir()
            path.write_text("", encoding="utf-8")
            (quests / "040-049_RandomQuests.txt").write_text(text, encoding="utf-8")
            info = load_quest_knowledge(path)
        self.assertEqual(set(info), {40, 49})
        self.assertEqual((info[40].level, info[49].level), (50, 6))

    def test_real_lib_edit_quest_one_matches_policy_constants(self):
        edit = Path(r"C:\hengband\lib\edit")
        if not (edit / "QuestDefinitionList.txt").is_file():
            self.skipTest("real Hengband lib/edit is not available")
        from hengbot.policy import FIXED_QUEST_LEVEL_MARGIN

        info = load_quest_knowledge(edit / "QuestDefinitionList.txt")[1]
        self.assertEqual(info.name, "\u76d7\u8cca\u306e\u96a0\u308c\u5bb6")
        self.assertEqual((info.type, info.level, info.flags), (6, 5, QUEST_FLAG_PRESET | QUEST_FLAG_ONCE))
        self.assertEqual(info.level + FIXED_QUEST_LEVEL_MARGIN, 8)

    def test_locator_prefers_legacy_then_falls_back_to_jsonc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "run" / "state.jsonl"
            state.parent.mkdir()
            edit = root / "lib" / "edit"
            quests = edit / "quests"
            quests.mkdir(parents=True)
            (quests / "001_test.jsonc").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=state.parent):
                self.assertEqual(find_quest_definitions(state), quests)
                legacy = edit / "QuestDefinitionList.txt"
                legacy.write_text("", encoding="utf-8")
                self.assertEqual(find_quest_definitions(state), legacy)


if __name__ == "__main__":
    unittest.main()
