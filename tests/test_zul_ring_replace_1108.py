"""The Zul trip's Ring of Levitation worn over two filled ring slots (n1-c life-160).

Recorded (tests/fixtures/zul-ring-replace-20261107.json.gz, from n1-c life-160
captures/20261107-185316-stuck-prompt-town-zul-wear-levitation): ``board`` is the
Outpost board of decision 17324 (turn 1455516, the Ring of Levitation just taken
out of the Home into slot m, Ring of Resist Confusion and Ring of Accuracy (+10)
worn), and ``replace_ring_screen`` is the game's chooser the bot stopped on.  With
both ring slots filled do_cmd_wield (cmd-item/cmd-equipment.cpp) asks
「どちらの指輪と取り替えますか?」 / "Replace which ring? " instead of the hand
question; the bot only knew the hand question, so the ')' answer was never
released and the stuck-prompt guard retired the character.

DECLARED CONSTRUCTED: the observed mutation signature (no character sheet in the
capture), the policy construction (the production one of the Q2 tower tests:
every town map, the lib/edit knowledge), the empty Home page, the wield chooser
screen (recorded cap-15, another character's 「どれを装備しますか?」) and the
command screen the game returns to after the wield.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import time
from pathlib import Path

from hengbot import zul_trip
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import parse_snapshot
from tests import test_input_executor as executor_harness
from tests import test_q2_tower_recharge_recorded as q2_town
from tests.test_classA_observed_input import recorded
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen
from tests.test_zul_trip import MUTATION, wilderness

FIXTURE = Path(__file__).parent / "fixtures" / "zul-ring-replace-20261107.json.gz"


def capture():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class ZulRingReplaceRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        q2_town.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)
        cls.capture = capture()

    def decide(self):
        raw = copy.deepcopy(self.capture["board"])
        policy = q2_town.Q2TowerRechargeRecordedTest.policy(self, raw)
        policy._wilderness_map = wilderness()
        policy._mutation_signature = (MUTATION,)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monraces))
        return key, policy.last_reason

    def drive(self, key, owner, screens):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(self.capture["board"])
        game.screen = command_screen(game.state["turn"])
        game.screens = copy.deepcopy(screens)
        game.states = [copy.deepcopy(game.state) for _screen in screens]
        _, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        _send_new_decision_key(port, "zul-ring-replace", key, None, set(),
                               in_store=False, decision={"sequence": 17324, "reason": owner},
                               snapshot=parse_snapshot(game.state, {}), posting_contract=None)
        return game, port.last_result

    def test_recorded_board_wields_the_ring_over_both_filled_slots(self):
        board = parse_snapshot(copy.deepcopy(self.capture["board"]), self.monraces)
        self.assertEqual({item.slot for item in board.equipment} & set(zul_trip.RING_SLOTS),
                         set(zul_trip.RING_SLOTS))
        key, reason = self.decide()
        # The live decision 17324: wield pack slot m, then ')' at the slot chooser.
        self.assertEqual((key, reason), ("wm)", zul_trip.WEAR_REASON))
        game, result = self.drive(key, reason, [
            recorded("live-screen-cap-15-home-wield-w.json"),
            self.capture["replace_ring_screen"],
            command_screen(game_turn(self.capture) + 10)])
        self.assertEqual(game.accepted, ["w", "m", ")"])
        self.assertEqual(result.outcome, "completed")

    def test_recorded_replace_ring_chooser_is_the_wield_slot_target(self):
        match = classify_screen(self.capture["replace_ring_screen"])
        self.assertIs(match.kind, ScreenKind.ITEM_TARGET)
        # The English build prints the same chooser as "Replace which ring? ".
        english = prompt_screen("(Equip: d-e,'(',')', ESC) Replace which ring? ")
        self.assertIs(classify_screen(english).kind, ScreenKind.ITEM_TARGET)

    def test_the_ring_answer_never_goes_to_another_chooser(self):
        # Constructed protocol control: a quaff chooser where the slot chooser
        # should be keeps the ')' unposted (the composed answer is not blind).
        game, result = self.drive("wm)", zul_trip.WEAR_REASON, [
            recorded("live-screen-cap-15-home-wield-w.json"),
            recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["w", "m"])
        self.assertEqual(result.outcome, "stuck-prompt")


def game_turn(value):
    return value["board"]["turn"]


if __name__ == "__main__":
    import unittest
    unittest.main()
