"""Native travel is never issued while hallucinated (owner decision 2026-11-06).

n1-c life-146 (12:09:11 and 16:53:40, stuck-prompt shop:travel): the bot sent
native travel toward Home; the travel stopped when hallucination began, and
store:entry-interrupted-replan sent the same travel again.  While
hallucinated, grid-selector.cpp tgt_pt_prepare offers only the player's own
grid, so the landmark key finds nothing, '.' on the own grid is ignored and
the point prompt stays open.  Owner: 「幻覚の間は場所指定の移動を使わず歩く。」

The life-146 boards are not available locally.  The pins reuse recorded town
boards that issue native travel: the store route of
tests/fixtures/store-entry-travel-interrupted-20260923.jsonl.gz (decision
1905, the Alchemist) and the life-068 Tower approach of
tests/test_me_tower_trips_recorded.py.  DECLARED CONSTRUCTED: the
hallucination status set on those recorded boards.
"""

import copy
import gzip
import json
import unittest
from pathlib import Path

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from hengbot import me_staff_sequence as sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.town_travel import is_travel_macro
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "store-entry-travel-interrupted-20260923.jsonl.gz"
)
EDIT = Path("C:/hengband/lib/edit")
ALCHEMIST = 4
ALCHEMIST_TRAVEL = "\x1b`n%."
WALK_KEYS = set("12346789")


def _hallucinated(raw):
    board = copy.deepcopy(raw)
    board.setdefault("player", {}).setdefault("status", {})["hallucinated"] = True
    return board


class ShopApproachTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        with gzip.open(FIXTURE, "rb") as stream:
            records = [json.loads(line) for line in stream]
        cls.skill = next(r["board"] for r in records
                         if r["role"] == "skill-knowledge"
                         and r["board"]["turn"] == 4_733_303)
        cls.board = next(r["board"] for r in records
                         if r["role"] == "decision-input"
                         and r["decision"]["decision_sequence"] == 1905)

    def _approach(self, raw):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        policy.consume_skill_knowledge(self.skill)
        policy._decision_sequence = 1905
        step = policy._shopping_approach_step(board, ALCHEMIST)
        self.assertIsNotNone(step)
        return board, policy._shopping_approach_key(board, step, "shop:travel")

    def test_recorded_board_travels(self):
        # Control: the recorded posting board issues the recorded travel.
        _board, key = self._approach(copy.deepcopy(self.board))
        self.assertEqual(key, ALCHEMIST_TRAVEL)

    def test_hallucinated_board_walks(self):
        board, key = self._approach(_hallucinated(self.board))
        self.assertTrue(board.player.hallucinated)
        self.assertFalse(is_travel_macro(str(key)), repr(key))
        self.assertIn(str(key), WALK_KEYS)


class TowerApproachTest(nokey.PostedKey):
    """choose_key on the life-068 Morivant board, keys through the executor."""

    def _policy(self):
        case = loops.CASE["tower"]
        policy = loops.new_policy(case, loops.CASE["inn"]["skill"],
                                  record=case["sequence"])
        raw = case["boards"][0]
        # As in test_me_tower_trips_recorded: Morivant's shelf seen, so the
        # round goes on to the Tower.
        sequence.state(policy).searched_towns.update({0: raw["turn"], 2: raw["turn"]})
        return policy, raw

    def test_hallucinated_tower_approach_walks(self):
        policy, raw = self._policy()
        board = _hallucinated(raw)
        key = loops.decide(policy, board)
        self.assertEqual(policy.last_reason, "me-staff:approach-tower", key)
        self.assertFalse(is_travel_macro(key), key)
        self.assertIn(key, WALK_KEYS)
        self.post(policy, board, key)

    def test_travel_interrupted_by_hallucination_walks_on(self):
        # The life-146 order: travel posted, then the next board (DECLARED
        # CONSTRUCTED: turn + 10, same position) is hallucinated.  Unfixed: the
        # same travel again, whose selector stays open.
        policy, raw = self._policy()
        key = loops.decide(policy, raw)
        self.assertTrue(is_travel_macro(key), key)
        self.post(policy, raw, key)
        policy.confirm_key_posted(key)
        again = _hallucinated(dict(copy.deepcopy(raw), turn=raw["turn"] + 10))
        second = loops.decide(policy, again)
        self.assertEqual(policy.last_reason, "me-staff:approach-tower", second)
        self.assertFalse(is_travel_macro(second), second)
        self.assertIn(second, WALK_KEYS)
        self.post(policy, again, second)


if __name__ == "__main__":
    unittest.main()
