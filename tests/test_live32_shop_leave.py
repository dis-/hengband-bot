"""Recorded outside shelf refusal must not manufacture a shop operation."""
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan, TownNeed

FIXTURE = Path(__file__).parent / "fixtures/live32-shop-leave"


def attachment(enforced):
    with gzip.open(FIXTURE / "state.jsonl.gz", "rt", encoding="utf8") as stream:
        boards = [parse_snapshot(row, {}) for row in map(json.loads, stream)]
    policy = HengbotPolicy()
    policy.prime(boards[2])
    policy.consume_skill_knowledge(json.loads((FIXTURE / "skills.json").read_text(encoding="utf8")))
    policy._decision_sequence = 4216
    # Recorded attachment: the shelf was observed then ESC was posted at 4215;
    # 4216 is its actual outside entrance board, not a synthesized store page.
    policy._home_knowledge_current = True
    policy._last_snapshot_was_store = True
    policy._shop_observation = (boards[1].store, 4215)
    policy._town_errand_plan = TownErrandPlan(
        [7, 6, 4], need_categories={7: ("equipment-catalog", "equipment-work"),
                                  6: ("quest-speed", "black-market"),
                                  4: ("launcher-enchant",)},
        requester_families={7: ("equipment-txn",), 6: ("shop-buy",), 4: ("curse-enchant",)})
    policy._shopping_approach_goal = boards[2].player.position
    policy._shopping_approach_store_type = 6
    policy.last_reason = "shop:approach"
    return policy, boards


class Live32ShopLeaveTest(unittest.TestCase):
    def test_cached_registry_callbacks_follow_the_restored_policy(self):
        for restored in (False, True):
            policy, boards = attachment(False)
            specs = policy._town_need_registry()
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            board = boards[2]
            policy._town_need_evaluation_snapshot = board
            policy._town_need_evaluation_candidates = [
                TownNeed(7, "equipment-work", "home-first"),
            ]
            spec = next(entry for entry in policy._town_need_registry()
                        if entry.category == "equipment-work")
            self.assertEqual(spec.produces(board), True)
            self.assertEqual(spec.resolve_store_type(board), 7)
            self.assertEqual(spec.satisfied(board), False)
            policy._town_need_evaluation_candidates = []
            self.assertEqual(spec.produces(board), False)
            self.assertEqual(spec.satisfied(board), True)

    def test_frozen_evidence(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf8"))
        for name, digest in provenance["fixture_sha256"].items():
            data = (FIXTURE / name).read_bytes()
            if name.endswith(".json"):
                data = data.replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        with gzip.open(FIXTURE / "decisions.jsonl.gz", "rt", encoding="utf8") as stream:
            rows = list(map(json.loads, stream))
        self.assertEqual([(row["decision_sequence"], row["key"], row["reason"]) for row in rows],
                         [(4215, "\x1b", "shop:observe-and-leave"),
                          (4216, "1", "shop:leave"),
                          (4217, None, "ownership:gate-missing:town-plan")])
        self.assertEqual(rows[1]["claim"]["goal"]["source"], "store-operation")
        self.assertIsNone(rows[1]["claim"]["execution"])

            # 9 is the first changed key (recorded 4217 stopped). No following
            # historical board is treated as a consequence of this new action.


if __name__ == "__main__":
    unittest.main()
