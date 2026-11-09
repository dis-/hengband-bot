"""Shared scaffolding for recorded replays and executor pins.

Moved verbatim out of the test modules that hosted it (maintainability review
1109, 段3); those modules re-export these names for backward compatibility.

- Recorded-replay policy (was tests/test_esp_threat_rest_recorded.py):
  ``GAME_ROOT``, ``EDIT`` and ``_policy`` -- the fully loaded production
  policy with Home history/disposal files and the frozen esp-threat-rest
  calibration in a temporary directory.
- Source-derived executor fake (was tests/test_input_executor.py):
  ``command_screen``, ``prompt_screen``, ``store_screen``,
  ``source_derived_identify_viewer``, ``FaithfulHookGame`` and the
  ``ProductionHarness`` base (no tests of its own).
- Dungeon-1031 recorded harness (was tests/test_dungeon_1031_recorded.py):
  ``READ_PROMPT``, ``QUAFF_PROMPT``, ``skill``, ``decide`` and the
  ``RecordedHarness`` base (no tests of its own).

The harness bases are ``unittest.TestCase`` subclasses.  Bind them through
the module (``from tests.support import recorded`` then
``class X(recorded.ProductionHarness)``), not by name: a test module that
binds a foreign TestCase is refused by tests/test_policy_structure.py.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import json
import shutil
import time
import unittest
from pathlib import Path

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.control_client import ControlClient
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.input_executor import OperationExecutor
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import (
    load_damaging_terrain_elements, load_damaging_terrain_ids, load_deep_damaging_terrain_ids)
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


TESTS = Path(__file__).resolve().parents[1]
FIXTURES = TESTS / "fixtures"

# ---------------------------------------------------------------------------
# Recorded-replay policy (was tests/test_esp_threat_rest_recorded.py)
# ---------------------------------------------------------------------------

GAME_ROOT = Path("C:/hengband")
EDIT = GAME_ROOT / "lib" / "edit"
ESP_THREAT_REST_CALIBRATION = FIXTURES / "esp-threat-rest-20260921.character-calibration.json"


def _policy(directory: Path, monrace) -> HengbotPolicy:
    town_maps = {}
    for town_index in range(1, 6):
        path = find_town_map(town_index, GAME_ROOT)
        if path is not None:
            town_maps[town_index - 1] = parse_town_map(path)
    policy = HengbotPolicy(
        town_map=town_maps.get(0),
        town_maps=town_maps,
        wilderness_map=load_wilderness_map(find_wilderness_definition(GAME_ROOT)),
        dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"),
        monrace_knowledge=monrace,
        damaging_terrain_ids=load_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc"),
        damaging_terrain_elements=load_damaging_terrain_elements(EDIT / "TerrainDefinitions.jsonc"),
        deep_damaging_terrain_ids=load_deep_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc"),
        quest_knowledge=load_quest_knowledge(
            find_quest_definitions(GAME_ROOT / "bot-client" / "state.jsonl")
        ),
        quest_strategies=load_quest_strategies(
            TESTS.parent / "strategy" / "quests"
        ),
        home_disposal_state=HomeDisposalState(
            directory / "home-withdraw-history.jsonc",
            directory / "home-disposal-decisions.jsonc",
            directory / "home-disposal-queue.json",
            directory / "events.jsonl",
        ),
        baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
    )
    calibration = directory / "character-calibration.json"
    shutil.copyfile(ESP_THREAT_REST_CALIBRATION, calibration)
    policy._character_calibration_path = calibration
    return policy


# ---------------------------------------------------------------------------
# Source-derived executor fake (was tests/test_input_executor.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dungeon-1031 recorded harness (was tests/test_dungeon_1031_recorded.py)
# ---------------------------------------------------------------------------

DUNGEON_1031_FIXTURE = FIXTURES / "dungeon-1031.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
QUAFF_PROMPT = "どの薬を飲みますか? "


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def decide(policy, raw):
    skill(policy, raw)
    return str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))


class RecordedHarness(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(DUNGEON_1031_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def boards(self, name):
        return [copy.deepcopy(board) for board in self.cases[name]["boards"]]

    def post(self, policy, raw, key, screens, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        return game.accepted

    @staticmethod
    def later(raw, turns=10):
        return dict(copy.deepcopy(raw), turn=raw["turn"] + turns, messages=[])
