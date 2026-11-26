"""n1-a life-543/544 (2026-11-26): Amberite Rogues stopped after Q34 as quest:blocked:opening-route.

The Q34 -> mining kit -> Q1 route (policy_opening) owned the Outpost after the Q34 reward.  The
CL6 Rogue's Q1 readiness failed only on the force's DPS (12.705 and 13.167 against the Warrior
row's 13.23, which the Rogue reads through class_roles), a requirement no purchase of the route
answers, and the route stopped; every restart re-evaluated it and stopped again (fixtures
tests/fixtures/n1a-543-opening-release-1126-1/2/3,
tests/extract_n1a_543_opening_release_1126_fixtures.py).

Supervisor 2026-11-26 (owner delegation 「自由なキャラクタと戦略で勝利を目指すこと」): an
opening step that cannot be satisfied is passed over and the ordinary flow continues.  The route
releases a character other than the Magic-Eater (policy_opening.OPENING_Q1_RELEASED); Q1 is
taken later in the ordinary fixed-quest order once its readiness is met.

Every board is decided by the public choose_key of the restored arrival policy.
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.policy_opening import (
    OPENING_Q1_RELEASED, OPENING_Q1_RELEASED_REASON, opening_q1_releasable,
)
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
BLOCKED = "quest:blocked:opening-route"
PLAYER_CLASS_ROGUE = 3
# fixture suffix: (the recorded row of the stop, its recorded reason).  The restart of life-543
# saved the game first on the board of its stop (the CLI's save before the stop).
STOP_ROWS = {"1": (44, BLOCKED), "2": (7, "periodic:game-save"), "3": (10, BLOCKED)}


def fixture(suffix: str) -> Path:
    return FIXTURES / f"n1a-543-opening-release-1126-{suffix}"


class RecordedOpeningRelease(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)

    def replay_until_divergence(self, suffix):
        policy, _journal, steps = load(fixture(suffix), Path(self.scratch.name) / suffix)
        for recorded, supply in steps:
            board = supply()
            key = policy.choose_key(board)
            if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
                return policy, recorded, board, key
            if key:
                policy.confirm_key_posted(key)
        self.fail("no decision differs from the recording")

    def test_the_rogue_passes_over_q1_and_the_town_goes_on(self):
        for suffix, (stop_row, stop_reason) in STOP_ROWS.items():
            with self.subTest(capture=suffix):
                policy, recorded, board, key = self.replay_until_divergence(suffix)
                # Every board before the stop is decided as recorded; the stop is not.
                self.assertEqual(recorded["row"], stop_row)
                self.assertEqual(recorded["reason"], stop_reason)
                self.assertEqual(board.player.class_id, PLAYER_CLASS_ROGUE)
                self.assertTrue(board.in_town)
                released = getattr(policy, OPENING_Q1_RELEASED)
                self.assertTrue(released.startswith("readiness:"), released)
                self.assertIn("'failed': ['dps']", released)
                self.assertIsNone(policy._opening_q1_failure)
                self.assertFalse(policy._opening_q1_active(board))
                # The ordinary town answers the board with a real key, and the following
                # decisions of the same board never stop.
                self.assertTrue(key)
                self.assertNotEqual(policy.last_reason, BLOCKED)
                for _ in range(3):
                    if key:
                        policy.confirm_key_posted(key)
                    key = policy.choose_key(board)
                    self.assertNotEqual(policy.last_reason, BLOCKED)
                # Q1 stays in the ordinary order: untaken, not requested below its readiness.
                self.assertFalse(policy._fixed_quest_ready(board, 1))

    def test_a_restored_latched_failure_releases_instead_of_stopping(self):
        # A checkpoint written by the old route holds the latched readiness failure.
        policy, recorded, board, _key = self.replay_until_divergence("2")
        detail = getattr(policy, OPENING_Q1_RELEASED)
        setattr(policy, OPENING_Q1_RELEASED, None)
        policy._opening_q1_failure = detail
        self.assertTrue(policy._opening_q1_active(board))
        self.assertIsNone(policy._opening_q1_town_key(board, []))
        self.assertEqual(getattr(policy, OPENING_Q1_RELEASED), detail)
        self.assertEqual(policy.last_reason, OPENING_Q1_RELEASED_REASON)

    def test_the_magic_eater_keeps_its_designed_stop(self):
        policy, _recorded, board, _key = self.replay_until_divergence("2")
        detail = getattr(policy, OPENING_Q1_RELEASED)
        setattr(policy, OPENING_Q1_RELEASED, None)
        eater = dataclasses.replace(
            board, player=dataclasses.replace(board.player, class_id=PLAYER_CLASS_MAGIC_EATER))
        self.assertEqual(policy._opening_q1_stop(detail, eater), "")
        self.assertEqual(policy.last_reason, BLOCKED)
        self.assertEqual(policy._opening_q1_failure, detail)
        self.assertIsNone(getattr(policy, OPENING_Q1_RELEASED))

    def test_only_requirements_release(self):
        for detail in ("readiness:{}", "stop:stock:quest-healing",
                       "stop:unaffordable-quest-reserve", "competing-quest:2"):
            self.assertTrue(opening_q1_releasable(detail), detail)
        # The route's own mechanical failures stay stops.
        for detail in ("no-progress:quest", "shelf-page-no-progress:1",
                       "supplier-route-unavailable:quest-healing", "not-in-outpost",
                       "quest-request-unavailable", None):
            self.assertFalse(opening_q1_releasable(detail), detail)


if __name__ == "__main__":
    unittest.main()
