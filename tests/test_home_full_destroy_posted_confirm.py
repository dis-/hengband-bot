"""A Home-full destroy is awaited only after its key was actually posted.

Live 2026-10-08 09:00 and 12:29: the relief selected its destroy key while the
player stood on a store entrance; the entrance step-off rewrite replaced the
key, no destroy was sent, yet the relief recorded the destroy as posted and
waited ``home:full-destroy-await-effect`` for minutes until the burst stop.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

import tests  # noqa: F401
from hengbot.model import Position
from tests.test_homefull3_recorded import ConstructedDiscardTest


class DestroyPostedConfirmTest(ConstructedDiscardTest):
    def _to_destroy_key(self):
        p, b, stock, _entries, _key = self.scene(False)
        b, key = self.decide(p, b, messages=(),
                             player=replace(b.player, position=Position(10, 14)),
                             store=self.home_page(stock))
        self.assertEqual(key, "\x1b")
        b, key = self.decide(p, b, store=None)
        self.assertIn("p", key)
        taken = replace(stock[-1], slot="s")
        b = replace(b, turn=b.turn + 1, inventory=(*b.inventory, taken))
        key = p.choose_key(b)
        self.assertEqual(key, "01ks")
        return p, b

    def test_rewritten_destroy_is_not_awaited_and_is_sent_again(self):
        p, b = self._to_destroy_key()
        # The driver posted a different key (the entrance step-off rewrite).
        p.confirm_key_posted("3")
        self.assertNotIn("destroy_posted", p._home_full_relief)
        b = replace(b, turn=b.turn + 1)
        key = p.choose_key(b)
        self.assertEqual(key, "01ks")
        self.assertEqual(p.last_reason, "home:full-destroy-surplus")

    def test_posted_destroy_is_awaited(self):
        p, b = self._to_destroy_key()
        p.confirm_key_posted("01ks")
        self.assertTrue(p._home_full_relief["destroy_posted"])
        b = replace(b, turn=b.turn + 1)
        p.choose_key(b)
        self.assertIn("home:full-destroy-await-effect", p.last_reason)


if __name__ == "__main__":
    unittest.main()
