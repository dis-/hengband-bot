"""junk_destroy_now.safe over SafetyFacts: each fact it asks about still refuses alone."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from types import SimpleNamespace
import unittest

from hengbot import junk_destroy_now, safety_facts


def board(*, in_town=False, store=None, monsters=(), **status):
    player = dict(blind=False, confused=False, stunned=False, paralyzed=False, hallucinated=False)
    player.update(status)
    return SimpleNamespace(in_town=in_town, store=store, visible_monsters=monsters,
                           player=SimpleNamespace(**player))


def policy(*, owner=None, **attributes):
    return SimpleNamespace(_escape_state=SimpleNamespace(owner=owner), **attributes)


class SafeOverFactsTest(unittest.TestCase):
    def test_a_quiet_board_is_safe(self):
        self.assertTrue(junk_destroy_now.safe(policy(), board()))
        self.assertTrue(junk_destroy_now.safe(policy(owner="return"), board()))
        self.assertTrue(junk_destroy_now.safe(
            policy(), board(monsters=(SimpleNamespace(hostile=False),))))

    def test_each_fact_refuses_alone(self):
        for name, asked_policy, asked_board in (
            ("in_town", policy(), board(in_town=True)),
            ("in_store", policy(), board(store=object())),
            ("hostile_in_view", policy(), board(monsters=(SimpleNamespace(hostile=True),))),
            ("took_damage", policy(_took_damage=True), board()),
            ("blind", policy(), board(blind=True)),
            ("confused", policy(), board(confused=True)),
            ("stunned", policy(), board(stunned=True)),
            ("paralyzed", policy(), board(paralyzed=True)),
            ("hallucinated", policy(), board(hallucinated=True)),
            ("escape_owner", policy(owner="flee"), board()),
        ):
            with self.subTest(fact=name):
                self.assertTrue(getattr(safety_facts.of(asked_policy, asked_board), name))
                self.assertFalse(junk_destroy_now.safe(asked_policy, asked_board))


if __name__ == '__main__':
    unittest.main()
