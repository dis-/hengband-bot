"""D35: the recorded n1-c life-045 staff-stockout mining run (2026-10-31).

Owner: 「魔道具術師の採掘が全然壁を掘らずに街に戻ってるけどなんか戦士と
アルゴリズム違う？」.  The zombie Magic-Eater (Lv8, 1647 gold) saw the Magic
shop sell the Identify staff but not Treasure Location, and the staff
sequence started ``me-staff:fundraise:staff-stockout:1648``: its target was
``max(gold + 1, estimate + supplies)``.  On Yeek cave 1F the run detected
146 veins, dug one, picked up 37 gold (1660 >= 1648) and the very next
decision was fundraise:seek-upstairs with 145 veins still known; this
repeated over a dozen times.

The town and dungeon boards, the Magic shop page and the knowledge rows are
recorded (tests/fixtures/me-stockout-run-20261031.json.gz, see
tests/extract_me_stockout_run_fixture.py); every decision goes through the
public ``choose_key`` and the dungeon key through the production executor.

DECLARED RECONSTRUCTED: the boards between the town decision and the
dungeon board (the departure, the descent, the detection read on this
floor) are not replayed.  The dungeon policy carries the town decision's own
sequence record and target, the mining mode the departure sets, the
detection marked as read on this floor, and the cross-area purpose the
departure posts (the run was started with --enforce-crossarea-fundraising).
The reply to the dungeon key is constructed (the board unchanged, ten game
turns later).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import me_staff_sequence as sequence
from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import (
    RUMOR_COST, RUMOR_GOLD_RESERVE, RUMOR_READS_PER_VISIT, TOWN_TELEPORT_COST,
)
from hengbot.policy_fundraising import (
    FundraisingPurpose, FundraisingPurposeRecord, FundraisingTransportChild,
)
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "me-stockout-run-20261031.json.gz"
# The staffs' base estimate (2 x base cost of Perception 400 and Treasure
# Location 200) and the rumor/travel/recharge total on the recorded pack:
# two fares, the Tower's recharge of the carried wand and staff (170), the
# inn reserve and one visit of rumor reads.  No survival supply is unmet.
RECORDED_TARGET = (2 * (400 + 200) + 2 * TOWN_TELEPORT_COST + 170
                   + RUMOR_GOLD_RESERVE + RUMOR_COST * RUMOR_READS_PER_VISIT)


class MeStockoutRunRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def raw(self, name, gold=None):
        raw = copy.deepcopy(self.case[name])
        if gold is not None:
            raw["player"]["gold"] = gold
        return raw

    def policy(self, raw, knowledge):
        policy = ConservativePolicy()
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        skill, home = self.case[knowledge]
        policy.consume_skill_knowledge(skill)
        policy.consume_home_knowledge(_parse_items(home["knowledge"]["items"], protocol=3))
        # DECLARED CONSTRUCTED: this process already read the game's staff
        # power list (me_staff_sequence.read_powers, #47).
        sequence.state(policy).powers_read = True
        return policy

    @staticmethod
    def decide(policy, raw):
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        return key

    def town_decision(self):
        """The recorded shop page, then the recorded town board."""
        store, town = self.raw("store"), self.raw("town")
        policy = self.policy(store, "town_knowledge")
        key = self.decide(policy, store)
        self.assertEqual(policy.last_reason, "shop:observe-and-leave")
        policy.confirm_key_posted(key)
        key = self.decide(policy, town)
        return policy, key

    def dungeon_policy(self, town_policy, raw):
        policy = self.policy(raw, "dungeon_knowledge")
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        # DECLARED RECONSTRUCTED (module docstring).
        policy._me_staff_sequence = copy.deepcopy(sequence.state(town_policy))
        policy._supply_stockout_gold_target = town_policy._supply_stockout_gold_target
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        policy._mining_scroll_used_floor = board.floor_key
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_runs_started = 1
        purpose = FundraisingPurpose(1, "mine", False)
        policy._fundraising_run_purpose = purpose
        policy._fundraising_purpose_record = FundraisingPurposeRecord(
            purpose, child=FundraisingTransportChild(
                purpose.identity, "depart", (0, 0, 0), 1, state="complete"))
        return policy

    def post(self, policy, raw, key):
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))

    def test_capture_pins_the_recorded_run(self):
        decisions = self.case["decisions"]
        self.assertEqual(decisions["209432"]["reason"],
                         "town:entrance-step-off:me-staff:fundraise:staff-stockout:1648")
        self.assertEqual(decisions["209432"]["player"]["gold"], 1647)
        row = decisions["212034"]
        self.assertEqual((row["reason"], row["key"]), ("fundraise:seek-upstairs", "1"))
        self.assertEqual(row["player"]["gold"], 1660)
        self.assertEqual((row["mining"]["collected"], row["mining"]["remaining_known"]), (1, 145))
        shelf = {(it["tval"], it["sval"]) for it in self.case["store"]["store"]["items"]}
        self.assertIn((55, sequence.SV_STAFF_IDENTIFY), shelf)
        self.assertNotIn((55, sequence.SV_STAFF_DETECT_GOLD), shelf)

    def test_stockout_target_is_what_the_sequence_still_needs(self):
        policy, _ = self.town_decision()
        board = parse_snapshot(self.raw("town"), policy._monrace_knowledge)
        self.assertEqual(sequence.recharge_cost(board), 170)
        self.assertEqual(sequence.supply_cost(policy, board), 0)
        self.assertEqual(RECORDED_TARGET, 3070)
        self.assertEqual(policy.last_reason,
                         f"town:entrance-step-off:me-staff:fundraise:staff-stockout:{RECORDED_TARGET}")
        self.assertEqual(policy._supply_stockout_gold_target, RECORDED_TARGET)

    def test_after_the_first_nugget_the_run_keeps_mining(self):
        # The recorded 1660 gold, and DECLARED CONSTRUCTED 4013 gold: a run
        # whose gold already covers its target still mines like the
        # warrior's run instead of returning (no gold-target return).
        for dungeon_gold in (None, RECORDED_TARGET + 943):
            with self.subTest(gold=dungeon_gold):
                town_policy, _ = self.town_decision()
                raw = self.raw("dungeon", dungeon_gold)
                policy = self.dungeon_policy(town_policy, raw)
                key = self.decide(policy, raw)
                self.assertEqual(len(policy._known_treasure), 145)
                self.assertIn(policy.last_reason,
                              {"fundraise:dig-to-treasure", "fundraise:seek-treasure"}, key)
                self.assertTrue(sequence.mines_floor_out(policy))
                self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
