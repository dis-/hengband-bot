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
from hengbot.cli import _build_argument_parser, _run_follow
from hengbot.flight_recorder import policy_state
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy


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


def decide(policy, raw):
    return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


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


if __name__ == "__main__":
    unittest.main()
