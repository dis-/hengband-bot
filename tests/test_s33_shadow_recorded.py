"""Shadow/ON agreement at recorded seams, never replaying long lifetimes.

The six fixture pins attach only to the first decision's input boundary
(the stuck fixture's declared closing window), using captured attach skills.
They are isolated attachments, not claims about an action-consistent tour.
Live8/9/10/11 reuse the preconditions of their existing focused pins.
"""
import gzip
import json
from pathlib import Path
import unittest
from dataclasses import replace

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.model import parse_snapshot, StoreState
from hengbot.policy import HengbotPolicy
from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from recorded_loadout import recorded_loadout_replay
from recorded_loot_observation import pre_fix_loot_observation
import test_s33_shadow as shadow_tests
import test_live8 as live8
import test_live10 as live10
import test_live11 as live11


FIXTURES = Path(__file__).parent / "fixtures"


class RecordedShadowTest(unittest.TestCase):
    compare = shadow_tests.ShadowVerdictTest.compare



    def test_live8_one_shot_identity(self):
        rows = live8.recorded_rows()
        with gzip.open(str(live8.LOG) + ".state.jsonl.gz", "rt", encoding="utf8") as f:
            raw = next(r for r in map(json.loads, f) if r.get("turn") == rows[211]["turn"]
                       and not r.get("inventory") and not r.get("store"))
        board = parse_snapshot(raw, {})
        policy = HengbotPolicy()
        policy.last_reason = "shop:one-shot-in-flight"
        self.compare(policy, board, "", "ownership:declaration-stale:shop-buy")

    def test_live10_restore_observation_and_stale_item(self):
        first, second, _ = live10.boards()
        policy = HengbotPolicy()
        policy._normal_sub_hand_is_optimal = True
        claim = policy._claim_register.declare("equipment-txn", observe(
            ("transaction",), 10, "transaction"))
        key = policy._town_restore_weapon_key(first)
        self.assertEqual(key, "wga")
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        policy._claim_register.declare_execution(
            claim.claim_id, producer="equipment-txn", work_id=declaration.work_id,
            state="awaiting", arguments=declaration.arguments,
            operation_ref="decision:435:" + key,
            expected_effect=declaration.expected_effect,
            continuation=declaration.continuation)
        self.compare(policy, second, None, None, holder_dispatch=True)
        changed = replace(second, equipment=[
            replace(second.equipment[0], name="different sword"), *second.equipment[1:]])
        self.compare(policy, changed, None, "ownership:declaration-stale:equipment-txn",
                     holder_dispatch=True)

    def test_live11_bound_shop_operation_and_changed_store(self):
        rows, outside, shelf, inside = live11.capture()
        policy = HengbotPolicy()
        policy._decision_sequence = 920
        policy._shop_observation = (shelf.store, 919)
        policy._home_knowledge_current = True
        key = policy._atomic_shop_transaction_key(outside)
        self.assertEqual(key, "5")
        claim = policy._claim_register.declare("shop-buy", observe(
            policy._store_visit.claim_operation_identity, 8, "store-operation"))
        policy._record_execution_declaration(claim, key, policy.last_reason)
        policy.confirm_key_posted(key)
        policy.last_reason = "shop:one-shot-in-flight"
        self.compare(policy, outside, "", None)
        self.compare(policy, inside, None, None, holder_dispatch=True)
        changed = replace(inside, store=StoreState(5, inside.store.items))
        self.compare(policy, changed, None, "ownership:declaration-stale:shop-buy",
                     holder_dispatch=True)

    def test_live13_and_live15_identification_continues(self):
        state = json.loads((FIXTURES / "live-screens/live13-before-identify-state.json").read_text(
            encoding="utf8"))
        board = parse_snapshot(state, {})
        for capture in ("live13-star-identify-equipment-prompt.json",
                        "live15-read-scroll-prompt.json"):
            with self.subTest(capture=capture):
                screen = json.loads((FIXTURES / "live-screens" / capture).read_text(encoding="utf8"))
                self.assertTrue(screen)
                policy = HengbotPolicy()
                key = policy._town_equipped_identification_key(board)
                self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))
                self.compare(policy, board, key, None)

    @recorded_loadout_replay
    def test_six_fixture_first_boards_public_off_shadow_equals_on(self):
        names = (
            "unaffordable-claim-tour-20260922", "town-approach-retired-20260925",
            "overweight-home-unreachable-20260925", "home-withdraw-failed-stock-present-20260925",
            "recall-read-cancel-pingpong-20260925", "stuck-prompt-staged-tail-20260925")
        for name in names:
            with self.subTest(fixture=name), pre_fix_loot_observation():
                boundaries = json.loads((FIXTURES / (name + ".jsonl.boundaries.json")).read_text(
                    encoding="utf8"))
                # Stuck's input_rows already indexes its four-row closing window.
                with gzip.open(FIXTURES / (name + ".jsonl.gz"), "rt", encoding="utf8") as f:
                    lines = [next(f) for _ in range(boundaries["input_rows"][0])]
                monrace = load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))
                outcomes = []
                for enforced in (False, True):
                    policy = HengbotPolicy()
                    policy._town_claim_bar_enforced = enforced
                    _, snapshots = _consume_response_sequence(
                        lines, policy, lambda _key: True, monrace)
                    board = snapshots[-1]
                    policy.prime(board)
                    if "attach_skill_knowledge" in boundaries:
                        policy.consume_skill_knowledge(boundaries["attach_skill_knowledge"])
                    key = policy.choose_key(board)
                    outcomes.append((key, policy.last_reason, policy.decision_claim))
                off, on = outcomes
                shadow = (off[2] or {}).get("s33_shadow")
                on_stop = on[1] if on[0] is None and on[1].startswith((
                    "ownership:declaration-", "ownership:holder-silent:",
                    "ownership:gate-missing:")) else None
                self.assertEqual(shadow["would_stop"] if shadow else None, on_stop)
                self.assertEqual(off[:2], on[:2])


if __name__ == "__main__":
    unittest.main()
