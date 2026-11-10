"""n1-b life-321 (2026-11-05 23:18 to 11-06 02:06): light radius 0 under a dark light.

At 23:18 the equipment optimizer put on the just identified ★火消しライター
(TR_LITE_M1 with TR_DARK_SOURCE: radius -1, +3 stealth) for its score and put the
★ガラドリエルの玻璃瓶 in Home: the loadout's light radius was only a tie-breaker.
Every light rule took the artifact (sval >= SV_LITE_FEANOR) for a permanent light
that lights.  The character read nothing in the dark from then on:

* 02:01 in town at night, ``town:repetition-depart:recall`` sent ``ric`` twelve times,
  each refused with 「明かりがないので見えない。」 and no turn passing.
* 02:05 and 02:06 on Yeek cave 1F, a granite tunnel finished (「穴を掘り終えた。」);
  the new floor does not REMEMBER and the dark hid it, so the board dropped the cell
  while the policy's grid memory kept the wall: ``T7`` twelve times, 「そこは掘れない。」.

Now a light that lights is required whenever one is owned, a dark light counts as no
light, the forced departure reads only where the game lets it, and a finished or
refused tunnel forgets the remembered wall the board no longer shows.  A wall the worn
digger can never break (skill_dig <= the terrain's tunnel power, n1-b life-315's
granite) is no dig target.
Fixtures: tests/extract_n1b_321_zero_light_1106_fixtures.py.
DECLARED CONSTRUCTED: in the pins of the read and the dig, the dark-light rule is held
off (``lights_nothing`` answers False), so the recorded run that reached those boards is
replayed; the Magic-Eater power uses of the floor are laid from the stop capture (the
executor's completed-operation receipts are not on the ring's boards); the digging
skill of the granite pin.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import equipment_optimizer, me_powers, policy as policy_module, policy_supply, town_travel
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, STORE_HOME, parse_snapshot
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests.support import recorded as executor_pins
import test_n1b_322_walkout_dig_1106_recorded as walkout_pins


FIXTURES = Path(__file__).with_name("fixtures") / "n1b-321-zero-light-1106"
PHIAL = "★ガラドリエルの玻璃瓶"
DELUMINATOR = "★火消しライター"
STEP_OFF_ROW = 34          # the visit leaves the Home entrance to re-enter it
RECALL_ROW = 191           # the first refused ``ric``
DUG_CELL = Position(17, 78)  # the granite the 02:06 tunnel finished
GRANITE = 56               # lib/edit/TerrainDefinitions.jsonc GRANITE, tunnel power 40
LIFE_315_DIGGING = 38      # n1-b life-315's Lv7 skill with a shovel (granite never breaks)


def _dark_light_rule_off():
    """The dark-light rule held off: the recorded run's own answers."""
    never = lambda _item: False  # noqa: E731
    return [mock.patch.object(module, "lights_nothing", never)
            for module in (policy_module, policy_supply, equipment_optimizer)]


class ZeroLightRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, case):
        visit = self.scratch / case / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / f"{case}.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        runtime = self.scratch / case / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        self.visit = visit
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def hold_dark_light_rule_off(self):
        for patcher in _dark_light_rule_off():
            patcher.start()
            self.addCleanup(patcher.stop)

    def replay(self, policy, recorded, steps, rows, *, strict=True):
        """Decide each row's board and post its recorded key."""
        for index in range(rows):
            board = steps[index][1]()
            chosen = policy.choose_key(board)
            if (strict and town_travel.is_travel_macro(recorded[index]["key"])
                    and policy._town_light_out(board)):
                # n1-b life-343 (2026-11-08): no native travel without the
                # player's own light; the recorded travel was refused
                # (「目が見えない！」 on the next board) and the walk replaces it.
                self.assertFalse(town_travel.is_travel_macro(chosen), f"row {index}")
            elif strict and recorded[index]["reason"] == "store:entry-interrupted-replan":
                # The recorded reaction to that refused travel: the same step,
                # now the walk's own (no travel was interrupted).
                self.assertEqual(chosen, recorded[index]["key"], f"row {index}")
            elif strict:
                self.assertEqual((chosen, policy.last_reason),
                                 (recorded[index]["key"], recorded[index]["reason"]),
                                 f"row {index}")
            policy.confirm_key_posted(recorded[index]["key"])

    def assert_posts(self, policy, raw, board, key):
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
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    @staticmethod
    def raw(row):
        return json.loads(row["line"] or row["inputs"][-1])

    # -- town, 02:01 ---------------------------------------------------------

    def test_the_phial_goes_back_on_and_the_dark_light_holds_the_departure(self):
        policy, recorded, steps = self.load("town")
        self.replay(policy, recorded, steps, STEP_OFF_ROW)
        board = steps[STEP_OFF_ROW][1]()
        worn = next(item for item in board.equipment if item.is_light)
        self.assertTrue(worn.name.startswith(DELUMINATOR))
        self.assertEqual(board.light_radius, 0)
        key = policy.choose_key(board)
        # The optimizer wants the phial from Home: the loadout must light.
        best = policy._equipment_optimization_preparation.result.best.loadout
        light = best.item_at(equipment_optimizer.SLOT_LIGHT)
        self.assertEqual(light.origin, "home")
        self.assertTrue(light.item.name.startswith(PHIAL))
        self.assertGreater(equipment_optimizer.loadout_light_radius(best), 0)
        # The light rules see no light: the expedition is not light-ready.
        self.assertIsNone(policy._worn_light(board))
        self.assertFalse(policy._expedition_light_ready(board))
        self.assertFalse(policy._light_ready(board))
        # Recorded: shop:travel elsewhere; now the Home visit steps off to re-enter.
        self.assertEqual(recorded[STEP_OFF_ROW]["reason"], "shop:travel")
        self.assertEqual(policy._store_visit.store_type, STORE_HOME)
        self.assertEqual(policy._store_visit.owner, "equipment-transaction")
        self.assert_posts(policy, self.raw(recorded[STEP_OFF_ROW]), board, key)

    def test_a_read_the_dark_refuses_is_not_sent(self):
        self.hold_dark_light_rule_off()
        policy, recorded, steps = self.load("town")
        self.assertEqual((recorded[RECALL_ROW]["key"], recorded[RECALL_ROW]["reason"]),
                         ("ric", "town:repetition-depart:recall"))
        self.replay(policy, recorded, steps, RECALL_ROW)
        board = steps[RECALL_ROW][1]()
        self.assertIs(board.can_see_own_grid, False)
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:repetition-depart:recall")
        self.assertFalse(key.startswith("r"), key)
        self.assert_posts(policy, self.raw(recorded[RECALL_ROW]), board, key)

    # -- Yeek cave 1F, 02:06 -------------------------------------------------

    def dungeon(self):
        """The arrival policy replayed through the town and onto the floor."""
        self.hold_dark_light_rule_off()
        policy, recorded, steps = self.load("dig")
        # Not strict: one journalled key is the driver's rewrite (row 40).
        self.replay(policy, recorded, steps, len(recorded), strict=False)
        with gzip.open(self.visit / "dungeon.json.gz", "rt", encoding="utf-8") as stream:
            case = json.load(stream)
        return policy, case

    def decide_on_floor(self, policy, case, raw):
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        memory = getattr(policy, me_powers.MEMORY, None)
        if memory is None or memory.floor != board.floor_key:
            memory = me_powers.FloorMemory(board.floor_key, board.turn)
            setattr(policy, me_powers.MEMORY, memory)
        memory.uses = [
            me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                          Position(*use["position"]), use["turn"], use["reason"], use["key"])
            for use in case["me_power_uses"] if use["turn"] < board.turn
        ]
        memory.pending = None
        return board, policy.choose_key(board)

    def walk_floor(self, policy, case, rows):
        for index, pair in enumerate(case["boards"][:rows]):
            _board, key = self.decide_on_floor(policy, case, pair["board"])
            recorded = pair["decision"]
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             f"floor row {index}")
            policy.confirm_key_posted(recorded["key"])

    def test_the_dug_cell_is_walked_not_dug_again(self):
        policy, case = self.dungeon()
        dug = case["boards"][-1]
        self.assertEqual((dug["decision"]["key"], dug["decision"]["turn"]), ("T7", 2596574))
        self.walk_floor(policy, case, len(case["boards"]) - 1)
        self.assertIn(DUG_CELL, policy._remembered_grids)
        raw = dug["board"]
        self.assertIn("穴を掘り終えた。", raw["messages"])
        board, key = self.decide_on_floor(policy, case, raw)
        self.assertNotIn(DUG_CELL, policy._remembered_grids)
        self.assertNotEqual(key, "T7")
        self.assertEqual((key, policy.last_reason), ("7", "fundraise:seek-treasure"))
        self.assert_posts(policy, raw, board, key)

    def test_granite_the_worn_digger_never_breaks_is_not_dug(self):
        policy, case = self.dungeon()
        last = len(case["boards"]) - 2
        pair = case["boards"][last]
        self.assertEqual((pair["decision"]["key"], pair["decision"]["reason"]),
                         ("T7", "fundraise:dig-to-treasure"))
        self.walk_floor(policy, case, last)
        raw = copy.deepcopy(pair["board"])
        raw["player"]["skill_ratings"]["digging"]["value"] = LIFE_315_DIGGING
        board, key = self.decide_on_floor(policy, case, raw)
        self.assertEqual(board.grids[DUG_CELL].terrain_id, GRANITE)
        self.assertNotEqual(key, "T7")
        self.assertNotEqual(policy.last_reason, "fundraise:dig-to-treasure")
        self.assert_posts(policy, raw, board, key)


class WalkOutDigNeverBreaksTest(executor_pins.ProductionHarness):
    """The walk-out dig (n1-b life-322's board, tests/test_n1b_322_walkout_dig_1106_recorded)
    with the worn digger of n1-b life-315: no route through granite it never breaks.
    DECLARED CONSTRUCTED: the digging skill (77 recorded)."""

    # That module's board helpers, without collecting its tests a second time.
    policy = walkout_pins.MiningWalkOutDigTest.policy
    board = staticmethod(walkout_pins.MiningWalkOutDigTest.board)
    decide = walkout_pins.MiningWalkOutDigTest.decide
    post = walkout_pins.MiningWalkOutDigTest.post

    def test_the_walk_out_does_not_tunnel_granite_it_never_breaks(self):
        raw = copy.deepcopy(walkout_pins.CASE["beside_trap_board"])
        self.assertEqual(raw["player"]["skill_ratings"]["digging"]["value"], 77)
        raw["player"]["skill_ratings"]["digging"]["value"] = LIFE_315_DIGGING
        policy = self.policy()
        board, key = self.decide(policy, raw)
        self.assertNotEqual(policy.last_reason, walkout_pins.DIG_UPSTAIRS)
        self.assertFalse(key.startswith(walkout_pins.TUNNEL_KEY), key)
        self.post(policy, board, raw, key)


if __name__ == "__main__":
    unittest.main()
