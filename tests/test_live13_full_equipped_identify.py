"""Live13 pins stop at the first divergent target answer (R4)."""
import tests  # noqa: F401
import copy
import json
import time
from pathlib import Path

from tests.test_input_executor import ProductionHarness, FaithfulHookGame
from hengbot.input_executor import Continuation, Operation, ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT

FIXTURES = Path(__file__).with_name("fixtures") / "live-screens"


class StopAfterTargetGame(FaithfulHookGame):
    # No board recorded after the NEW target answer: do not invent its effect.
    def hook(self, request):
        if request["op"] == "screen" and self.accepted == ["rf", "a"]:
            return {"id": request["id"], "ok": False, "error": "no post-divergence capture"}, None
        return super().hook(request)


class Live13FullEquippedPin(ProductionHarness):
    def load(self):
        screen = json.loads((FIXTURES / "live13-star-identify-equipment-prompt.json").read_text(encoding="utf-8"))
        state = json.loads((FIXTURES / "live13-before-identify-state.json").read_text(encoding="utf-8"))
        return screen, state

    def test_recorded_town_surface_composer_and_owned_target(self):
        screen, state = self.load()
        snapshot = parse_snapshot(state, {})
        self.assertEqual((snapshot.in_town, snapshot.store), (True, None))
        policy = ConservativePolicy()
        policy._decision_sequence = 87
        key = policy._town_equipped_identification_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))
        chain = policy.peek_staged_prompt_chain()
        self.assertEqual((chain["key"], chain["sequence"], chain["gates"][1]),
                         ("rfa", 87, (2, IDENTIFY_ITEM_PROMPT)))
        self.assertEqual([(item.slot, item.tval, item.sval) for item in snapshot.inventory if item.slot == "f"],
                         [("f", 70, 13)])
        self.assertEqual(classify_screen(screen).kind, ScreenKind.ITEM_TARGET)
        game = StopAfterTargetGame()
        game.state = copy.deepcopy(state)
        game.screens = [screen]
        game.states = [copy.deepcopy(state)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        # rf reached the captured chooser live. Pin only the FIRST new answer.
        result = executor.submit(Operation(
            87, policy.last_reason, "rf", state,
            [Continuation(frozenset({ScreenKind.ITEM_TARGET}), key[2], IDENTIFY_ITEM_PROMPT[0])],
        ), deadline=time.monotonic() + 0.2)
        self.assertEqual(game.accepted, ["rf", "a"])
        self.assertEqual((result.outcome, result.screen), ("stuck-prompt", None))
        self.assertEqual(result.operation.continuations, [])
