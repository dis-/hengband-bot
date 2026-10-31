"""#47: the recorded n1-c Magic-Eater no-key-exhausted stops of 2026-10-31.

Boards, knowledge rows and decision rows are frozen in
tests/fixtures/me-nokey-20261031.json.gz (tests/extract_me_nokey_1031.py).
Every decision goes through the public ``choose_key``; posted keys go
through the production executor, and the driver stop through ``_run_follow``.

DECLARED RECONSTRUCTED: the staff sequence record of each policy is the
server incident capture's ``_me_staff_sequence`` (RECORDED_SEQUENCE in the
fixture); a case states which of its fields it changes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hengbot import me_staff_sequence as sequence
from hengbot.cli import (
    SendResult, _ExecutorInputPort, _build_argument_parser, _run_follow, _transport_key,
)
from hengbot.flight_recorder import policy_state
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "me-nokey-20261031.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)


def staff_board(index):
    """Ring row 104 + index of the 061452 capture."""
    return copy.deepcopy(CASE["staff"]["boards"][index])


def staff_policy(raw, *, record=True, **changes):
    policy = ConservativePolicy()
    policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    policy.consume_skill_knowledge(copy.deepcopy(CASE["staff"]["skill"]))
    if record:
        # DECLARED RECONSTRUCTED (module docstring); ``changes`` override.
        recorded = {**CASE["recorded_sequence"], "failure": None, **changes}
        state = sequence.state(policy)
        state.absorbed = {int(sval): count for sval, count in recorded["absorbed"].items()}
        state.bought = frozenset(recorded["bought"])
        state.completed_stages = {int(k): v for k, v in recorded["completed_stages"].items()}
        state.fundraise_runs = recorded["fundraise_runs"]
        state.reached_runs = recorded["reached_runs"]
        state.fundraise_why = recorded["fundraise_why"]
        state.shelf_after_turn = recorded["shelf_after_turn"]
        state.stage = recorded["stage"]
        state.failure = recorded["failure"]
    return policy


def decide(policy, raw, skill=None):
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    key = str(policy.choose_key(board))
    if key.startswith("~f") and skill is not None:
        # DECLARED CONSTRUCTED: the recorded ~f reply answers the re-request.
        policy.consume_skill_knowledge(dict(copy.deepcopy(skill), turn=raw["turn"]))
        key = str(policy.choose_key(board))
    return key


def without_staffs(raw, svals):
    raw = copy.deepcopy(raw)
    if "inventory" in raw:
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == 55 and item["sval"] in svals)]
    return raw


def drive_staff_boards(policy, last, absorbed=()):
    """Ring rows 104..104+last through choose_key, as the recorded run saw them.

    DECLARED CONSTRUCTED (``absorbed``): those staffs are taken out of the
    pack, as 'G' consumes the absorbed device (mind-magic-eater.cpp).
    """
    key = None
    for raw in CASE["staff"]["boards"][:last + 1]:
        raw = without_staffs(raw, absorbed)
        if raw["type"] == "knowledge":
            policy.consume_home_knowledge(
                tuple(_parse_items(raw["knowledge"]["items"], protocol=3)))
            continue
        key = decide(policy, raw, CASE["staff"]["skill"])
        policy.confirm_key_posted(key) if key else None
    return key


class PostedKey(harness.ProductionHarness):
    def post(self, policy, raw, key):
        """Send ``key`` through the production executor on ``raw``."""
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


class NamedFinalStopTest(unittest.TestCase):
    """R0: a policy final stop sent as "" is that stop, not no-key-exhausted."""

    def test_capture_pins_the_recorded_stop(self):
        stop = CASE["staff"]["stop"]
        self.assertEqual((stop["reason"], stop["key"]), ("quest:blocked:me-staff", ""))
        self.assertEqual(CASE["recorded_sequence"]["failure"],
                         "fundraise-target-drift:staff-stockout:2530")
        opening = CASE["opening"]["stop"]
        self.assertEqual((opening["reason"], opening["key"]), ("quest:blocked:opening-route", ""))
        self.assertEqual(opening["fixedquest_readiness"]["opening_route_failure"],
                         "stop:unaffordable-quest-reserve")

    def test_driver_stops_on_the_named_staff_stop(self):
        # The recorded board after the Magic shop (ring row 108) with the
        # recorded failure: the sequence re-declares its stop with "".
        raw = staff_board(4)
        policy = staff_policy(raw, failure=CASE["recorded_sequence"]["failure"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            state_path.write_text(json.dumps(staff_board(3)) + "\n", encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(root / "decisions.jsonl"),
                "--poll-interval", "0.001", "--stall-timeout", "0.01",
                "--dump-interval-seconds", "0",
            ])
            args.wait_telemetry = Mock()
            appended = False

            def append_board():
                # _run_follow seeks to EOF; the board arrives on its first pass.
                nonlocal appended
                if not appended:
                    appended = True
                    with state_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(raw) + "\n")

            with (
                patch("hengbot.cli._arm_decision_watchdog", side_effect=append_board),
                patch("hengbot.cli._append_capture_ledger"),
                patch("hengbot.cli._freeze_incident_safely") as freeze,
                patch("builtins.print") as output,
            ):
                result = _run_follow(args, policy, lambda *_a, **_k: self.fail("posted a key"),
                                     policy._monrace_knowledge)
            rows = [json.loads(line) for line in
                    (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result, 0)
        self.assertEqual([(row["reason"], row["key"]) for row in rows if "reason" in row],
                         [("quest:blocked:me-staff", "")])
        self.assertEqual(freeze.call_args.args[1], "quest:blocked:me-staff")
        printed = [str(call.args[0]) for call in output.call_args_list if call.args]
        self.assertTrue(any(line.startswith("<quest:blocked:me-staff> ") for line in printed))
        self.assertFalse(any(line.startswith("<no-key-exhausted>") for line in printed))

    def test_incident_policy_state_keeps_the_opening_route_failure(self):
        policy = ConservativePolicy()
        policy._opening_q1_failure = "stop:unaffordable-quest-reserve"
        self.assertEqual(policy_state(policy)["state"]["_opening_q1_failure"],
                         "stop:unaffordable-quest-reserve")


class StaffStockoutTest(PostedKey):
    """鍵1a: stage 2's fifth staff out of stock with four carried (life-054 061452).

    Owner 2026-10-31 「持っている分を先に取り込む」: the carried staffs go to the
    Tower now; the stock-out waits do not count toward the run limit.
    """

    def test_capture_pins_four_carried_staffs_and_no_detect_evil(self):
        shelf = {(item["tval"], item["sval"]) for item in staff_board(1)["store"]["items"]}
        self.assertNotIn((55, sequence.SV_STAFF_DETECT_EVIL), shelf)
        carried = sorted(item["sval"] for item in staff_board(4)["inventory"] if item["tval"] == 55)
        self.assertEqual(carried, [sequence.SV_STAFF_LITE, sequence.SV_STAFF_MAPPING,
                                   sequence.SV_STAFF_DETECT_TRAP, sequence.SV_STAFF_DETECT_DOOR])
        self.assertEqual(staff_board(4)["player"]["gold"], 60981)

    def test_carried_staffs_go_to_the_tower_while_the_fifth_is_out_of_stock(self):
        # The recorded record (six reached stock-out runs); unfixed, the board
        # after the Magic shop stopped with fundraise-target-drift.
        policy = staff_policy(staff_board(0))
        key = drive_staff_boards(policy, 4)
        self.assertIsNone(sequence.state(policy).failure)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant", key)
        self.assertNotEqual(key, "")
        self.post(policy, staff_board(4), key)

    def test_stockout_wait_is_not_counted_toward_the_run_limit(self):
        # DECLARED CONSTRUCTED: the four carried staffs already absorbed, so
        # only Detect Evil remains and nothing is carried for the Tower.
        absorbed = {**CASE["recorded_sequence"]["absorbed"],
                    **{str(sval): 9 for sval in (8, 9, 12, 13)}}
        policy = staff_policy(staff_board(0), absorbed=absorbed)
        key = drive_staff_boards(policy, 4, absorbed=(8, 9, 12, 13))
        record = sequence.state(policy)
        self.assertIsNone(record.failure)
        self.assertIn("me-staff:fundraise:staff-stockout:", policy.last_reason, key)
        self.assertEqual((record.fundraise_runs, record.reached_runs), (6, 6))
        # The run comes back with its gold target met: still not counted.
        policy._fundraising_mode = None
        decide(policy, without_staffs(staff_board(4), (8, 9, 12, 13)), CASE["staff"]["skill"])
        self.assertIsNone(record.fundraise_target)  # the returned run was settled
        self.assertEqual((record.fundraise_runs, record.reached_runs), (6, 6))
        self.assertIsNone(record.failure)


if __name__ == "__main__":
    unittest.main()
