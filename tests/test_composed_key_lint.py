"""composed_key_lint: a direction or target walk appended to a command key outside the input
entry fails unless observed_input lists its composer (review 2026-11-23 K4, (a)-3)."""

import tests  # noqa: F401
import unittest

import composed_key_lint


SUFFIX = ("def shoot(policy, snapshot, item, direction):\n"
          "    return reserved_item_command(policy, snapshot, 'wand', item, suffix=direction)\n")
TARGET = ("def aim(policy, snapshot, ammo):\n"
          "    return reserved_item_command(policy, snapshot, 'fire', ammo, suffix='*t5\\x1b')\n")
APPEND = ("TUNNEL_KEY = 'T'\n"
          "def dig(policy, direction):\n"
          "    return TUNNEL_KEY + direction\n")
WALK = ("def walk(policy, here, there):\n"
        "    return '*p' + policy._cursor_delta_keys(here, there) + 't5\\x1b'\n")


def _findings(modules, suffix=None, append=None):
    return composed_key_lint.findings(modules, suffix or {}, append or {})


class ComposedKeyLintTest(unittest.TestCase):
    def test_the_tree_is_clean(self):
        self.assertEqual(composed_key_lint.main(), 0)

    def test_unlisted_suffix_call_fails_and_listed_passes(self):
        self.assertEqual(len(_findings({"m": SUFFIX})), 1)
        self.assertEqual(_findings({"m": SUFFIX}, {("m", "shoot"): (1, frozenset({"direction"}))}),
                         [])

    def test_a_count_that_differs_or_a_stale_row_fails(self):
        self.assertEqual(len(_findings({"m": SUFFIX},
                                       {("m", "shoot"): (2, frozenset({"direction"}))})), 1)
        self.assertEqual(len(_findings({}, {("m", "gone"): (1, frozenset({"direction"}))})), 1)

    def test_unknown_suffix_kind_fails(self):
        self.assertEqual(len(_findings({"m": SUFFIX}, {("m", "shoot"): (1, frozenset({"move"}))})),
                         1)

    def test_target_literal_needs_a_listed_composer(self):
        unlisted = _findings({"m": TARGET})
        self.assertTrue(any("target-mode literal" in line for line in unlisted))
        self.assertEqual(
            _findings({"m": TARGET}, {("m", "aim"): (1, frozenset({"target-cursor"}))}), [])

    def test_appended_direction_and_target_walk_need_a_row(self):
        self.assertEqual(len(_findings({"m": APPEND})), 1)
        self.assertEqual(_findings({"m": APPEND}, append={("m", "dig"): (1, "passthrough")}), [])
        walk = _findings({"m": WALK})
        self.assertEqual(len(walk), 3)   # the append, '*p' and the 't5\x1b' literal
        self.assertEqual(_findings({"m": WALK}, append={("m", "walk"): (1, "passthrough")}), [])

    def test_the_input_entry_is_exempt(self):
        self.assertEqual(_findings({"observed_input": SUFFIX + APPEND + TARGET}), [])


if __name__ == "__main__":
    unittest.main()
