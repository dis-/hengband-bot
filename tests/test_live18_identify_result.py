"""Live18 recorded result, plus a declared single-row derived page variant."""
import copy
import json
import time

from hengbot.cli import _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.input_executor import ScreenKind, classify_screen, _cell_width
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
import tests.test_input_executor as harness
from tests.test_live17_identify_observation import FIXTURES


class Live18IdentifyResultPin(harness.ProductionHarness):
    def test_recorded_result_through_live_sender(self):
        recorded = json.loads((FIXTURES / "live18-full-identify-result.json").read_text(encoding="utf-8"))
        for page_first in (False, True):
            with self.subTest(derived_page_first=page_first):
                state = json.loads((FIXTURES / "live17-before-identify-state.json").read_text(encoding="utf-8"))
                game = harness.FaithfulHookGame()
                game.state = copy.deepcopy(state)
                game.screens = [json.loads((FIXTURES / name).read_text(encoding="utf-8")) for name in (
                    "live15-read-scroll-prompt.json", "live13-star-identify-equipment-prompt.json")]
                if page_first:
                    # Derived only by replacing the recorded final-marker row.
                    page = copy.deepcopy(recorded)
                    row = recorded["lines"][10]
                    marker = "[何かキーを押すとゲームに戻ります]"
                    self.assertEqual(_cell_width(row[:row.index(marker)]), 15)
                    page["lines"][10] = row[:row.index(marker)] + "-- 続く --"
                    game.screens.append(page)
                game.screens.extend([recorded, harness.command_screen(state["turn"] + 1)])
                game.states = [copy.deepcopy(state) for _ in game.screens]
                _, client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
                policy = ConservativePolicy()
                snapshot = parse_snapshot(state, {})
                key = policy._town_equipped_identification_key(snapshot)
                self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))
                port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
                _, _, _, result = _send_decision_key_with_prompt_chain(
                    port, "recorded-live18", key, None, set(), policy=policy,
                    shadow_client=client, file=None, deadline=time.monotonic() + 1,
                    poll_interval=0, prompt_japanese=True,
                    decision=dict(sequence=1, turn=snapshot.turn, reason=policy.last_reason,
                                  key=key, prompt_owner_handoff=policy.prompt_owner_handoff),
                    snapshot=snapshot, posting_contract=None, in_store=False)
                self.assertEqual(game.accepted, ["r", "f", "a"] + ([" "] if page_first else []) + ["\x1b"])
                self.assertEqual(port.last_result.outcome, "completed")
                self.assertEqual(result["outcome"], "released")
                self.assertEqual(classify_screen(recorded).kind, ScreenKind.IDENTIFY_VIEWER_FINAL)
                if page_first:
                    self.assertEqual(classify_screen(page).kind, ScreenKind.IDENTIFY_VIEWER_PAGE)

    def test_display_column_literals_and_wide_boundary(self):
        for heading in ("Item Attributes:", "アイテムの能力:"):
            for marker, kind in (("-- more --", ScreenKind.IDENTIFY_VIEWER_PAGE),
                                 ("-- 続く --", ScreenKind.IDENTIFY_VIEWER_PAGE),
                                 ("[Press any key to continue]", ScreenKind.IDENTIFY_VIEWER_FINAL),
                                 ("[何かキーを押すとゲームに戻ります]", ScreenKind.IDENTIFY_VIEWER_FINAL)):
                screen = harness.command_screen()
                screen["lines"][1] = "種族" + " " * 16 + heading
                screen["lines"][10] = "能力値" + " " * 9 + marker
                self.assertEqual(classify_screen(screen).kind, kind)
                screen["lines"][1] = "種族" + " " * 15 + heading
                self.assertEqual(classify_screen(screen).kind, ScreenKind.UNKNOWN)
        screen["lines"][1] = " " * 19 + "界" + "Item Attributes:"
        self.assertEqual(classify_screen(screen).kind, ScreenKind.UNKNOWN)
