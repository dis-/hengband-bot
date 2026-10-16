import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map

EDIT = Path(r"C:\hengband\lib\edit")


class WildernessMapTest(unittest.TestCase):
    def test_real_map_routes_angband_to_a_town(self):
        path = EDIT / "WildernessDefinition.jsonc"
        if not EDIT.is_dir():
            self.skipTest("real Hengband lib/edit data is unavailable")
        wilderness = load_wilderness_map(path)
        self.assertEqual((wilderness.width, wilderness.height), (99, 66))

        y, x = 40, 57  # Angband entrance from DungeonDefinitions.jsonc.
        visited = []
        vectors = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        for _ in range(200):
            key = wilderness.next_key_to_town(y, x)
            if key == ">":
                break
            self.assertIn(key, vectors)
            dy, dx = vectors[key]
            y, x = y + dy, x + dx
            visited.append(wilderness.rows[y][x])
        self.assertIn((y, x), wilderness.towns)
        self.assertFalse({"_", "~"}.intersection(visited))

    def test_finder_discovers_only_jsonc_definition(self):
        jsonc_text = (
            '{"width": 3, "height": 3, "maps": '
            '{"normal": {"layout": ["###", "#1#", "###"]}}}'
        )
        txt_text = "M:WX:3\nW:D:###\nW:D:#1#\nW:D:###\n"
        with tempfile.TemporaryDirectory() as root:
            edit = Path(root) / "lib" / "edit"
            edit.mkdir(parents=True)
            (edit / "WildernessDefinition.txt").write_text(txt_text, encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=Path(root)):
                self.assertIsNone(find_wilderness_definition(Path(root)))
            (edit / "WildernessDefinition.jsonc").write_text(jsonc_text, encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=Path(root)):
                found = find_wilderness_definition(Path(root))
            self.assertEqual(found, edit / "WildernessDefinition.jsonc")
            self.assertEqual(load_wilderness_map(found).rows, ("###", "#1#", "###"))

    def test_jsonc_layout_with_wrong_width_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "WildernessDefinition.jsonc"
            path.write_text(
                '{"width": 4, "maps": {"normal": {"layout": ["###"]}}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_wilderness_map(path)

    def test_loader_rejects_legacy_text_path(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "WildernessDefinition.txt"
            path.write_text("W:D:#", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_wilderness_map(path)


if __name__ == "__main__":
    unittest.main()
