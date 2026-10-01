"""Live sender pin: recorded chooser after p; later gates are independent captures.

Quantity/price captures are protocol samples, not outcomes of this incident.
The constructed command/store boards only establish and close the harness.
"""
import hashlib
import json
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_new_decision_key, SendResult
from hengbot.input_executor import ScreenKind, classify_screen
from tests import test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURES = Path(__file__).parent / "fixtures" / "live-screens"


class StoreWhich2RecordedPin(executor_harness.ProductionHarness):
    def test_live_metadata_and_recorded_screen_after_p(self):
        data = (FIXTURES / "storewhich2-20261001-2130.json").read_bytes()
        self.assertEqual(hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
                         "7890e31e5cf0453542d89da02cb9063cc07237c4fc85e632a88370a68e4c47d8")
        chooser = json.loads(data)
        self.assertEqual((chooser["width"], chooser["height"]), (213, 68))
        self.assertEqual(classify_screen(chooser).kind, ScreenKind.ITEM_SOURCE)
        initial = json.loads((FIXTURES / "live-screen-cap-08-alchemist-buy-confirm.json").read_text(encoding="utf8"))["screen"]["result"]
        self.assertEqual(classify_screen(initial).kind, ScreenKind.STORE)
        game = FaithfulHookGame()
        game.screen = initial
        game.state = self.store_state(1)
        game.jsonl = [game.state]
        game.screens = [chooser] + [json.loads((FIXTURES / name).read_text(encoding="utf8"))["screen"]["result"] for name in (
            "live-screen-cap-06-alchemist-buy-select-detection.json",
            "live-screen-cap-07-alchemist-buy-quantity-enter.json")]
        game.screens += [initial, command_screen(2)]
        game.states = [self.store_state(1)] * 4 + [{"turn": 2, "grid_map": {"runs": []}}]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        decision = dict(sequence=18, turn=1, reason="shop:one-shot-buy",
                        key="pk4\r\r\x1b", prompt_owner_handoff=None)
        sent, _ = _send_new_decision_key(port, "storewhich2", decision["key"], None,
                                      set(), in_store=True, decision=decision)
        self.assertEqual(game.accepted, ["p", "k", "4\r", "\r", "\x1b"])
        self.assertEqual(sent, SendResult.SENT)
        self.assertEqual(port.last_result.outcome, "completed")
