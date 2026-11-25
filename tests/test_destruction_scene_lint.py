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

    def test_the_spared_cells_are_read_through_their_table(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "destruction_use.py").write_text(
                "def _spared_positions(policy, snapshot, target, *, near=None, remembered):\n"
                "    return []\n"
                "def _walk_spared_positions(policy, snapshot, target, *, near=None):\n"
                "    return _spared_positions(policy, snapshot, target, remembered=True)\n"
                "def _use_spared_positions(policy, snapshot, target, *, near=None):\n"
                "    return _spared_positions(policy, snapshot, target, remembered=False)\n"
                "def _spared_in_circle(policy, snapshot, target):\n"
                "    return _use_spared_positions(policy, snapshot, target)\n"
                "def _scene_holds(policy, snapshot):\n"
                "    return _walk_spared_positions(policy, snapshot, None)\n"
                "def emergency(policy, snapshot):\n"
                "    return _spared_positions(policy, snapshot, None, remembered=True)\n",
                encoding="utf-8")
            (root / "threat_tiers.py").write_text(
                "def walk(policy, snapshot):\n"
                "    return destruction_use.spared_positions(policy, snapshot)\n", encoding="utf-8")
            (root / "new_reader.py").write_text(
                "def use(policy, snapshot):\n"
                "    return destruction_use.spared_positions(policy, snapshot)\n", encoding="utf-8")
            sites = destruction_scene_lint.spared_sites(root)
        # The use's scene reading the walk's reader, a direct read of the core, and a module
        # outside the public table; the readers in their rows pass.
        self.assertEqual([(module, line) for module, line, _what in sites],
                         [("destruction_use", 10), ("destruction_use", 12), ("new_reader", 2)])


if __name__ == "__main__":
    unittest.main()
