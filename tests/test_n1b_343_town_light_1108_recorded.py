"""n1-b life-343 (2026-11-08 04:54, Magic-Eater Lv9): the lantern out in town.

The last flask was poured on the floor at 04:51:28 (「もう油つぼを持っていない」), the
lantern went out in town at 04:54:20 (「明かりが消えてしまった！」), light radius 0,
50,284 gold.  The Magic-Eater staff sequence walked to the Magic shop, stepped out on
its lit entrance (27,76) and sent its inn travel ``\\x1b`n9999999999999.``
(me-staff:return-to-shop / travel-morivant); the game refused the next step in the
dark street (travel-execution.cpp decide_travel_step_dir: blind or no_lite
「目が見えない！」), the town progress invariant walked back to the shop and the
travel went out again, until town:blocked:owner-retired-burst.

Now the light out in town is restored ahead of the class sequences (refuel from the
pack, a carried torch, else the General Store's oil), and no native travel is sent
while the player's own light is out.
Fixture: tests/extract_n1b_343_345_1108_fixtures.py (light.tar.xz: the 04:54:51 restart
checkpoint in Angwil and its journal rows 0..12).
DECLARED CONSTRUCTED: the General Store page (no page of Angwil's General Store was
observed this stay; its flask row as articles-on-sale.cpp stocks it, price
assumed) and the board after its purchase (the flasks in the pack).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import town_travel
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_GENERAL, parse_snapshot
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-343-345-1108"
READ_POWERS_ROW = 4   # the first errand decision of the restart
TRAVEL_ROW = 11       # the staff sequence's inn travel from the lit entrance
TVAL_FLASK, SV_FLASK_OIL = 77, 0
OIL_ROW = {
    "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 20,
    "damage_dice": {"num": 2, "sides": 6}, "fully_known": True, "inscription": "",
    "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
    "is_ego": False, "is_equipment": False, "known": True, "known_flags": [],
    "letter": "a", "name": "油つぼ", "price": 4, "pval": 7500, "sval": SV_FLASK_OIL,
    "to_a": 0, "to_d": 0, "to_h": 0, "tval": TVAL_FLASK, "weight": 10,
}


class TownLightRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self):
        visit = self.scratch / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / "light.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay(self, policy, recorded, steps, rows, *, strict=True):
        for index in range(rows):
            board = steps[index][1]()
            chosen = policy.choose_key(board)
            if strict:
                self.assertEqual((chosen, policy.last_reason),
                                 (recorded[index]["key"], recorded[index]["reason"]), f"row {index}")
            policy.confirm_key_posted(recorded[index]["key"])

    @staticmethod
    def raw(row):
        return json.loads(row["line"] or row["inputs"][-1])

    def assert_posts(self, policy, raw, board, key, *, in_store=False):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=in_store,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_the_light_out_sends_the_board_to_the_general_store_first(self):
        policy, recorded, steps = self.load()
        self.replay(policy, recorded, steps, READ_POWERS_ROW)
        board = steps[READ_POWERS_ROW][1]()
        self.assertEqual((board.light_radius, board.can_see_own_grid), (0, False))
        worn = policy._worn_light(board)
        self.assertEqual((worn.is_lantern, worn.fuel), (True, 0))
        self.assertFalse(any(item.is_oil for item in board.inventory))
        key = policy.choose_key(board)
        # Recorded: 'bA' me-staff:read-powers, then the walk to the Magic shop.
        self.assertEqual(recorded[READ_POWERS_ROW]["reason"], "me-staff:read-powers")
        # No errand plan on the restart's first board: the supply ledger's oil
        # row (0 of 5 flasks) names the General Store.
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._store_visit.store_type, STORE_GENERAL)
        oil = policy._supply_ledger(board, policy._planned_depth())["oil"]
        self.assertEqual((oil.count, oil.stores), (0, (STORE_GENERAL,)))
        self.assertFalse(town_travel.is_travel_macro(key), key)
        self.assert_posts(policy, self.raw(recorded[READ_POWERS_ROW]), board, key)

    def test_no_travel_is_sent_from_the_lit_entrance_without_a_light(self):
        policy, recorded, steps = self.load()
        self.replay(policy, recorded, steps, TRAVEL_ROW, strict=False)
        board = steps[TRAVEL_ROW][1]()
        # The lit Magic shop entrance: the own grid is seen, the player's light is out.
        self.assertEqual((board.light_radius, board.can_see_own_grid), (0, True))
        self.assertEqual(recorded[TRAVEL_ROW]["key"], "\x1b`n9999999999999.")
        self.assertTrue(policy._native_travel_sightless(board))
        key = policy.choose_key(board)
        self.assertFalse(town_travel.is_travel_macro(key), (key, policy.last_reason))
        self.assertFalse(policy.last_reason.startswith("me-staff:"), policy.last_reason)

    def test_a_light_that_cannot_be_restored_walks_the_staff_leg(self):
        policy, recorded, steps = self.load()
        self.replay(policy, recorded, steps, TRAVEL_ROW, strict=False)
        board = steps[TRAVEL_ROW][1]()
        # DECLARED CONSTRUCTED: no stop of the errand plan left to restore the
        # light (the shelves visited without oil), so the restore yields.
        with mock.patch.object(policy, "_town_light_restore_key", return_value=None):
            key = policy.choose_key(board)
        self.assertTrue(policy.last_reason.startswith("me-staff:"), policy.last_reason)
        self.assertFalse(town_travel.is_travel_macro(key), (key, policy.last_reason))
        self.assert_posts(policy, self.raw(recorded[TRAVEL_ROW]), board, key)

    def general_store_board(self, recorded):
        raw = self.raw(recorded[READ_POWERS_ROW])
        raw["store"] = {"items": [dict(OIL_ROW)], "max_cost": 5000, "page_size": 52,
                        "page_top": 0, "stock_num": 1, "store_type": STORE_GENERAL,
                        "owner_name": "", "owner_race": "", "store_name": "雑貨屋"}
        return raw

    def test_the_general_store_page_buys_the_oil(self):
        policy, recorded, steps = self.load()
        self.replay(policy, recorded, steps, READ_POWERS_ROW)
        policy.choose_key(steps[READ_POWERS_ROW][1]())
        raw = self.general_store_board(recorded)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.observe_store_screen(True)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "shop:in-store-buy", key)
        self.assertTrue(key.startswith("pa"), key)

    def test_carried_oil_refuels_the_lantern_before_the_staff_sequence(self):
        policy, recorded, steps = self.load()
        self.replay(policy, recorded, steps, READ_POWERS_ROW)
        raw = self.raw(recorded[READ_POWERS_ROW])
        oil = {key: value for key, value in OIL_ROW.items() if key not in {"letter", "price"}}
        raw["inventory"].append(dict(oil, count=5, slot=chr(ord("a") + len(raw["inventory"]))))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "refill-light", key)
        flask = next(item for item in board.inventory if item.is_oil)
        # The recorded floor refill was '\\Fa' (refill-light, 04:51:28).
        self.assertEqual(key, "\\F" + flask.slot)


if __name__ == "__main__":
    unittest.main()
