"""destruction_scene_lint: no module outside destruction_use reads its private scene readers or
compares a distance against the sure radius (maintainability review 2026-11-17, N1)."""

import tests  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import destruction_scene_lint


class DestructionSceneLintTest(unittest.TestCase):
    def test_the_source_has_no_finding(self):
        self.assertEqual(destruction_scene_lint.findings(), [])

    def test_a_private_read_and_a_radius_comparison_fail(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "new_reader.py").write_text(
                "from hengbot import destruction_use\n"
                "def gates(policy, snapshot):\n"
                "    return destruction_use._clear_headed(snapshot.player)\n"
                "def near(snapshot, monster):\n"
                "    radius = destruction_use.GUARANTEED_RADIUS\n"
                "    return game_distance(snapshot.player.position, monster.position) <= radius\n"
                "def near13(snapshot, monster):\n"
                "    return game_distance(snapshot.player.position, monster.position) <= 13\n"
                "def public(policy, snapshot, monster):\n"
                "    return destruction_use.in_sure_radius(snapshot, monster)\n",
                encoding="utf-8")
            (root / "destruction_use.py").write_text(
                "GUARANTEED_RADIUS = 13\n"
                "def _within(d):\n    return d <= GUARANTEED_RADIUS\n", encoding="utf-8")
            sites = destruction_scene_lint.sites(root)
        self.assertEqual([(module, line) for module, line, _what in sites],
                         [("new_reader", 3), ("new_reader", 6), ("new_reader", 8)])


if __name__ == "__main__":
    unittest.main()
