import json
import tempfile
import unittest
from pathlib import Path

from hengbot.dungeon_knowledge import load_dungeon_knowledge


class DungeonKnowledgeTest(unittest.TestCase):
    def test_loads_static_dungeon_flags(self):
        data = {
            "dungeons": [
                {
                    "id": 4,
                    "name": {"en": "Labyrinth"},
                    "generation": {
                        "minDepth": 10,
                        "maxDepth": 18,
                        "minPlayerLevel": 1,
                    },
                    "final_floor": {"guardian": 1034, "object": 354},
                    "flags": ["MAZE", "SMALLEST", "FORGET"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DungeonDefinitions.jsonc"
            path.write_text(json.dumps(data), encoding="utf-8")
            info = load_dungeon_knowledge(path)[4]

        self.assertEqual(info.flags, frozenset({"MAZE", "SMALLEST", "FORGET"}))
        self.assertEqual(info.guardian_id, 1034)


if __name__ == "__main__":
    unittest.main()
