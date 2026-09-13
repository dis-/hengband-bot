"""Input causal-barrier pins using a source-derived one-request-per-hook fake."""

import json
from pathlib import Path
import ast
import hashlib
import unittest

from hengbot.control_client import ControlClient, KeyPostStatus
from hengbot.input_executor import (
    Continuation, Operation, OperationExecutor, ScreenKind, Transport,
    classify_screen, compose_barrier_board,
)


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


class _FakeSocket:
    def __init__(self, game):
        self.game, self.output = game, bytearray()
        self.closed = False

    def settimeout(self, _value):
        pass

    def close(self):
        self.closed = True

    def sendall(self, payload):
        request = json.loads(payload)
        response, fault = self.game.hook(request)
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
        self.screens = []
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
        self.state = {"turn": self.state["turn"] + 1, "grid_map": {"runs": []}}
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
        source = Path(__file__).parents[1] / "jsonlog/incident-20260913-town-pingpong-gold-burn/bot-state-fixed.jsonl"
        expected = b"".join(source.read_bytes().splitlines(keepends=True)[73:96])
        actual = self.FIXTURE.read_bytes()
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual.splitlines()), 23)
        self.assertEqual(hashlib.sha256(actual).hexdigest(),
                         hashlib.sha256(expected).hexdigest())
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
            "15-home-store-screen.json": ScreenKind.UNKNOWN,
            "16-after-home-esc.json": ScreenKind.UNKNOWN,
            "17-editor-menu-before-exit.json": ScreenKind.UNKNOWN,
            "18-after-editor-quit-nosave.json": ScreenKind.COMMAND,
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

    def test_real_command_fixture_rejects_mismatched_fresh_state_position(self):
        fixture = Path(__file__).with_name("fixtures") / "live-screens" / "00-command-idle.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        state = payload["state"]["result"]
        state["player"]["x"] += 1
        self.assertEqual(classify_screen(payload["screen"]["result"], state).kind,
                         ScreenKind.UNKNOWN)

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
        overlay = command_screen(); overlay["lines"][0] = "Unsupported text:"
        overlay["cursor"]["visible"] = True
        self.assertEqual(classify_screen(overlay).kind, ScreenKind.UNKNOWN)
        overlay["lines"][10] = " menu overlay"
        self.assertEqual(classify_screen(overlay).kind, ScreenKind.UNKNOWN)

    def test_viewer_subtemplates(self):
        file_view = command_screen(); file_view["lines"][0] = "[Home Inventory, Line 1/2]"
        file_view["lines"][-1] = "[Press ESC to exit.]"
        self.assertEqual(classify_screen(file_view).kind, ScreenKind.FILE_VIEWER)
        for marker, kind in [("-- more --", ScreenKind.IDENTIFY_VIEWER_PAGE),
                             ("[Press any key to continue]", ScreenKind.IDENTIFY_VIEWER_FINAL)]:
            view = command_screen(); view["lines"][1] = " " * 20 + "Item Attributes:"
            view["lines"][20] = " " * 15 + marker
            self.assertEqual(classify_screen(view).kind, kind)
        char = command_screen(); char["lines"][23] = "['c' to change name, 'f' to file, 'h' to change mode, or ESC]"
        self.assertEqual(classify_screen(char).kind, ScreenKind.CHARACTER)


class TcpBarrierPinTest(ProductionHarness):
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
        result = executor.submit(Operation(6, "wait", "5", executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("phase=state", result.reason)


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
