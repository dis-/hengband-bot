"""Recorded chooser pin; later cap-06/07 prompts are independent protocol samples.
They are not claimed as outcomes of the incident purchase (R4).
"""
import hashlib
import json
from pathlib import Path
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key, SendResult
from hengbot.input_executor import ScreenKind, classify_screen
from tests import test_input_executor as executor_harness
from tests.test_input_executor import store_screen, command_screen

FIXTURES = Path(__file__).parent / "fixtures" / "live-screens"

class StoreWhichRecordedPin(executor_harness.ProductionHarness):
    def test_recorded_chooser_through_production_sender(self):
        data = (FIXTURES / "storewhich-20261001-2118.json").read_bytes()
        self.assertEqual(hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
                         "81c7c3c8b56011d73b2e247f9a36e514676f67baef71e8d833c5c6f444e567ff")
        recorded = json.loads(data)
        from tests.test_input_executor import FaithfulHookGame
        game = FaithfulHookGame()
        game.screen = store_screen()
        game.state = self.store_state(1)
        game.jsonl = [game.state]
        game.screens = [recorded] + [json.loads((FIXTURES / name).read_text(encoding="utf8"))["screen"]["result"] for name in (
            "live-screen-cap-06-alchemist-buy-select-detection.json",
            "live-screen-cap-07-alchemist-buy-quantity-enter.json")]
        game.screens += [store_screen(), command_screen(2)]
        game.states = [self.store_state(1)] * 4 + [{"turn": 2, "grid_map": {"runs": []}}]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _ = _send_new_decision_key(port, "storewhich", "pk4\r\r\x1b", None, set(),
            in_store=True, decision={"sequence": 5170, "reason": "shop:one-shot-buy"})
        self.assertEqual(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["pk", "k", "4\r", "\r", "\x1b"])
        self.assertEqual(port.last_result.outcome, "completed")
        match = classify_screen(recorded)
        self.assertEqual((match.kind, match.column), (ScreenKind.ITEM_SOURCE, 66))


    def test_declared_bilingual_offset_variants(self):
        # Derived from the recorded chooser: replace only row zero's prompt
        # and indentation; preserve the screen and all store/footer rows.
        recorded = json.loads((FIXTURES / "storewhich-20261001-2118.json").read_bytes())
        for prompt in ("(Items a-Z, ESC to exit) Which item?",
                       "(\u5546\u54c1:a-Z, ESC\u3067\u4e2d\u65ad) Which item?",
                       "(\u30a2\u30a4\u30c6\u30e0:a-Z, ESC\u3067\u4e2d\u65ad) Which item?"):
            for offset in (0, 15, 66):
                recorded["lines"][0] = " " * offset + prompt
                match = classify_screen(recorded)
                self.assertEqual((match.kind, match.feature, match.column),
                                 (ScreenKind.ITEM_SOURCE, prompt, offset))
        recorded["lines"][0] = " " * 66 + "Unknown store question?"
        self.assertEqual(classify_screen(recorded).kind, ScreenKind.UNKNOWN)
