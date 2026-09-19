"""Input causal-barrier pins using a source-derived one-request-per-hook fake."""

import json
import copy
from pathlib import Path
import ast
import hashlib
import gzip
import unittest
import time
from io import StringIO
from types import SimpleNamespace

from hengbot.control_client import ControlClient, KeyPostStatus
from hengbot.input_executor import (
    Continuation, Operation, OperationExecutor, ScreenKind, Transport,
    classify_screen, compose_barrier_board,
)
from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _send_new_decision_key,
    _send_prompt_gated_decision_key, _store_buy_continuations,
)
from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT, SOURCE_PROMPT
from hengbot.quest_navigator import QuestFloorNavigator


def command_screen(turn=1):
    lines = [""] * 24
    lines[1] = "Human"
    lines[10] = " " * 20 + "@"
    lines[23] = " " * 72 + "Surf."
    return {"width": 80, "height": 24, "cursor": {"visible": False, "y": 10, "x": 20},
            "lines": lines, "turn": turn}


def prompt_screen(text):
    value = command_screen()
    value["lines"][0] = text
    return value


def store_screen(message=""):
    value = command_screen()
    value["cursor"] = {"visible": True, "y": 20, "x": 0}
    value["lines"][0] = message
    value["lines"][20] = "You may: p) Purchase an item. s) Sell an item."
    value["lines"][21] = " ESC) Exit from Building."
    return value


def source_derived_identify_viewer(*, final=False):
    """identification.cpp:762-799 result screen at the documented columns."""
    value = command_screen()
    value["lines"][5] = " " * 20 + "Item Attributes:"
    value["lines"][20] = " " * 15 + (
        "[Press any key to continue]" if final else "-- more --"
    )
    value["cursor"] = {"visible": True, "y": 20, "x": 15}
    return value


class _FakeSocket:
    def __init__(self, game):
        self.game, self.output = game, bytearray()
        self.closed = False
        self.recv_timeout = False
        self.timeout = None
        self.send_elapsed = 0.0

    def settimeout(self, value):
        self.timeout = value

    def close(self):
        self.closed = True

    def sendall(self, payload):
        started = time.monotonic()
        request = json.loads(payload)
        response, fault = self.game.hook(request)
        self.send_elapsed = time.monotonic() - started
        if fault == "timeout":
            response = None
            self.recv_timeout = True
        if response is not None:
            wire = (json.dumps(response, ensure_ascii=False) + "\n").encode()
            chunks = self.game.fragments.pop(0) if self.game.fragments else [len(wire)]
            start = 0
            for size in chunks:
                self.output.extend(wire[start:start + size]); start += size
            self.output.extend(wire[start:])
        if fault == "partial-send":
            raise ConnectionError("partial socket send after acceptance")

    def recv(self, size):
        if self.timeout is not None and self.send_elapsed > self.timeout:
            self.output.clear()
            self.send_elapsed = 0.0
            raise TimeoutError("timed out")
        if self.recv_timeout:
            self.recv_timeout = False
            raise TimeoutError("timed out")
        if not self.output:
            return b""
        amount = min(size, self.game.recv_chunks.pop(0) if self.game.recv_chunks else size)
        result = bytes(self.output[:amount]); del self.output[:amount]
        return result


class FaithfulHookGame:
    """Faithful subset of Term/frontend FIFO and one request per empty-read hook.

    The interpreter consumes the atomic Term FIFO, renders the next wait, and
    records its JSONL snapshot *before* the following blocking command read.
    Inner prompts deliberately add no JSONL. WM FIFO pumping happens only after
    the currently waiting hook returns. Responses can fragment independently.
    """
    capacity = 32

    def __init__(self):
        self.frontend_fifo, self.term_fifo = [], []
        self.accepted, self.wm_posts, self.jsonl, self.trace = [], [], [], []
        self.screen, self.state = command_screen(1), {"turn": 1, "grid_map": {"runs": []}}
        self.screens, self.states = [], []
        self.faults, self.fragments, self.recv_chunks = [], [], []
        self.pending_prompt = None
        self.hook_waiting = True

    def socket_factory(self, *_args, **_kwargs):
        return _FakeSocket(self)

    def post_wm(self, char):
        self.trace.append(("post", char, self.hook_waiting)); self.frontend_fifo.append(char); self.wm_posts.append(char)
        return True

    def _decode(self, notation):
        named = {"e": "\x1b", "s": " ", "r": "\r", "n": "\n", "t": "\t", "b": "\b", "\\": "\\", "^": "^"}
        out, i = "", 0
        while i < len(notation):
            if notation[i] == "\\":
                i += 1
                if notation[i] == "x": out += chr(int(notation[i + 1:i + 3], 16)); i += 2
                else: out += named[notation[i]]
            elif notation[i] == "^": i += 1; out += chr(ord(notation[i]) & 31)
            else: out += notation[i]
            i += 1
        return out

    def _consume(self, *, pump_frontend=True):
        if pump_frontend and self.frontend_fifo:
            self.term_fifo.extend(self.frontend_fifo); self.frontend_fifo.clear()
        if not self.term_fifo:
            return
        raw = "".join(self.term_fifo); self.term_fifo.clear()
        self.state = self.states.pop(0) if self.states else {
            "turn": self.state["turn"] + 1, "grid_map": {"runs": []}
        }
        self.screen = self.screens.pop(0) if self.screens else command_screen(self.state["turn"])
        # Source-derived inner prompts are raised inside a command and emit no JSONL.
        if not self.screen["lines"][0].rstrip():
            self.jsonl.append(dict(self.state))

    def hook(self, request):
        # A response is flushed and at most this one new request is dispatched.
        op = request["op"]
        self.hook_waiting = True
        if op not in ("keys", "info") and self.term_fifo:
            # A later hook is reachable only after the ACK hook returned and
            # the interpreter consumed the pending Term FIFO at its next read.
            self._consume(pump_frontend=False)
        self.trace.append(("issue", op, request["id"]))
        fault = self.faults.pop(0) if self.faults else None
        if op == "keys":
            raw = self._decode(request["keys"])
            if fault == "backpressure" or len(self.term_fifo) + len(raw) > self.capacity:
                response = {"id": request["id"], "ok": False,
                            "error": ControlClient.BACKPRESSURE_ERROR}
            else:
                self.term_fifo.extend(raw) # atomic insertion; consumed after ACK hook returns
                self.accepted.append(raw)
                response = {"id": request["id"], "ok": True, "result": {"pushed": len(raw)}}
        elif op == "info":
            # The fence reply is deliberately old. Its hook return permits the
            # frontend FIFO to be pumped before the next screen hook.
            response = {"id": request["id"], "ok": True, "result": {"turn": self.state["turn"]}}
            self._consume()
        elif op == "screen":
            response = {"id": request["id"], "ok": True, "result": self.screen}
        else:
            response = {"id": request["id"], "ok": True, "result": self.state}
        if fault == "wrong-id": response["id"] += 1
        if fault == "wrong-pushed": response["result"]["pushed"] -= 1
        self.trace.append(("reply", op, response["id"]))
        if fault == "ack-loss": response = None
        if op == "keys" and fault == "flush":
            self.term_fifo.clear()
            self.screen = command_screen(self.state["turn"])
        self.hook_waiting = not self.term_fifo
        return response, fault


class ProductionHarness(unittest.TestCase):
    def make(self, game=None):
        game = game or FaithfulHookGame()
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        return game, client, OperationExecutor(client, drain=lambda: list(game.jsonl))

    @staticmethod
    def store_state(turn, messages=()):
        return {
            "turn": turn, "floor": {"dungeon_id": 0, "level": 0},
            "player": {"gold": 5483}, "inventory": [], "equipment": [],
            "grid_map": {"runs": []}, "messages": list(messages),
            "store": {"store_type": 4, "items": []},
        }


class AcceptedObservationRetryPins(ProductionHarness):
    def test_send_instrumentation_preserves_request_sequence_and_board(self):
        game, _client, executor = self.make()
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        expected_state = {
            "turn": 2,
            "grid_map": {
                "palette": [[1, 0, 0, True], [2, 0, 0, False]],
                "runs": [[1, 2, 3, 0], [1, 5, 2, 1]],
            },
        }
        game.states = [copy.deepcopy(expected_state)]
        result = executor.submit(
            Operation(78, "timing:test", "6", executor.ready_board),
            deadline=9999999999,
        )
        expected_board = copy.deepcopy(expected_state)
        expected_board.update({
            "messages": [],
            "_completed_operation_sequence": 78,
            "_completed_operation_owner": "timing:test",
            "_completed_operation_receipt": result.board["_completed_operation_receipt"],
        })
        self.assertEqual(
            json.dumps(result.board, sort_keys=True, separators=(",", ":")),
            json.dumps(expected_board, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(
            [entry[1] for entry in game.trace if entry[0] == "issue"],
            ["screen", "state", "keys", "screen", "state"],
        )
        numeric_keys = {
            "ack_wait_ms", "screen_wait_ms", "screen_classification_ms",
            "state_wait_ms", "jsonl_drain_ms", "jsonl_drain_bytes",
            "jsonl_drain_records", "jsonl_decode_ms", "state_deepcopy_ms",
            "board_compose_ms", "posting_contract_settlement_ms", "segments",
            "requests", "observation_epoch_refreshes", "known_cells",
            "request_first_byte_ms", "first_last_byte_ms",
            "request_json_decode_ms", "response_bytes",
        }
        self.assertTrue(numeric_keys.issubset(result.timing))
        self.assertTrue(all(result.timing[key] >= 0 for key in numeric_keys))
        self.assertEqual(result.timing["known_cells"], 3)
        self.assertEqual(result.timing["requests"], 3)
        self.assertEqual(len(result.timing["control_requests"]), 3)
        self.assertTrue(all({
            "request", "kind", "attempt_count", "connect_count",
            "retry_count", "response_bytes", "attempts",
        }.issubset(item) for item in result.timing["control_requests"]))
        self.assertTrue(all({
            "request_first_byte_ms", "first_last_byte_ms", "json_decode_ms",
            "response_bytes", "connected",
        }.issubset(attempt) for item in result.timing["control_requests"]
            for attempt in item["attempts"]))

    def test_single_segment_ack_gets_post_ack_observation_grace(self):
        game = FaithfulHookGame()
        client = ControlClient(
            1, request_budget=0.01, retries=0, backoff=0,
            socket_factory=game.socket_factory,
        )
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(
            executor.observe_boundary(deadline=9999999999).outcome, "ready"
        )
        original = game.hook
        delayed = False

        def slow_first_post_ack_screen(request):
            nonlocal delayed
            if request["op"] == "screen" and game.accepted and not delayed:
                delayed = True
                time.sleep(0.03)
            return original(request)

        game.hook = slow_first_post_ack_screen
        operation = Operation(
            79, "identify:full-equipped", "rg/j", executor.ready_board,
            response_grace=0.1,
        )
        result = executor.submit(
            operation, deadline=time.monotonic() + client.request_budget
        )
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["rg/j"])
        self.assertEqual(
            [entry[1] for entry in game.trace if entry[0] == "issue"],
            ["screen", "state", "keys", "screen", "state"],
        )

    def test_keys_ack_first_screen_timeout_second_succeeds_without_repost(self):
        game = FaithfulHookGame()
        _client = ControlClient(
            1, request_budget=2, retries=0, backoff=0,
            socket_factory=game.socket_factory,
        )
        self.addCleanup(_client.close)
        executor = OperationExecutor(_client, drain=lambda: list(game.jsonl))
        self.assertEqual(
            executor.observe_boundary(deadline=9999999999).outcome, "ready"
        )
        game.faults = [None, "timeout"]
        result = executor.submit(
            Operation(79, "identify:full-equipped", "rg/j", executor.ready_board),
            deadline=9999999999,
        )
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["rg/j"])
        self.assertEqual(
            [entry[1] for entry in game.trace if entry[0] == "issue"],
            ["screen", "state", "keys", "screen", "screen", "state"],
        )
        retried = next(
            item for item in result.timing["control_requests"]
            if item["kind"] == "screen"
        )
        self.assertEqual(retried["attempt_count"], 2)
        self.assertEqual(retried["retry_count"], 1)

    def test_screen_failure_through_deadline_is_same_visible_terminal(self):
        game, _client, executor = self.make()
        self.assertEqual(
            executor.observe_boundary(deadline=9999999999).outcome, "ready"
        )
        original = game.hook

        def lose_post_ack_screens(request):
            response, fault = original(request)
            if request["op"] == "screen" and game.accepted:
                return None, fault
            return response, fault

        game.hook = lose_post_ack_screens
        result = executor.submit(
            Operation(79, "identify:full-equipped", "rg/j", executor.ready_board,
                      response_grace=0.01),
            deadline=time.monotonic() + 0.001,
        )
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(
            result.reason,
            "<stuck-prompt> owner=identify:full-equipped phase=screen "
            "transport=accepted request_id=3 reason=read-only request failed",
        )
        self.assertEqual(game.accepted, ["rg/j"])

    def test_lost_mutating_ack_is_never_replayed(self):
        game, _client, executor = self.make()
        self.assertEqual(
            executor.observe_boundary(deadline=9999999999).outcome, "ready"
        )
        game.faults = ["ack-loss"]
        result = executor.submit(
            Operation(80, "mutating", "6", executor.ready_board),
            deadline=9999999999,
        )
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["6"])
        self.assertEqual(
            [entry[1] for entry in game.trace if entry[0] == "issue"],
            ["screen", "state", "keys"],
        )


class BarrierProvenanceS3Pin(ProductionHarness):
    @staticmethod
    def posting_snapshot(*, messages=(), receipt=None, recalling=False):
        return SimpleNamespace(
            turn=1, floor_key=(0, 0, 0), messages=tuple(messages),
            completed_operation_receipt=receipt, store=None,
            inventory=[], equipment=[],
            player=SimpleNamespace(
                position=Position(1, 1), gold=5483, recalling=recalling,
            ),
        )

    def test_recorded_prompt_history_receipt_releases_only_matching_post(self):
        fixture = json.loads((
            Path(__file__).parent / "fixtures" / "live-screens" /
            "36-home-prompt-owner-mismatch-20260915-1408.json"
        ).read_text(encoding="utf-8"))["result"]
        with gzip.open(
            Path(__file__).parent / "fixtures" /
            "barrier-provenance-s3-r12-20260915.jsonl.gz",
            "rt", encoding="utf-8",
        ) as replay:
            rows = [json.loads(line) for line in replay]
        prompt = next(
            row["messages"][-1] for row in rows
            if row.get("turn") == 2898828 and row.get("messages")
        )
        game = FaithfulHookGame()
        game.screens = [fixture, command_screen(3)]
        game.states = [self.store_state(2, [prompt]), {
            "turn": 3, "floor": {"dungeon_id": 0, "level": 0},
            "player": {"gold": 5483}, "inventory": [], "equipment": [],
            "grid_map": {"runs": []}, "messages": [prompt],
        }]
        _game, _client, executor = self.make(game)
        contract = PostingContract()
        executor.accepted = contract.accepted
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2)
        before = self.posting_snapshot()
        sent, _ = _send_new_decision_key(
            port, "travel", "\x1b`n(.", None, set(), in_store=False,
            decision={"sequence": 2, "reason": "shop:travel"},
            snapshot=before, posting_contract=contract,
        )
        self.assertTrue(sent)
        receipt = port.last_result.board["_completed_operation_receipt"]
        self.assertEqual(
            (receipt["sequence"], receipt["owner"],
             receipt["accepted_segments"][0]["keys"],
             receipt["terminal_kind"]),
            (2, "shop:travel", "\x15", "store"),
        )
        parsed = parse_snapshot(dict(
            rows[-1], _completed_operation_receipt=receipt,
            _completed_operation_sequence=2,
            _completed_operation_owner="shop:travel",
        ))
        self.assertEqual(parsed.completed_operation_receipt, receipt)
        terminal = self.posting_snapshot(
            messages=(prompt,), receipt=receipt,
        )
        terminal.store = SimpleNamespace(
            store_type=7, stock_num=0, page_top=0, items=(),
        )
        self.assertTrue(contract.allow(
            terminal, "\x1b", "home:scan-incomplete-open-page"
        ))
        self.assertIsNone(contract.last_incident)

        sent, _ = _send_new_decision_key(
            port, "home", "\x1b", None, set(), in_store=True,
            decision={"sequence": 3,
                      "reason": "home:scan-incomplete-open-page"},
            snapshot=terminal, posting_contract=contract,
        )
        self.assertTrue(sent)
        second_receipt = port.last_result.board["_completed_operation_receipt"]
        reselection = self.posting_snapshot(
            messages=(prompt, "later"), receipt=second_receipt,
        )
        sent, _ = _send_new_decision_key(
            port, "home-again", "\x1b", None, set(), in_store=False,
            decision={"sequence": 4,
                      "reason": "home:scan-incomplete-open-page"},
            snapshot=reselection, posting_contract=contract,
        )
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["\x15", "\x1b", "\x1b"])

    def test_wrong_and_duplicate_receipts_do_not_retire_another_acceptance(self):
        game, _client, executor = self.make()
        contract = PostingContract()
        executor.accepted = contract.accepted
        executor.observe_boundary(deadline=9999999999)
        before = self.posting_snapshot()
        contract.prepare(before, "6", "move", 7)
        result = executor.submit(Operation(7, "move", "6", executor.ready_board),
                                 deadline=9999999999)
        wrong = copy.deepcopy(result.board)
        wrong["_completed_operation_receipt"]["owner"] = "other"
        self.assertFalse(contract.settle(wrong))
        wrong_snapshot = self.posting_snapshot(
            messages=("Continue? [y/n]",),
            receipt=wrong["_completed_operation_receipt"],
        )
        self.assertFalse(contract.allow(wrong_snapshot, "n", "other"))
        self.assertTrue(contract.settle(result.board))
        self.assertFalse(contract.settle(result.board))

    def test_settlement_keeps_active_recall_business_guard(self):
        contract = PostingContract()
        before = self.posting_snapshot()
        contract.posted(before, "rha", "town:recall")
        active = self.posting_snapshot(recalling=True)
        self.assertFalse(contract.allow(active, "rha", "town:recall"))
        self.assertEqual(contract.last_incident["marker"],
                         "posting-contract:recall-already-active")

    def test_executor_settlement_keeps_active_recall_business_guard(self):
        game, _client, executor = self.make()
        contract = PostingContract()
        executor.accepted = contract.accepted
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2)
        before = self.posting_snapshot()
        sent, posted_line = _send_new_decision_key(
            port, "recall-first", "rha", None, set(), in_store=False,
            decision={"sequence": 7, "reason": "town:recall"},
            snapshot=before, posting_contract=contract,
        )
        self.assertTrue(sent)
        receipt = port.last_result.board["_completed_operation_receipt"]
        self.assertEqual(
            (receipt["sequence"], receipt["owner"],
             receipt["accepted_segments"][0]["keys"],
             receipt["terminal_kind"]),
            (7, "town:recall", "rha", "command"),
        )
        active = self.posting_snapshot(receipt=receipt, recalling=True)
        accepted_before = tuple(game.accepted)
        sent, _ = _send_new_decision_key(
            port, "recall-second", "rha", posted_line, set(), in_store=False,
            decision={"sequence": 8, "reason": "town:recall"},
            snapshot=active, posting_contract=contract,
        )
        self.assertFalse(sent)
        self.assertEqual(contract.last_incident["marker"],
                         "posting-contract:recall-already-active")
        self.assertEqual(tuple(game.accepted), accepted_before)
        self.assertEqual(game.accepted, ["rha"])

    def test_executor_settlement_discharges_identical_repost_transport_guard(self):
        game, _client, executor = self.make()
        contract = PostingContract()
        executor.accepted = contract.accepted
        executor.observe_boundary(deadline=9999999999)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2)
        before = self.posting_snapshot(messages=("before",))
        sent, posted_line = _send_new_decision_key(
            port, "recall-first", "rha", None, set(), in_store=False,
            decision={"sequence": 9, "reason": "town:recall"},
            snapshot=before, posting_contract=contract,
        )
        self.assertTrue(sent)
        receipt = port.last_result.board["_completed_operation_receipt"]
        settled = self.posting_snapshot(
            messages=("before", "later"), receipt=receipt, recalling=False,
        )
        sent, _ = _send_new_decision_key(
            port, "recall-reselection", "rha", posted_line, set(),
            in_store=False,
            decision={"sequence": 10, "reason": "town:recall"},
            snapshot=settled, posting_contract=contract,
        )
        self.assertTrue(sent)
        self.assertIsNone(contract.last_incident)
        self.assertEqual(game.accepted, ["rha", "rha"])


class Stage2aProducerRoutingPin(ProductionHarness):
    """P8: every former producer is fenced by executor ownership."""

    def test_p8_bypass_matrix_and_authorized_continuation_values(self):
        from hengbot.cli import SendResult, _ExecutorInputPort

        game, client, executor = self.make()
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        executor.active = Operation(7, "owner:identify", "r", {"turn": 1})
        executor.ready_board = None
        port = _ExecutorInputPort(
            executor, tunnel_macros_ready=True, request_budget=2
        )
        producers = {
            "policy:macro": "R10\r",
            "movement": "6",
            "store-home": "gayy",
            "recall": "ra",
            "periodic:save": "^S",
            "periodic:dump": "C",
            "periodic:knowledge": "~9\x1b",
            "floor-clear": "\x1b",
            "desync-clear": "l\x1b",
            "stall-recovery": "\x1b",
            "death-resync": "\x1bn\r",
            "esc-look-recovery": "\x1bl\x1b",
        }
        measured = {}
        for owner, keys in producers.items():
            result = port(keys, decision={"sequence": 8, "reason": owner})
            measured[owner] = result.value
        self.assertEqual(set(measured.values()), {SendResult.DESIGNED_WAIT.value})
        self.assertEqual(game.accepted, [])
        self.assertEqual(executor.active.owner, "owner:identify")

        # The owning operation may post only its prebound continuation.
        game2, _client2, executor2 = self.make()
        self.assertEqual(executor2.observe_boundary(deadline=9999999999).outcome, "ready")
        game2.screens = [prompt_screen("Read which scroll?"), command_screen(3)]
        operation = Operation(
            9, "owner:identify", "r", {"turn": 1},
            [Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "a", "Read which scroll?")],
        )
        result = executor2.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game2.accepted, ["r", "a"])
        self.assertEqual(result.operation.accepted_segments, ["r", "a"])


class Stage2bHistoricalIncidentPin(ProductionHarness):
    FIXTURE = Path(__file__).with_name("fixtures") / "input-barrier-stage2b-rec74-96.jsonl"

    def rows(self):
        return [json.loads(line) for line in self.FIXTURE.read_bytes().splitlines()]

    def test_p1_fixture_is_exact_physical_rec74_96_and_mid_operation_decisions_are_empty(self):
        actual = self.FIXTURE.read_bytes()
        self.assertEqual(len(actual.splitlines()), 23)
        self.assertEqual(hashlib.sha256(actual).hexdigest(),
                         "875a4eb1e3c9617eedbfa00dc2ace30d756917d9ecc68f345c1af6ce3ee3cb51")
        mid_operation = {75, 77, *range(78, 86), *range(86, 95)}
        barrier_decision_sources = {74, 76, 96}
        self.assertEqual(mid_operation & barrier_decision_sources, set())

    def test_p2_counterfactual_measured_values(self):
        rows = dict(enumerate(self.rows(), 74))
        self.assertEqual((rows[74]["player"]["gold"], rows[74]["floor"]["town_id"]),
                         (1580, 3))
        self.assertEqual((rows[76]["player"]["gold"], rows[76]["floor"]["town_id"]),
                         (1080, 0))
        self.assertEqual(rows[78]["player"]["gold"], 1080)
        self.assertEqual(len(rows[78]["messages"]), 2)
        self.assertEqual(len(rows[86]["messages"]), 2)
        identify = [item for item in rows[78]["inventory"] if "*鑑定*" in item["name"]]
        lights = [item for item in rows[86]["inventory"] if item.get("slot") == "g"]
        target = [item for item in rows[78]["inventory"] if item.get("slot") == "k"]
        self.assertEqual(identify, [])
        self.assertEqual((len(lights), lights[0]["count"]), (1, 1))
        self.assertTrue(target[0]["fully_known"])

    def test_p8_source_audit_only_executor_calls_transport_post(self):
        root = Path(__file__).parents[1]
        callers = []
        for path in (root / "src" / "hengbot").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == "post_keys":
                    callers.append(path.name)
        self.assertEqual(
            callers,
            ["control_client.py", "input_executor.py", "input_executor.py"],
        )

    def test_accepted_callback_once_per_accepted_segment_unknown_is_zero(self):
        accepted = []
        game, client, _executor = self.make()
        executor = OperationExecutor(
            client, drain=lambda: list(game.jsonl),
            accepted=lambda operation, segment: accepted.append((operation.owner, segment)),
        )
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(1, "policy", "6", {}), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(accepted, [("policy", "6")])

        game.faults = ["ack-loss"]
        executor.ready_board = game.state
        result = executor.submit(Operation(2, "unknown", "4", {}), deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(accepted, [("policy", "6")])


class ScreenClassifierTest(unittest.TestCase):
    def test_recorded_centered_character_dump_boundaries_and_coordinates(self):
        fixtures = Path(__file__).with_name("fixtures") / "live-screens"
        expected = (
            ("31-town-character-dump-stuck-20260915-1100.json",
             ScreenKind.FILE_NAME, "ファイル名: bot-test.txt", 21, 65),
            ("32-town-dump-after-enter-20260915.json", ScreenKind.CONFIRM,
             "現存するファイル C:\\hengband\\lib\\user\\bot-test.txt に上書きしますか? [y/n]",
             21, 65),
            ("33-town-dump-after-overwrite-y-20260915.json",
             ScreenKind.CHARACTER,
             "['c'で名前変更, 'f'でファイルへ書出, 'h'でモード変更, ESCで終了]",
             44, 67),
            ("34-town-dump-step0-20260915.json", ScreenKind.COMMAND,
             "layout-player-cursor", 45, 96),
        )
        for name, kind, feature, row, column in expected:
            with self.subTest(name=name):
                payload = json.loads((fixtures / name).read_text(encoding="utf-8"))
                match = classify_screen(payload["result"])
                self.assertEqual(
                    (match.kind, match.feature, match.row, match.column),
                    (kind, feature, row, column),
                )

        # The round-1 fake put the prompt at physical row zero even though the
        # same complete 211x67 character template proves a (65,21) offset.
        old_shape = json.loads((fixtures / expected[0][0]).read_text(
            encoding="utf-8"))["result"]
        old_shape["lines"][21] = ""
        old_shape["lines"][0] = "ファイル名: bot-test.txt"
        self.assertEqual(classify_screen(old_shape).kind, ScreenKind.CHARACTER)

    def test_real_live_screen_table_through_classifier_and_executor_boundary(self):
        fixture_dir = Path(__file__).with_name("fixtures") / "live-screens"
        expected = {
            "00-command-idle.json": ScreenKind.COMMAND,
            "01-after-ctrlF.json": ScreenKind.COMMAND,
            "02-knowledge-menu.json": ScreenKind.KNOWLEDGE,
            "03-after-knowledge-esc.json": ScreenKind.COMMAND,
            "04-character-screen.json": ScreenKind.CHARACTER,
            "05-after-character-esc.json": ScreenKind.COMMAND,
            "06-inventory.json": ScreenKind.UNKNOWN,
            "07-after-inventory-esc.json": ScreenKind.COMMAND,
            "08-look.json": ScreenKind.LOOK,
            "09-after-look-esc.json": ScreenKind.COMMAND,
            "10-rest-prompt.json": ScreenKind.QUANTITY,
            "11-after-rest-esc.json": ScreenKind.COMMAND,
            "12-read-item-prompt.json": ScreenKind.ITEM_SOURCE,
            "13-after-read-esc.json": ScreenKind.COMMAND,
            "14-before-home.json": ScreenKind.COMMAND,
            "15-auto-pickup-editor.json": ScreenKind.UNKNOWN,
            "16-after-home-esc.json": ScreenKind.UNKNOWN,
            "17-editor-menu-before-exit.json": ScreenKind.UNKNOWN,
            "18-after-editor-quit-nosave.json": ScreenKind.COMMAND,
            "24-town3-reward-pack-full-stop.json": ScreenKind.BUILDING,
        }

        class FixtureClient:
            observation_epoch = 0

            def __init__(self, payload):
                self.payload = payload

            def request(self, op, **_kwargs):
                return self.payload[op]["result"]

        for name, kind in expected.items():
            with self.subTest(name=name):
                payload = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
                screen, state = payload["screen"]["result"], payload["state"]["result"]
                self.assertEqual(classify_screen(screen, state).kind, kind)
                result = OperationExecutor(FixtureClient(payload)).observe_boundary(
                    deadline=9999999999)
                self.assertEqual(result.screen.kind, kind)
                self.assertEqual(result.outcome,
                                 "ready" if kind is ScreenKind.COMMAND else "stuck-prompt")

    def test_real_211x67_command_fixture_and_derived_negative_variants(self):
        fixture = Path(__file__).with_name("fixtures") / "live-screen-idle-town0-20260913.json"
        payload = json.loads(fixture.read_bytes())
        screen = payload["result"]
        self.assertEqual(classify_screen(screen).kind, ScreenKind.COMMAND)

        # Derived from the real fixture: active row-zero prompt overrides @.
        prompt = json.loads(fixture.read_bytes())["result"]
        prompt["lines"][0] = "Direction (Escape to cancel)?"
        self.assertEqual(classify_screen(prompt).kind, ScreenKind.DIRECTION)

        # Derived from the real fixture: row-zero message continuation overrides @.
        more = json.loads(fixture.read_bytes())["result"]
        more["lines"][0] = " " * (more["width"] - len("-more-")) + "-more-"
        self.assertEqual(classify_screen(more).kind, ScreenKind.MORE)

        # Derived from the real fixture: cursor off the rendered @ is unsupported.
        moved = json.loads(fixture.read_bytes())["result"]
        moved["cursor"]["x"] -= 1
        self.assertEqual(classify_screen(moved).kind, ScreenKind.UNKNOWN)

    def test_real_command_fixture_accepts_panel_independent_state_positions(self):
        fixture = Path(__file__).with_name("fixtures") / "live-screens" / "00-command-idle.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        screen = payload["screen"]["result"]
        state = payload["state"]["result"]
        # Derived variants model panel origin zero and a shifted/centered panel.
        # Both retain the measured hidden-cursor + rendered-@ evidence.
        for y, x in ((screen["cursor"]["y"] - 1, screen["cursor"]["x"] - 13),
                     (state["player"]["y"] + 17, state["player"]["x"] + 41)):
            with self.subTest(player=(y, x)):
                variant = copy.deepcopy(state)
                variant["player"]["y"], variant["player"]["x"] = y, x
                self.assertEqual(classify_screen(screen, variant).kind,
                                 ScreenKind.COMMAND)

    def test_store_inner_prompt_and_complete_building(self):
        screen = prompt_screen("Quantity (1-3): 1")
        screen["lines"][20:23] = ["You may: ", " ESC) Exit from Building.     p) Purchase an item.", ""]
        self.assertEqual(classify_screen(screen).kind, ScreenKind.QUANTITY)
        building = {"width": 80, "height": 24, "cursor": {"y": 23, "x": 0}, "lines": [""] * 24}
        building["lines"][2] = "  The Innkeeper"; building["lines"][19] = " a) Rest 10 gold"
        building["lines"][23] = " ESC) Exit building"
        self.assertEqual(classify_screen(building).kind, ScreenKind.BUILDING)

    def test_store_height_and_centered_width_follow_game_layout(self):
        lines = [" " * 211 for _ in range(67)]
        ox, menu_y = (211 - 80) // 2, 20 + min(40, 67 - 24)
        lines[menu_y] = " " * ox + "You may: "
        lines[menu_y + 1] = (" " * ox + " ESC) Exit from Building." + " " * 4
                             + "p) Purchase an item." + " " * 4 + "i/e) Inventry/Equipment list")
        self.assertEqual(classify_screen({"width": 211, "height": 67, "lines": lines,
                                         "cursor": {"visible": False, "x": 0, "y": 0}}).kind,
                         ScreenKind.STORE)

    def test_japanese_store_selector_and_look_prompt(self):
        self.assertEqual(classify_screen(prompt_screen("(商品:a-z, ESCで中断) どれにしますか?" )).kind,
                         ScreenKind.ITEM_SOURCE)
        look = prompt_screen("q,t,p,o,+,-,<dir>")
        self.assertEqual(classify_screen(look).kind, ScreenKind.LOOK)

    def test_exact_prompt_kinds_and_full_width_coordinate(self):
        cases = [("Read which scroll?", ScreenKind.ITEM_SOURCE),
                 ("Identify which item?", ScreenKind.ITEM_TARGET),
                 ("Direction (Escape to cancel)?", ScreenKind.DIRECTION),
                 ("Proceed? [Y/n]", ScreenKind.CONFIRM)]
        for text, kind in cases:
            with self.subTest(text=text): self.assertEqual(classify_screen(prompt_screen(text)).kind, kind)
        match = classify_screen(prompt_screen("漢字-more-"))
        self.assertEqual((match.kind, match.column), (ScreenKind.MORE, 4))

    def test_knowledge_more_and_unknown_overlay(self):
        knowledge = command_screen(); knowledge["lines"][3] = "Display current knowledge"
        knowledge["lines"][17] = "-more-"; knowledge["lines"][20] = "Command:"
        knowledge["lines"][21] = " ESC) Exit menu"
        self.assertEqual(classify_screen(knowledge).kind, ScreenKind.KNOWLEDGE)
        # cmd-draw.cpp:112 supplies the bilingual prompt; asking-player.cpp:
        # 182-188 prints it at row zero followed by the editable default.
        for row in ("ファイル名: hero.txt", "File name: hero.txt"):
            with self.subTest(row=row):
                self.assertEqual(classify_screen(prompt_screen(row)).kind,
                                 ScreenKind.FILE_NAME)

    def test_japanese_and_english_death_screens_are_player_death(self):
        class Client:
            observation_epoch = 0

            def __init__(self, screen):
                self.screen = screen

            def request(self, op, **_kwargs):
                return self.screen if op == "screen" else command_state(1)

        for literal in ("You die.", "You are broken.", "あなたは死にました。",
                        "後でスコアを登録するために待機しますか？"):
            with self.subTest(literal=literal):
                executor = OperationExecutor(Client(prompt_screen(literal)))
                result = executor.observe_boundary(deadline=9999999999)
                self.assertEqual(result.outcome, "player-death")
        overlay = command_screen(); overlay["lines"][0] = "Unsupported text:"
        overlay["cursor"]["visible"] = True
        self.assertEqual(classify_screen(overlay).kind, ScreenKind.UNKNOWN)
        overlay["lines"][10] = " menu overlay"
        self.assertEqual(classify_screen(overlay).kind, ScreenKind.UNKNOWN)

    def test_viewer_subtemplates(self):
        fixtures = Path(__file__).with_name("fixtures") / "live-screens"
        expected = [
            ("26-knowledge-viewer-stuck-20260915-0534.json",
             ScreenKind.FILE_VIEWER, "home-inventory", 0, 65),
            ("27-knowledge-menu-after-viewer-esc-20260915.json",
             ScreenKind.KNOWLEDGE, None, 24, 65),
            ("28-after-menu-esc-20260915.json",
             ScreenKind.STORE, "complete-store-menu", 60, 65),
        ]
        for name, kind, feature, row, column in expected:
            with self.subTest(name=name):
                screen = json.loads((fixtures / name).read_text(
                    encoding="utf-8"))["result"]
                match = classify_screen(screen)
                self.assertEqual((match.kind, match.row, match.column),
                                 (kind, row, column))
                if feature is not None:
                    self.assertEqual(match.feature, feature)

        # No source path renders logical column zero at physical column zero on
        # a 211-column term; the former fake is not an acceptable substitute.
        uncentered = command_screen()
        uncentered.update(width=211, height=67, lines=[""] * 67)
        uncentered["lines"][0] = "[Home Inventory, Line 1/2]"
        uncentered["lines"][-1] = "[Press ESC to exit.]"
        self.assertNotEqual(classify_screen(uncentered).kind,
                            ScreenKind.FILE_VIEWER)
        for marker, kind in [("-- more --", ScreenKind.IDENTIFY_VIEWER_PAGE),
                             ("[Press any key to continue]", ScreenKind.IDENTIFY_VIEWER_FINAL)]:
            view = command_screen(); view["lines"][1] = " " * 20 + "Item Attributes:"
            view["lines"][20] = " " * 15 + marker
            self.assertEqual(classify_screen(view).kind, kind)
        char = command_screen(); char["lines"][23] = "['c' to change name, 'f' to file, 'h' to change mode, or ESC]"
        self.assertEqual(classify_screen(char).kind, ScreenKind.CHARACTER)


class TcpBarrierPinTest(ProductionHarness):
    def _identify_incident_fixture(self):
        return json.loads((Path(__file__).with_name("fixtures") / "live-screens" /
                           "20-sweep-identify-item-target.json").read_text(
                               encoding="utf-8"))

    def _identify_failure_fixture(self):
        return json.loads((Path(__file__).with_name("fixtures") / "live-screens" /
                           "21-identify-prompt-absent.json").read_text(
                               encoding="utf-8"))

    def _produce_identify_chain(self, *, scroll=False):
        fixture = self._identify_incident_fixture()
        raw = copy.deepcopy(fixture["state"]["result"])
        if scroll:
            for item in raw["inventory"]:
                if item["slot"] in {"m", "n"}:
                    item["charges"] = 0
                if item["slot"] == "f":
                    item.update(sval=12, count=1, name="鑑定の巻物")
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        policy._decision_sequence = 649
        key = policy._identify_carried_item_key(
            snapshot, lambda item: item.slot == "g", "quest:sweep:identify"
        )
        return fixture, snapshot, policy, key, policy.peek_staged_prompt_chain()

    def _drive_identify_chain(self, *, scroll=False, target_screen=None):
        fixture, snapshot, policy, key, chain = self._produce_identify_chain(
            scroll=scroll
        )
        self.assertIsNotNone(chain)
        source_prompt = chain["gates"][0][1][0].rstrip()
        game = FaithfulHookGame()
        game.screens = [
            prompt_screen(source_prompt),
            target_screen or fixture["screen"]["result"],
            command_screen(2863066),
        ]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2)
        sent, _line, result = _send_prompt_gated_decision_key(
            port, "incident-seq649", key, None, set(), chain,
            shadow_client=_client, file=StringIO(), deadline=9999999999,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": 649, "reason": policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        return game, port, sent, result, key

    def test_japanese_staff_identify_incident_chain_owns_fixture_target_once(self):
        game, port, sent, result, key = self._drive_identify_chain()
        self.assertEqual(key, "umg")
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["u", "m", "g"])
        self.assertEqual(port.last_result.operation.accepted_segments,
                         ["u", "m", "g"])
        self.assertEqual(result["outcome"], "released")
        self.assertNotEqual(port.last_result.outcome, "stuck-prompt")

    def _drive_absent_target(self, message, *, mutate_final_state=None, owner=None):
        fixture = self._identify_failure_fixture()
        raw = copy.deepcopy(fixture["state"]["result"])
        raw["messages"] = []
        # These pins exercise missing-target continuation handling, not pack
        # overflow.  Make their captured Identify staff a non-splitting
        # single source; the full-pack stacked-source case is pinned in
        # test_policy_identification.
        next(item for item in raw["inventory"] if item["slot"] == "n")["count"] = 1
        final = copy.deepcopy(raw)
        if mutate_final_state is not None:
            mutate_final_state(final)
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        policy._decision_sequence = 656
        key = policy._identify_carried_item_key(
            snapshot, lambda item: item.slot == "i", "quest:sweep:identify"
        )
        self.assertEqual(key, "uni")
        chain = policy.peek_staged_prompt_chain()
        screen = copy.deepcopy(fixture["screen"]["result"])
        screen["lines"][0] = message + " " * max(0, screen["width"] - len(message))
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screens = [prompt_screen(chain["gates"][0][1][0].rstrip()), screen]
        game.states = [copy.deepcopy(raw), final]
        _game, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True,
                                  request_budget=2)
        sent, _line, result = _send_prompt_gated_decision_key(
            port, "incident-seq656", key, None, set(), chain,
            shadow_client=client, file=StringIO(), deadline=9999999999,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": 656, "reason": owner or policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        return game, executor, port, policy, raw, sent, result

    def test_device_failure_retires_real_incident_operation_and_allows_fresh_retry(self):
        game, executor, _port, policy, raw, sent, result = self._drive_absent_target(
            "杖をうまく使えなかった。"
        )
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["u", "n"])
        self.assertEqual(executor.active, None)
        self.assertEqual(result["outcome"], "released")
        self.assertEqual(executor.ready_board["turn"], 2863152)
        fresh = parse_snapshot(executor.ready_board, {})
        retry = policy._identify_carried_item_key(
            fresh, lambda item: item.slot == "i", "quest:sweep:identify"
        )
        self.assertEqual(retry, "uni")

    def test_empty_staff_retires_and_is_not_reselected_on_fresh_board(self):
        def empty_staff(raw):
            next(item for item in raw["inventory"] if item["slot"] == "n")["charges"] = 0

        game, executor, _port, policy, _raw, sent, _result = self._drive_absent_target(
            "この杖にはもう魔力が残っていない。",
            mutate_final_state=empty_staff
        )
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["u", "n"])
        fresh = parse_snapshot(executor.ready_board, {})
        next_key = policy._identify_carried_item_key(
            fresh, lambda item: item.slot == "i", "quest:sweep:identify"
        )
        self.assertFalse(next_key and next_key.startswith("un"))

    def test_rod_charging_retires_and_is_not_reselected_on_fresh_board(self):
        fixture = self._identify_failure_fixture()
        raw = copy.deepcopy(fixture["state"]["result"])
        for item in raw["inventory"]:
            if item["slot"] == "n":
                item["charges"] = 0
            if item["slot"] == "i":
                item.update(aware=True, known=True, sval=2, timeout=10,
                            name="鑑定のロッド")
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        self.assertIsNone(policy._find_identification_source(snapshot, full=False))

        game = FaithfulHookGame(); game.state = copy.deepcopy(raw)
        screen = copy.deepcopy(fixture["screen"]["result"])
        screen["lines"][0] = "このロッドはまだ魔力を充填している最中だ。"
        game.screens = [screen]; game.states = [copy.deepcopy(raw)]
        _game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        operation = Operation(657, "identify", "zi", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_TARGET}), "o",
                         "どのアイテムを鑑定しますか?")])
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual((result.outcome, game.accepted), ("completed", ["zi"]))
        self.assertIsNone(policy._find_identification_source(
            parse_snapshot(result.board, {}), full=False))

    def test_bilingual_source_proven_command_endings_drop_no_tail(self):
        cases = [
            ("u", "杖をうまく使えなかった。"),
            ("u", "You failed to use the staff properly."),
            ("a", "魔法棒をうまく使えなかった。"),
            ("a", "The wand has no charges left."),
            ("z", "うまくロッドを使えなかった。"),
            ("z", "The rod is still charging."),
            ("r", "目が見えない。"),
            ("r", "You have no light."),
        ]
        for command, message in cases:
            with self.subTest(command=command, message=message):
                game, _client, executor = self.make()
                screen = command_screen(2); screen["lines"][0] = message
                game.screens = [screen]
                executor.observe_boundary(deadline=9999999999)
                operation = Operation(658, "owned", command + "a",
                                      executor.ready_board, [
                    Continuation(frozenset({ScreenKind.ITEM_TARGET}), "b",
                                 "Identify which item?")])
                result = executor.submit(operation, deadline=9999999999)
                self.assertEqual((result.outcome, game.accepted),
                                 ("completed", [command + "a"]))

    def test_absent_prompt_without_causal_message_or_with_unrelated_message_stops(self):
        for message in ("", "ブラック・オークの骨がある。"):
            with self.subTest(message=message):
                game, executor, port, _policy, _raw, sent, result = \
                    self._drive_absent_target(message)
                self.assertEqual(sent.value, "terminal")
                self.assertEqual(game.accepted, ["u", "n"])
                self.assertEqual(executor.state.value, "terminal")
                self.assertEqual(result["outcome"], "dropped")
                self.assertIn("expected prompt absent", port.last_result.reason)

    def test_japanese_scroll_identify_chain_owns_fixture_target_once(self):
        game, port, sent, result, key = self._drive_identify_chain(scroll=True)
        self.assertEqual(key, "rfg")
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["r", "f", "g"])
        self.assertEqual(port.last_result.operation.accepted_segments,
                         ["r", "f", "g"])
        self.assertEqual(result["outcome"], "released")

    def test_japanese_identify_chain_rejects_different_target_question(self):
        game, port, sent, result, _key = self._drive_identify_chain(
            target_screen=prompt_screen("Identify which item?")
        )
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["u", "m"])
        self.assertEqual(port.last_result.outcome, "stuck-prompt")
        self.assertEqual(
            port.last_result.reason,
            "<stuck-prompt> owner=quest:sweep:identify phase=continuation "
            "transport=accepted request_id=6 reason=unowned item-target: "
            "Identify which item?",
        )
        self.assertEqual(result["outcome"], "dropped")

    def test_prompt_tables_match_captured_rows_and_contain_no_mojibake(self):
        fixture_dir = Path(__file__).with_name("fixtures") / "live-screens"
        fixtures = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in fixture_dir.glob("*.json")
        }
        row12 = fixtures["12-read-item-prompt"]["screen"]["result"]["lines"][0]
        row20 = fixtures["20-sweep-identify-item-target"]["screen"]["result"]["lines"][0]
        self.assertTrue(row12.rstrip().endswith(SOURCE_PROMPT["r"][0].rstrip()))
        self.assertTrue(row20.rstrip().endswith(IDENTIFY_ITEM_PROMPT[0].rstrip()))
        prompt_values = [value for pair in SOURCE_PROMPT.values() for value in pair]
        prompt_values.extend(IDENTIFY_ITEM_PROMPT)
        for value in prompt_values:
            with self.subTest(value=value):
                value.encode("utf-8").decode("utf-8")
                self.assertNotRegex(value, r"[縺繧荳螳蜿譁闕楜]")

        prompt_sources = [
            Path(__file__).resolve().parents[1] / "src" / "hengbot" / "cli.py",
            Path(__file__).resolve().parents[1] / "src" / "hengbot" /
            "input_executor.py",
        ]
        audited = []
        for path in prompt_sources:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            classify = next((node for node in tree.body
                             if isinstance(node, ast.FunctionDef) and
                             node.name == "classify_screen"), None)
            selected = set(ast.walk(classify)) if classify is not None else set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id == "Continuation":
                    if len(node.args) >= 3:
                        selected.update(ast.walk(node.args[2]))
                    for keyword in node.keywords:
                        if keyword.arg == "feature":
                            selected.update(ast.walk(keyword.value))
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names = [target.id for target in targets if isinstance(target, ast.Name)]
                    if any(any(word in name.upper() for word in
                               ("PROMPT", "QUESTION", "MESSAGE")) for name in names):
                        selected.update(ast.walk(node.value))
            for value in selected:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    audited.append((path, value.lineno, value.value))
        self.assertTrue(audited)
        for path, lineno, value in audited:
            with self.subTest(path=path.name, lineno=lineno, value=value):
                value.encode("utf-8").decode("utf-8")
                if any(ord(char) > 127 for char in value):
                    self.assertNotRegex(value, r"[縺繧繝荳螳蜿譁闕楜邵郢]")

        cited = {(path.name, value) for path, _line, value in audited}
        self.assertIn(("input_executor.py", "ファイル名: "), cited)
        self.assertIn(("cli.py", r"現存するファイル .+ に上書きしますか\? \[y/n\]"), cited)

    def _quest_entry_snapshot(self):
        start, entrance = Position(63, 98), Position(63, 99)
        player = SimpleNamespace(position=start)
        grids = {
            start: SimpleNamespace(position=start, has_quest_enter=False, quest_id=0),
            entrance: SimpleNamespace(
                position=entrance, has_quest_enter=True, quest_id=22
            ),
        }
        return Snapshot(player, grids, [], turn=2857339, floor_key=(0, 0, 0),
                        town_flag=True, town_id=3), entrance

    def _produce_quest_entry_move(self, snapshot, entrance):
        owner = SimpleNamespace(last_reason=None)
        owner._fixed_quest_entrance_positions = lambda *_args: {entrance}
        owner._quest_equipment_entry_allowed = lambda *_args: True
        owner._nearest_goal_step = lambda *_args: entrance
        owner._step_toward = lambda *_args: "6"
        return owner, QuestFloorNavigator.enter_from_town(owner, snapshot, 22)

    def test_live_quest_entry_fixture_is_owned_and_reaches_quest_floor_before_release(self):
        fixture = json.loads((Path(__file__).with_name("fixtures") / "live-screens" /
                              "19-quest-entry-confirm-yn.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["screen"]["result"]["cursor"],
                         {"visible": True, "x": 27, "y": 0})
        self.assertEqual(fixture["state"]["result"]["turn"], 2857339)
        snapshot, entrance = self._quest_entry_snapshot()
        owner, key = self._produce_quest_entry_move(snapshot, entrance)

        class QuestEntryGame(FaithfulHookGame):
            def _consume(self, *, pump_frontend=True):
                super()._consume(pump_frontend=pump_frontend)
                if self.accepted and self.accepted[-1] == "y":
                    self.state["floor"] = {"quest_id": 22, "level": 15}

        game = QuestEntryGame()
        game.screens = [fixture["screen"]["result"], command_screen(2857340)]
        _game, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        sent, _line = _send_new_decision_key(
            port, "incident-seq83", key, None, posted, in_store=False,
            decision={"sequence": 83, "reason": owner.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["6", "y"])
        self.assertEqual(port.last_result.operation.accepted_segments, ["6", "y"])
        self.assertEqual(port.last_result.board["floor"],
                         {"quest_id": 22, "level": 15})

    def test_quest_entry_move_does_not_own_an_unrelated_yes_no(self):
        snapshot, entrance = self._quest_entry_snapshot()
        owner, key = self._produce_quest_entry_move(snapshot, entrance)
        game, _client, executor = self.make()
        game.screens = [prompt_screen("Enter the arena? [y/n]")]
        executor.observe_boundary(deadline=9999999999)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "incident-seq83", key, None, set(), in_store=False,
            decision={"sequence": 83, "reason": owner.last_reason},
            snapshot=snapshot, posting_contract=PostingContract(),
        )
        self.assertFalse(sent)
        self.assertEqual(port.last_result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["6"])

    def test_p1_mid_operation_jsonl_is_ordered_observation_not_decision(self):
        game, client, _ = self.make()
        observed = []
        executor = OperationExecutor(
            client, drain=lambda: observed.extend(game.jsonl) or list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.jsonl.extend([
            {"turn": 1, "type": "character", "messages": ["same"]},
            {"turn": 1, "type": "look", "messages": ["same"]},
        ])
        result = executor.submit(Operation(1, "move", "6", executor.ready_board),
                                 deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual([row["type"] for row in observed[-3:-1]], ["character", "look"])
        self.assertEqual(result.board["messages"], ["same", "same"])

    def test_p4_state_is_base_messages_are_delta_and_prior_map_is_never_overlaid(self):
        state = {"turn": 76, "floor": {"town_id": 0}, "player": {"gold": 1080},
                 "inventory": [], "equipment": [], "grid_map": {"fresh": True},
                 "messages": ["history"]}
        records = [
            {"turn": 75, "type": "player_turn", "grid_map": {"stale": True},
             "messages": ["first", "first"]},
            {"turn": 78, "type": "player_turn", "messages": ["identify", "no scroll"]},
        ]
        board, ordered = compose_barrier_board(
            state, command_screen(), ScreenKind.COMMAND, records)
        self.assertEqual(board["grid_map"], {"fresh": True})
        self.assertEqual(board["messages"], ["first", "first", "identify", "no scroll"])
        self.assertEqual([row["turn"] for row in ordered], [75, 78])

    def test_p4_store_requires_latest_current_page_and_decreases_once(self):
        screen = command_screen()
        screen["lines"][20:23] = ["You may:", " ESC) Exit from Building. p) Purchase an item.", "Potion"]
        state = {"turn": 9, "floor": {"town_id": 0}, "player": {"gold": 80},
                 "inventory": [], "equipment": [], "grid_map": {"fresh": True}}
        stale = {**state, "turn": 8, "store": {"store_type": 1, "page": 0,
                                                "items": [{"name": "Potion", "count": 2}]}}
        current = {**state, "store": {"store_type": 1, "page": 0,
                                       "items": [{"name": "Potion", "count": 1}]}}
        board, _ = compose_barrier_board(state, screen, ScreenKind.STORE, [stale, current])
        self.assertEqual(board["store"]["items"][0]["count"], 1)
        wrong = {**current, "turn": 8}
        board, _ = compose_barrier_board(state, screen, ScreenKind.STORE, [wrong])
        self.assertIsNone(board)

    def test_fragmented_responses_more_and_flush_are_real_protocol_paths(self):
        game, _client, executor = self.make()
        game.fragments = [[1, 2, 3], [2, 1], [1], [3, 2], [1], [2, 2], [1]]
        game.recv_chunks = [1, 2, 1, 3] * 20
        game.screens = [prompt_screen("history-more-"), command_screen(3)]
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        result = executor.submit(Operation(2, "message", "x", executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["x", " "])

        game, _client, executor = self.make()
        executor.observe_boundary(deadline=9999999999)
        game.faults.append("flush")
        op = Operation(3, "identify", "rf", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_TARGET}), "k", "Identify which item?")])
        self.assertEqual(executor.submit(op, deadline=9999999999).outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["rf"])

    def test_ack_loss_partial_send_id_and_count_never_repost_or_wm(self):
        for fault in ("ack-loss", "partial-send", "wrong-id", "wrong-pushed"):
            with self.subTest(fault=fault):
                game, client, executor = self.make()
                self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
                game.faults.append(fault)
                result = executor.submit(Operation(3, "identify", "rfk", executor.ready_board), deadline=9999999999)
                self.assertEqual(result.outcome, "stuck-prompt")
                self.assertIn("acceptance-unknown", result.reason)
                self.assertEqual(game.accepted, ["rfk"])
                self.assertEqual(game.wm_posts, [])

    def test_barrier_and_owned_actual_answer_bytes(self):
        game, _client, executor = self.make(); game.screens = [prompt_screen("Identify which item?"), command_screen(3)]
        executor.observe_boundary(deadline=9999999999)
        op = Operation(4, "identify", "rf", executor.ready_board,
                       [Continuation(frozenset({ScreenKind.ITEM_TARGET}), "k", "Identify which item?")])
        result = executor.submit(op, deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["rf", "k"])
        self.assertEqual([x[1] for x in game.trace if x[0] == "issue"],
                         ["screen", "state", "keys", "screen", "state",
                          "keys", "screen", "state"])

    def test_enchant_launcher_owns_advertised_equipment_letter_and_toggles_only_inven(self):
        prompt = "Enchant which item?"
        for continuation_kind, screens, accepted in (
            (ScreenKind.ITEM_SOURCE,
             [prompt_screen("(Equip: a-c,'(',')', ESC) " + prompt),
              command_screen(3)], ["rj", "c"]),
            (ScreenKind.ITEM_TARGET,
             [prompt_screen("(Equip: a-c,'(',')', ESC) " + prompt),
              command_screen(3)], ["rj", "c"]),
            (ScreenKind.ITEM_SOURCE,
             [prompt_screen("(Inven: a-k,'(',')', / for Equip, ESC) " + prompt),
              prompt_screen("(Equip: a-c,'(',')', / for Inven, ESC) " + prompt),
              command_screen(3)], ["rj", "/", "c"]),
            (ScreenKind.ITEM_TARGET,
             [prompt_screen("(Inven: a-k,'(',')', / for Equip, ESC) " + prompt),
              prompt_screen("(Equip: a-c,'(',')', / for Inven, ESC) " + prompt),
              command_screen(3)], ["rj", "/", "c"]),
        ):
            with self.subTest(continuation_kind=continuation_kind,
                              accepted=accepted):
                game, _client, executor = self.make()
                game.screens = screens
                executor.observe_boundary(deadline=9999999999)
                operation = Operation(
                    112, "town:enchant-launcher-tohit", "rj",
                    executor.ready_board,
                    [Continuation(
                        frozenset({continuation_kind}), "c", prompt)],
                )
                result = executor.submit(operation, deadline=9999999999)
                self.assertEqual((result.outcome, game.accepted),
                                 ("completed", accepted))

        game, _client, executor = self.make()
        game.screens = [
            prompt_screen("(Equip: a-b,'(',')', ESC) " + prompt)]
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(
            113, "town:enchant-launcher-tohit", "rj", executor.ready_board,
            [Continuation(
                frozenset({ScreenKind.ITEM_SOURCE}), "c", prompt)],
        ), deadline=9999999999)
        self.assertEqual((result.outcome, game.accepted),
                         ("stuck-prompt", ["rj"]))

    def test_p5_source_then_target_ignore_intermediate_jsonl_and_release_once(self):
        game, _client, executor = self.make()
        source = "どの巻物を読みますか?"
        target = "どのアイテムを鑑定しますか?"
        game.screens = [prompt_screen(source), prompt_screen(target), command_screen(4)]
        executor.observe_boundary(deadline=9999999999)
        original = game.hook
        screen_replies = 0

        def write_before_each_screen(request):
            nonlocal screen_replies
            if request["op"] == "screen":
                screen_replies += 1
                game.jsonl.append({
                    "turn": game.state["turn"], "type": "player_turn",
                    "messages": [f"intermediate-{screen_replies}"],
                })
            return original(request)

        game.hook = write_before_each_screen
        operation = Operation(52, "identify", "r", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f", source),
            Continuation(frozenset({ScreenKind.ITEM_TARGET}), "k", target),
        ])
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", "f", "k"])
        self.assertEqual(result.operation.accepted_segments, ["r", "f", "k"])
        self.assertEqual(
            result.board["messages"],
            ["intermediate-1", "intermediate-2", "intermediate-3"],
        )

    def test_stage2f_full_identify_owns_viewer_pages_and_reconciles_absent_prompt(self):
        game, _client, executor = self.make()
        game.screens = [
            prompt_screen("Read which scroll?"),
            prompt_screen("Identify which item?"),
            source_derived_identify_viewer(),
            source_derived_identify_viewer(final=True),
            command_screen(6),
        ]
        executor.observe_boundary(deadline=9999999999)
        operation = Operation(70, "identify:full", "r", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f", "Read which scroll?"),
            Continuation(frozenset({ScreenKind.ITEM_TARGET}), "k", "Identify which item?"),
        ])
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", "f", "k", " ", "\x1b"])

        game, _client, executor = self.make()
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(
            71, "identify:full", "r", executor.ready_board,
            [Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f", "Read which scroll?")],
        ), deadline=9999999999)
        self.assertEqual((result.outcome, game.accepted), ("stuck-prompt", ["r"]))
        self.assertIn("expected prompt absent", result.reason)

        for effect in ("source-exhausted", "target-already-known"):
            with self.subTest(effect=effect):
                before = {
                    "turn": 1, "grid_map": {"runs": []},
                    "inventory": [
                        {"slot": "f", "count": 1, "fully_known": True,
                         "tval": 70, "sval": 13, "name": "*Identify*"},
                        {"slot": "k", "count": 1, "fully_known": False,
                         "tval": 22, "sval": 1, "name": "Axe"},
                    ],
                }
                after = copy.deepcopy(before); after["turn"] = 2
                if effect == "source-exhausted":
                    after["inventory"] = [after["inventory"][1]]
                else:
                    after["inventory"][1]["fully_known"] = True
                game, _client, executor = self.make()
                game.state = copy.deepcopy(before)
                game.screens = [prompt_screen("Read which scroll?"), command_screen(2)]
                game.states = [copy.deepcopy(before), after]
                executor.observe_boundary(deadline=9999999999)
                operation = Operation(73, "identify:full", "r", before, [
                    Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f",
                                 "Read which scroll?"),
                    Continuation(frozenset({ScreenKind.ITEM_TARGET}), "k",
                                 "Identify which item?"),
                ])
                result = executor.submit(operation, deadline=9999999999)
                self.assertEqual((result.outcome, game.accepted),
                                 ("completed", ["r", "f"]))

    def test_full_equipped_identify_owns_viewer_pages(self):
        game, _client, executor = self.make()
        game.screens = [
            source_derived_identify_viewer(),
            source_derived_identify_viewer(final=True),
            command_screen(6),
        ]
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(
            72, "identify:full-equipped", "r", executor.ready_board,
        ), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", " ", "\x1b"])

    def test_source_direction_confirm_quantity_and_building_answers(self):
        cases = [
            ("Read which scroll?", ScreenKind.ITEM_SOURCE, "r", "f"),
            ("Direction (Escape to cancel)?", ScreenKind.DIRECTION, "T", "6"),
            ("Destroy it? [Y/n]", ScreenKind.CONFIRM, "d", "y"),
            ("Quantity (1-9): 1", ScreenKind.QUANTITY, "p", "2\r"),
        ]
        building = {"width": 80, "height": 24, "cursor": {"y": 23, "x": 0}, "lines": [""] * 24}
        building["lines"][2] = " The Innkeeper"; building["lines"][19] = " a) Rest 10 gold"
        building["lines"][23] = " ESC) Exit building"
        cases.append((building, ScreenKind.BUILDING, "8", "a"))
        for prompt, kind, prefix, answer in cases:
            with self.subTest(kind=kind):
                game, _client, executor = self.make()
                game.screens = [prompt if isinstance(prompt, dict) else prompt_screen(prompt), command_screen(3)]
                executor.observe_boundary(deadline=9999999999)
                op = Operation(40, "owned", prefix, executor.ready_board,
                               [Continuation(frozenset({kind}), answer,
                                             classify_screen(prompt if isinstance(prompt, dict) else prompt_screen(prompt)).feature)])
                self.assertEqual(executor.submit(op, deadline=9999999999).outcome, "completed")
                self.assertEqual(game.accepted, [prefix, answer])

    def test_continuations_are_ordered_and_exact_question_bound(self):
        game, _client, executor = self.make()
        game.screens = [prompt_screen("Cancel recall? [y/n]")]
        executor.observe_boundary(deadline=9999999999)
        op = Operation(41, "recall", "r", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f", "Read which scroll?"),
            Continuation(frozenset({ScreenKind.CONFIRM}), "n", "Cancel recall? [y/n]"),
        ])
        result = executor.submit(op, deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, ["r"])

    def test_warning_confirm_is_refused_and_operation_completes(self):
        game, _client, executor = self.make()
        game.screens = [
            prompt_screen("Really want to go ahead? [y/n]"),
            command_screen(3),
        ]
        executor.observe_boundary(deadline=9999999999)

        result = executor.submit(
            Operation(4555, "explore", "6", executor.ready_board),
            deadline=9999999999,
        )

        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["6", "n"])

    def test_unrelated_question_and_knowledge_more_post_no_answer(self):
        for screen in (prompt_screen("Unrelated? [y/n]"), self._knowledge_screen()):
            with self.subTest(row0=screen["lines"][0]):
                game, _client, executor = self.make()
                game.screens = [screen]
                executor.observe_boundary(deadline=9999999999)
                op = Operation(42, "owned", "x", executor.ready_board, [
                    Continuation(frozenset({ScreenKind.CONFIRM}), "y", "Expected? [y/n]")])
                self.assertEqual(executor.submit(op, deadline=9999999999).outcome, "stuck-prompt")
                self.assertEqual(game.accepted, ["x"])

    @staticmethod
    def _knowledge_screen():
        value = command_screen()
        value["lines"][3] = "Display current knowledge"
        value["lines"][17] = "        -more-"
        value["lines"][20] = "Command: "
        value["lines"][21] = " ESC) Exit menu"
        return value

    def test_backpressure_reobserves_then_accepts_once(self):
        game, _client, executor = self.make(); executor.observe_boundary(deadline=9999999999)
        game.faults.append("backpressure")
        result = executor.submit(Operation(5, "move", "6", executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["6"])

    def test_backpressure_rebinds_current_item_prompt_and_fresh_state(self):
        game, _client, executor = self.make()
        game.screens = [prompt_screen("Read which scroll?"), command_screen(3)]
        executor.observe_boundary(deadline=9999999999)
        original = game.hook
        key_calls = 0

        def reject_continuation_once(request):
            nonlocal key_calls
            if request["op"] == "keys":
                key_calls += 1
                if key_calls == 2:
                    game.faults.insert(0, "backpressure")
            return original(request)

        game.hook = reject_continuation_once
        prompt = classify_screen(prompt_screen("Read which scroll?")).feature
        operation = Operation(51, "read", "r", executor.ready_board, [
            Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "f", prompt)])
        result = executor.submit(operation, deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["r", "f"])

    def test_state_timeout_is_terminal_not_wait(self):
        game, _client, executor = self.make(); executor.observe_boundary(deadline=9999999999)
        original = game.hook
        def lose_state(request):
            response, fault = original(request)
            return (None, fault) if request["op"] == "state" else (response, fault)
        game.hook = lose_state
        result = executor.submit(
            Operation(6, "wait", "5", executor.ready_board),
            deadline=__import__("time").monotonic() + 0.01,
        )
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("phase=state", result.reason)


class StorePurchaseOwnershipPin(ProductionHarness):
    def test_completed_home_curse_refusal_has_concrete_business_outcome(self):
        game = FaithfulHookGame()
        before = self.store_state(1)
        game.screen = store_screen()
        game.state = before
        game.jsonl = [copy.deepcopy(before)]
        game.screens = [store_screen("Hmmm, it seems to be cursed.")]
        game.states = [self.store_state(
            2, ["Hmmm, it seems to be cursed."]
        )]
        game, _client, executor = self.make(game)

        self.assertEqual(
            executor.observe_boundary(deadline=9999999999).outcome, "ready"
        )
        game.jsonl[:] = [copy.deepcopy(game.states[0])]
        result = executor.submit(Operation(
            26, "equipment-transaction:takeoff", "tA",
            copy.deepcopy(executor.ready_board),
        ), deadline=9999999999)

        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(result.operation.business_outcome, "refused")
        self.assertEqual(game.accepted, ["tA"])

    def test_refused_buy_drops_blind_tail_then_owned_escape(self):
        game, _client, executor = self.make()
        refusal = "\u305d\u3093\u306a\u306b\u30a2\u30a4\u30c6\u30e0\u3092\u6301\u3066\u306a\u3044\u3002"
        game.screens = [store_screen(), command_screen(3)]
        game.states = [self.store_state(2, [refusal]), {
            "turn": 3, "floor": {"dungeon_id": 0, "level": 0},
            "player": {"gold": 5483}, "inventory": [], "equipment": [],
            "grid_map": {"runs": []},
        }]
        executor.observe_boundary(deadline=9999999999)
        split = _store_buy_continuations("pq1\r\r\x1b", "shop:one-shot-buy")
        self.assertIsNotNone(split)
        prefix, continuations = split
        result = executor.submit(Operation(
            25, "shop:one-shot-buy", prefix, executor.ready_board,
            continuations,
        ), deadline=9999999999)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.operation.business_outcome,
                         "failed:purchase-refused")
        self.assertEqual(game.accepted, ["pq", "\x1b"])
        self.assertNotIn("1", "".join(game.accepted))
        self.assertNotIn("\r", "".join(game.accepted))


class WmFencePinTest(ProductionHarness):
    def test_wm_fence_partial_order_and_fresh_board(self):
        game, client, _ = self.make(); executor = OperationExecutor(client, wm_post=game.post_wm)
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(7, "move", "6", executor.ready_board, transport=Transport.WM), deadline=9999999999)
        self.assertEqual(result.outcome, "completed"); self.assertEqual(result.board["turn"], 2)
        self.assertIn(("post", "6", True), game.trace)
        trace = [(row[0], row[1]) for row in game.trace]
        trace = trace[trace.index(("post", "6")):]
        for left, right in [(('post','6'),('issue','info')), (('issue','info'),('reply','info')),
                            (('reply','info'),('issue','screen')), (('issue','screen'),('reply','screen'))]:
            self.assertLess(trace.index(left), trace.index(right))

    def test_without_info_fence_screen_is_old(self):
        game, client, _ = self.make()
        old_turn = game.screen["turn"]
        game.post_wm("6")
        observed = client.request("screen", deadline=9999999999, term=0, attrs=False)
        self.assertEqual(observed["turn"], old_turn)

    def test_partial_post_never_reposts_and_wm_only_refuses(self):
        game, client, _ = self.make(); calls = []
        def partial(char): calls.append(char); return len(calls) < 2
        executor = OperationExecutor(client, wm_post=partial); executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(8, "macro", "ab", executor.ready_board, transport=Transport.WM), deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt"); self.assertEqual(calls, ["a", "b"])
        refused = OperationExecutor(None, wm_post=game.post_wm).observe_boundary(deadline=9999999999)
        self.assertEqual(refused.outcome, "stuck-prompt"); self.assertEqual(game.wm_posts, [])


if __name__ == "__main__":
    unittest.main()
