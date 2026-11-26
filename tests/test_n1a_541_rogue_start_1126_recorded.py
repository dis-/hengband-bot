"""n1-a life-541 (2026-11-26): the first Amberite Rogue stood in town until livelock:exhausted.

The Q34-first opening owned the town of the Lv1 Rogue (DPS 5.58-5.80 against the floor 8,
the three-turn threat 41 against 58 * 0.5), bought the torches and, through the poverty
fundraising, a mining kit down to $1, then toured the shops it could buy nothing in and stopped
as livelock:exhausted three times (fixtures tests/fixtures/n1a-541-rogue-start-1126-1/2/3,
tests/extract_n1a_541_rogue_start_1126_fixtures.py).

Supervisor 2026-11-26 (owner delegation 「自由なキャラクタと戦略で勝利を目指すこと」):

A. QUEST_34 gives the Rogue (class 3) the Magic-Eater's three relaxations: the Rogue reaches
   the quest request instead of the shops.
B. An opening requirement no route of the opening meets (its shops and fundraising spent)
   releases the opening to the ordinary town (quest_opening_readiness.RELEASED).

Every board is decided by the public choose_key of the restored arrival policy.
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_opening_readiness
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name("fixtures")
FILE_STRATEGIES = load_quest_strategies(ROOT / "strategy" / "quests")
REQUEST = "fixedquest:request:approach"
STORE_GENERAL = 0
STORE_MAGIC = 5


def fixture(suffix: str) -> Path:
    return FIXTURES / f"n1a-541-rogue-start-1126-{suffix}"


class RecordedArrival(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)

    def arrival(self, suffix: str, *, file_strategies: bool):
        policy, _journal, steps = load(fixture(suffix), Path(self.scratch.name) / suffix)
        if file_strategies:
            # A new process reads strategy/quests again (cli); the checkpoint holds the old.
            policy._quest_strategies = FILE_STRATEGIES
        return policy, steps

    def replay_until_divergence(self, policy, steps):
        """Decide the recorded boards; (row, board, key) of the first new decision."""
        for recorded, supply in steps:
            board = supply()
            key = policy.choose_key(board)
            if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
                return recorded["row"], board, key
            if key:
                policy.confirm_key_posted(key)
        self.fail("no decision differs from the recording")

    @staticmethod
    def next_reasons(policy, board, key, count=4):
        """The reasons the following decisions give on the same board."""
        reasons = []
        for _ in range(count):
            if key:
                policy.confirm_key_posted(key)
            key = policy.choose_key(board)
            reasons.append(policy.last_reason)
        return reasons


class RogueQ34AcceptanceTest(RecordedArrival):
    """A: the Rogue's Q34 readiness is met; the opening walks to the request."""

    def test_restarted_rogue_walks_to_the_request_not_the_shops(self):
        for suffix in ("2", "3"):
            with self.subTest(capture=suffix):
                policy, steps = self.arrival(suffix, file_strategies=True)
                row, board, key = self.replay_until_divergence(policy, steps)
                # The recorded row 3 approached the General Store for a fourth tour.
                self.assertEqual(row, 3)
                self.assertIs(policy._fixed_quest_readiness["verdict"], True)
                self.assertIn(REQUEST, [policy.last_reason,
                                        *self.next_reasons(policy, board, key)])
                self.assertIsNone(getattr(policy, quest_opening_readiness.RELEASED, None))

    def test_fresh_rogue_leaves_the_mining_kit_and_walks_to_the_request(self):
        policy, steps = self.arrival("1", file_strategies=True)
        row, board, key = self.replay_until_divergence(policy, steps)
        # Rows 0-8 bought the 16 torches; the recorded row 9-10 went on to the $88 Shovel.
        self.assertEqual(row, 9)
        self.assertEqual(board.player.gold, 132)
        self.assertEqual(policy.last_reason, REQUEST)


class OpeningReleaseTest(RecordedArrival):
    """B: with the old QUEST_34 (A reverted) the opening hands the town on."""

    def test_spent_opening_routes_release_the_rogue_where_it_stopped(self):
        policy, steps = self.arrival("2", file_strategies=False)
        for recorded, supply in steps:
            board = supply()
            key = policy.choose_key(board)
            if recorded["row"] == 4:
                # Rations at $4 on the General Store's shelf, $1 in the purse.
                skips = policy.in_store_decision_telemetry()["shelf_evidence_skips"]
                food = [entry for entry in skips
                        if entry["store"] == STORE_GENERAL and entry["category"] == "food"]
                self.assertEqual([entry["cause"] for entry in food], ["unaffordable"])
            if getattr(policy, quest_opening_readiness.RELEASED, None) is not None:
                break
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            policy.confirm_key_posted(key)
        # The opening toured its shops as recorded; at row 11 (the recording saved the game
        # and stopped as livelock:exhausted two decisions later) nothing it can buy is left.
        self.assertEqual(recorded["row"], 11)
        self.assertEqual(getattr(policy, quest_opening_readiness.RELEASED), "strategy-force:dps")
        self.assertFalse(policy._opening_q34_active(board))
        # The ordinary town: its one unvisited stop (the Magic shop's identify staff), with the
        # poverty fundraising's mining trip next.
        self.assertEqual((key, policy.last_reason), ("`n&.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.assertEqual(policy._fundraising_mode, "mine")


if __name__ == "__main__":
    unittest.main()
