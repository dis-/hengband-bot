import tempfile
import unittest
from pathlib import Path

from hengbot.monrace_knowledge import _strip_jsonc, load_monrace_knowledge


class JsoncTest(unittest.TestCase):
    def test_preserves_comment_markers_inside_strings_and_removes_trailing_commas(self):
        source = '''{
          // line comment
          "url": "https://example.invalid/a/*b*/",
          "items": [1, 2,],
          /* block comment */
        }'''
        self.assertEqual(
            __import__("json").loads(_strip_jsonc(source)),
            {"url": "https://example.invalid/a/*b*/", "items": [1, 2]},
        )

    def test_loads_combat_knowledge_by_race_id(self):
        source = '''{
          "monsters": [
            {"id": 10, "hit_point": "10d10", "speed": 5,
             "skill": {"list": ["BLINK", "S_MONSTER",],},},
            {"id": 11, "hit_point": "2d7", "speed": -3,
             "skill": {"list": ["BO_FIRE"],},},
          ],
        }'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "MonraceDefinitions.jsonc"
            path.write_text(source, encoding="utf-8")
            knowledge = load_monrace_knowledge(path)
            self.assertEqual(knowledge[10].max_hp, 100)
            self.assertEqual(knowledge[10].speed, 115)
            self.assertTrue(knowledge[10].can_summon)
            self.assertEqual(knowledge[11].max_hp, 14)
            self.assertEqual(knowledge[11].speed, 107)
            self.assertFalse(knowledge[11].can_summon)


if __name__ == "__main__":
    unittest.main()
