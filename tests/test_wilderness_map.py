import unittest
from pathlib import Path

from hengbot.wilderness_map import load_wilderness_map


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


if __name__ == "__main__":
    unittest.main()
