"""Structural check: every melee-composing site consults _can_fight_in_dungeon.

ROOT-FIX (2026-10-23 Anti-melee cave death): one predicate, every site.  The
census counts the repository's melee-composing sites; a new site must either
consult the predicate or fail here.
"""

import tests  # noqa: F401
import unittest

from melee_site_lint import analyze_repository, melee_sites, unguarded_melee_sites


MELEE_SITE_CENSUS = 20


class MeleeSiteLintTest(unittest.TestCase):
    def test_every_repository_melee_site_consults_the_predicate(self):
        count, findings = analyze_repository()
        self.assertEqual(findings, [])
        self.assertEqual(count, MELEE_SITE_CENSUS)

    def test_unguarded_adjacent_attack_is_reported(self):
        source = (
            "def producer(self, snapshot, adjacent):\n"
            "    if adjacent and not snapshot.player.afraid:\n"
            "        return self._direction_key(snapshot.player.position, self._weakest(adjacent).position)\n"
        )
        self.assertEqual(len(unguarded_melee_sites(source)), 1)

    def test_unguarded_alter_attack_is_reported(self):
        source = (
            "def producer(self, here, cell):\n"
            "    return ALTER_KEY + self._direction_key(here, cell)\n"
        )
        self.assertEqual(len(unguarded_melee_sites(source)), 1)

    def test_enclosing_predicate_guard_passes(self):
        source = (
            "def producer(self, snapshot, adjacent):\n"
            "    if adjacent and self._can_fight_in_dungeon(snapshot.floor_key[0]):\n"
            "        return self._direction_key(snapshot.player.position, adjacent[0].position)\n"
        )
        self.assertEqual(unguarded_melee_sites(source), [])

    def test_earlier_returning_predicate_guard_passes(self):
        source = (
            "def producer(self, snapshot, target):\n"
            "    if not self._can_fight_in_dungeon(snapshot.floor_key[0]):\n"
            "        return None\n"
            "    return self._direction_key(snapshot.player.position, target.position)\n"
        )
        self.assertEqual(unguarded_melee_sites(source), [])

    def test_guard_in_another_function_does_not_count(self):
        source = (
            "def other(self, snapshot):\n"
            "    if not self._can_fight_in_dungeon(snapshot.floor_key[0]):\n"
            "        return None\n"
            "def producer(self, snapshot, target):\n"
            "    return self._direction_key(snapshot.player.position, target.position)\n"
        )
        self.assertEqual(len(unguarded_melee_sites(source)), 1)

    def test_missile_aim_and_plain_steps_are_not_sites(self):
        source = (
            "def producer(self, snapshot, target, cell):\n"
            "    if cell:\n"
            "        return self._direction_key(snapshot.player.position, cell)\n"
            "    return command(suffix=self._direction_key(snapshot.player.position, target.position))\n"
        )
        self.assertEqual(melee_sites(source), 0)


if __name__ == "__main__":
    unittest.main()
