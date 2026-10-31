"""OIL-FULL-LAMP: the recorded n1-c life-072 oil waste into a full lantern (2026-10-31 21:58).

The worn 真鍮のランタン {並, Q34} is unidentified, so its fuel is hidden.
Right after descending to Yeek cave 1F (decision 836, turn 85412) the bot
posted ``fundraise:refill-light`` '\\Fa' five times; each was answered
「ランプに油を注いだ。」「ランプの油は一杯だ。」 and all five flasks were gone.
The unidentified-lantern darkness test read the grid's ``lite`` flag, which
the records never set, although ``can_see_own_grid`` was true and
``light_radius`` 2.  On the next town visit (decision 1069, turn 96693) the
departure top-up poured again into the lamp the game had just called full.

Boards, the game's replies and decision rows are recorded
(tests/fixtures/oil-full-lamp-20261031.json.gz, see
tests/extract_oil_full_lamp_fixture.py).  Keys go through the public
chooser and the production executor port.

DECLARED RECONSTRUCTED: the capture keeps the fundraising mode, not the
staff sequence's record; the town case restores the explicit-target mining
run that owned the visit (me-staff:fundraise:staff-stockout:9578 of the same
life) and the power list read by this process.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import lamp_fuel, me_staff_sequence
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "oil-full-lamp-20261031.json.gz"
REFILL_REASONS = {"refill-light", "fundraise:refill-light"}
STAFF_STOCKOUT_TARGET = 9578


class OilFullLampRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)

    def board(self, turn):
        return copy.deepcopy(self.data["boards"][str(turn)])

    def policy(self, raw, *, mode):
        policy = HengbotPolicy(monrace_knowledge={})
        policy.prime(parse_snapshot(raw, {}))
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        # DECLARED RECONSTRUCTED (module docstring).
        record = me_staff_sequence.state(policy)
        record.powers_read = True
        record.fundraise_target, record.fundraise_runs = STAFF_STOCKOUT_TARGET, 1
        policy._fundraising_mode = mode
        policy._supply_stockout_gold_target = STAFF_STOCKOUT_TARGET
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        return policy

    @staticmethod
    def choose(policy, raw):
        return str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))

    def post(self, policy, raw, key, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)

    def test_recorded_rows_poured_into_a_full_lamp(self):
        decisions = self.data["decisions"]
        self.assertEqual([decisions[str(n)]["reason"] for n in range(836, 841)],
                         ["fundraise:refill-light"] * 5)
        self.assertEqual(decisions["1069"]["reason"], "refill-light")
        for sequence in (837, 838, 839, 840, 841, 1070):
            self.assertIn("ランプの油は一杯だ。", decisions[str(sequence)]["messages"])
        board = parse_snapshot(self.board(85412), {})
        lantern = next(item for item in board.equipment if item.is_light)
        self.assertTrue(lantern.is_lantern)
        self.assertFalse(lantern.known)
        self.assertEqual((board.light_radius, board.can_see_own_grid), (2, True))

    def test_descent_board_keeps_the_burning_lantern(self):
        raw = self.board(85412)
        policy = self.policy(raw, mode="mine")
        key = self.choose(policy, raw)
        # Recorded: fundraise:refill-light '\Fa' into a burning lantern.
        self.assertNotIn(policy.last_reason, REFILL_REASONS)
        self.assertFalse(key.startswith("\\F"), key)

    def test_after_the_first_full_reply_no_second_refill(self):
        raw = self.board(85412)
        policy = self.policy(raw, mode="mine")
        self.choose(policy, raw)
        # The recorded first refill and the game's recorded reply.
        reply = self.board(85416)
        self.post(policy, raw, "\\Fa", reply)
        key = self.choose(policy, reply)
        self.assertEqual(lamp_fuel.known_fuel_floor(policy, parse_snapshot(reply, {})), 15000)
        self.assertNotIn(policy.last_reason, REFILL_REASONS)
        self.assertFalse(key.startswith("\\F"), key)

    def test_departure_top_up_skips_the_lamp_known_full(self):
        # Without the 「一杯だ」 knowledge the recorded departure top-up stands.
        town = self.board(96693)
        fresh = self.policy(town, mode="mine")
        self.assertEqual(self.choose(fresh, town), "\\Fa")
        self.assertEqual(fresh.last_reason, "refill-light")
        # With it (the fifth reply at turn 85438): 11255 game turns burn at
        # most 1125 fuel, so the lamp still holds over the refill threshold.
        floor = self.board(85438)
        policy = self.policy(floor, mode="mine")
        self.choose(policy, floor)
        key = self.choose(policy, town)
        self.assertNotIn(policy.last_reason, REFILL_REASONS)
        self.assertFalse(key.startswith("\\F"), key)
        self.assertEqual(lamp_fuel.known_fuel_floor(policy, parse_snapshot(town, {})),
                         15000 - (96693 - 85438) // 10)


if __name__ == "__main__":
    unittest.main()
