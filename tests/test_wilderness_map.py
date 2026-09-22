import tempfile
import unittest
from pathlib import Path

from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map

EDIT = Path(r"C:\hengband\lib\edit")


class WildernessMapTest(unittest.TestCase):
    def test_real_map_routes_angband_to_a_town(self):
        path = Path(r"C:\hengband\lib\edit\WildernessDefinition.txt")
        if not path.is_file():
            self.skipTest("real Hengband wilderness definition is unavailable")
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



class WildernessDefinitionFormatTest(unittest.TestCase):
    """P4: the upstream .jsonc and the legacy .txt describe the same map."""

    def test_p4_current_jsonc_equals_txt(self):
        jsonc = EDIT / "WildernessDefinition.jsonc"
        txt = EDIT / "WildernessDefinition.txt"
        if not (jsonc.is_file() and txt.is_file()):
            self.skipTest("both wilderness definition formats are required")
        from_jsonc = load_wilderness_map(jsonc)
        from_txt = load_wilderness_map(txt)
        self.assertEqual((from_jsonc.width, from_jsonc.height), (99, 66))
        self.assertEqual(from_jsonc, from_txt)
        self.assertEqual(from_jsonc.towns, from_txt.towns)

    def test_p4_finder_prefers_jsonc_and_falls_back_to_txt(self):
        jsonc_text = (
            '// comment\n{"width": 3, "height": 3, "maps": {"normal": '
            '{"layout": ["###", "#1#", "###",],}, "compact": {"layout": ["#"]}},}'
        )
        txt_text = "M:WX:3\nW:D:###\nW:D:#1#\nW:D:###\n\nW:D:#\n"
        with tempfile.TemporaryDirectory() as root:
            edit = Path(root) / "lib" / "edit"
            edit.mkdir(parents=True)
            (edit / "WildernessDefinition.txt").write_text(txt_text, encoding="utf-8")
            self.assertEqual(
                find_wilderness_definition(Path(root)), edit / "WildernessDefinition.txt"
            )
            from_txt = load_wilderness_map(edit / "WildernessDefinition.txt")
            (edit / "WildernessDefinition.jsonc").write_text(jsonc_text, encoding="utf-8")
            found = find_wilderness_definition(Path(root))
            self.assertEqual(found, edit / "WildernessDefinition.jsonc")
            self.assertEqual(load_wilderness_map(found), from_txt)
            self.assertEqual(from_txt.rows, ("###", "#1#", "###"))

    def test_jsonc_layout_with_wrong_width_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "WildernessDefinition.jsonc"
            path.write_text(
                '{"width": 4, "maps": {"normal": {"layout": ["###"]}}}', encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                load_wilderness_map(path)


if __name__ == "__main__":
    unittest.main()
