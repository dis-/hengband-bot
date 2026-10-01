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
from hengbot.policy_types import TownErrandPlan

FIXTURE = Path(__file__).parent / "fixtures/live32-shop-leave"


def attachment(enforced):
    with gzip.open(FIXTURE / "state.jsonl.gz", "rt", encoding="utf8") as stream:
        boards = [parse_snapshot(row, {}) for row in map(json.loads, stream)]
    policy = HengbotPolicy()
    policy.prime(boards[2])
    policy.consume_skill_knowledge(json.loads((FIXTURE / "skills.json").read_text(encoding="utf8")))
    policy._town_claim_bar_enforced = enforced
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

    def test_refused_composition_keeps_route_owner_and_real_declaration(self):
        for restored in (False, True):
            policy, boards = attachment(True)
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            step = policy._walkable_neighbors(boards[2], boards[2].player.position)[0]
            self.assertEqual(step, boards[3].player.position)
            key = policy._shopping_approach_key(boards[2], step, "shop:travel")
            self.assertEqual(key, "1")
            self.assertEqual(policy._claim_family_of(policy.last_reason), "store-router")
            policy._record_decision_claim(boards[2], key)
            holder = policy._claim_register.current
            self.assertEqual(holder.owner.value, "store-router")
            self.assertEqual(holder.goal.kind, "Reach")
            self.assertEqual(holder.goal.cell, (45, 84))
            self.assertEqual(holder.execution.next_step, "route.resume")
            self.assertIsNone(policy.decision_claim["violation"])

    def test_historical_gate_stop_shadow_agrees_without_mutation(self):
        policy, boards = attachment(False)
        step = policy._walkable_neighbors(boards[2], boards[2].player.position)[0]
        key = policy._shopping_approach_key(boards[2], step, "shop:travel")
        self.assertEqual((key, policy.last_reason), ("1", "shop:leave"))
        policy._record_decision_claim(boards[2], key)
        self.assertEqual(policy._claim_register.current.goal.source, "store-operation")
        self.assertIsNone(policy._claim_register.current.execution)
        # Recorded final producer result immediately before the 4217 guard.
        # This is a gate attachment, not a fabricated continuation key.
        policy.last_reason = "town:blocked:equipment-calibration-required"
        before = pickle.dumps(policy)
        shadow = policy._s33_shadow_verdict(boards[3], "5")
        self.assertEqual(pickle.dumps(policy), before)
        self.assertEqual(shadow["would_stop"], "ownership:gate-missing:town-plan")
        on = pickle.loads(before)
        on._town_claim_bar_enforced = True
        self.assertIsNone(on._enforce_town_claim_result(boards[3], "5"))
        self.assertEqual(on.last_reason, shadow["would_stop"])


if __name__ == "__main__":
    unittest.main()
