"""n1-a life-531: no arrival at 50F+ without the *Destruction* means; the climb may teleport.

Owner 2026-11-22 (verbatim): 「上りの間は即死以外でもテレポートを許すが、そもそも50Fに降りない方を
しっかり作ること」 (deep_teleport.applies on the climb, deep_fall_guard).  On the Castle's 50F
climb the character read Recall about twenty times in place of a teleport (deep-teleport:recall,
07:49-08:19) and fell through two trap doors 50F -> 52F -> 54F (08:04).

Recorded: the 08:25:05 town-arrival checkpoint of n1-a life-531
(tests/fixtures/n1a-531-mountain-climb-1122-survival): the policy holding the unsafe-recall
fallback's Mountain climb (dungeon 14, landing 50, its last floor), no *Destruction* means (device
skill 42), no levitation.

DECLARED CONSTRUCTED:

* every dungeon board: the recorded row-13 board moved to a dungeon floor (``floor_key``,
  ``town_flag``), with, where a test says so, a trap shown on the cell east of the player, every
  grid still CAVE_UNSAFE (``unsafe_rows``) or none, a down staircase underfoot, the Recall
  counting down (``recalling``), and one carried item replaced by a Staff of Detect Traps, a Rod
  of Trap Location or a Scroll of Teleport Level; no such board of these rules was journalled
  (the rules did not exist);
* the executor's game: the recorded row-13 line, its floor moved the same way, and the next board
  after the command (``turn`` + 10).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures")
ANGBAND, CASTLE, MOUNTAIN = 1, 12, 14
TVAL_STAFF, SV_STAFF_DETECT_TRAP = 55, 12
TVAL_SCROLL, SV_SCROLL_TELEPORT_LEVEL = 70, 10
TVAL_ROD, SV_ROD_DETECT_TRAP = 66, 0

# DECLARED CONSTRUCTED: the visits replay under the Teleport Other carry rule they were recorded
# with.  Since 2026-11-22 an empty Wand of Teleport Other the Tower recharges is a device to take
# out (teleport_away_carry.rechargeable; n1-a life-531's Home held twelve or thirteen of them), so
# the replayed Home visits would take one where the recording did not
# (tests/test_n1a_531_away_wand_recharge_1122_recorded.py).
_RECORDED_CARRY_RULE = mock.patch("hengbot.teleport_away_carry.rechargeable", return_value=False)


def setUpModule():
    _RECORDED_CARRY_RULE.start()


def tearDownModule():
    _RECORDED_CARRY_RULE.stop()


class NoDeepArrivalTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(
                FIXTURES / "n1a-531-mountain-climb-1122-survival", Path(cls.scratch.name))
            replay_window("n1a-531-no-deep", cls.policy, iter(steps[:13]))
            cls.row = _journal[13]
            cls.town = steps[13][1]()
            cls.policy.choose_key(cls.town)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    # DECLARED CONSTRUCTED (module docstring).
    def _board(self, floor_key, *, trap_east=False, unsafe=None, item=None, down_stairs=False,
               recalling=False):
        board = replace(self.town, floor_key=floor_key, town_flag=False)
        if recalling:
            board = replace(board, player=replace(board.player, recalling=True))
        here = board.player.position
        east = Position(here.y, here.x + 1)
        grids = dict(board.grids)
        grids[here] = replace(grids[here], passable=True, wall=False, known=True, trap=False,
                              has_up_stairs=False, has_down_stairs=down_stairs,
                              has_entrance=False, store_number=-1, building_type=-1,
                              is_closed_door=False)
        grids[east] = replace(grids.get(east, grids[here]), position=east, passable=True,
                              wall=False, known=True, trap=trap_east, has_up_stairs=False,
                              has_down_stairs=False, has_entrance=False, store_number=-1,
                              building_type=-1, is_closed_door=False, is_door=False,
                              object_count=0)
        board = replace(board, grids=grids)
        if unsafe is not None:
            height = max(here.y, east.y) + 2
            width = max(here.x, east.x) + 2
            board = replace(board, unsafe_rows=tuple((unsafe,) * width for _ in range(height)),
                            unsafe_rows_malformed=False)
        if item is not None:
            inventory = list(board.inventory)
            inventory[-1] = replace(inventory[-1], **item)
            board = replace(board, inventory=inventory)
        return board, east

    def test_the_climb_floor_reads_the_teleport_as_above_50f(self):
        from hengbot import deep_teleport

        climb, _ = self._board((MOUNTAIN, 50, 0))
        self.assertFalse(deep_teleport.applies(self.policy, climb))
        # Angband's 50F is no climb floor: the 50F+ teleport rule stays.
        angband, _ = self._board((ANGBAND, 50, 0))
        self.assertTrue(deep_teleport.applies(self.policy, angband))

    def test_a_fall_is_at_risk_only_where_it_lands_unsanctioned(self):
        from hengbot import deep_fall_guard

        policy = self.policy
        self.assertTrue(deep_fall_guard.at_risk(policy, self._board((ANGBAND, 49, 0))[0]))
        self.assertTrue(deep_fall_guard.at_risk(policy, self._board((CASTLE, 50, 0))[0]))
        # The climb's own 49F falls onto its 50F landing; the Mountain's 50F is its last floor.
        self.assertFalse(deep_fall_guard.at_risk(policy, self._board((MOUNTAIN, 49, 0))[0]))
        self.assertFalse(deep_fall_guard.at_risk(policy, self._board((MOUNTAIN, 50, 0))[0]))
        # A trap door drops one floor or two (n1-a life-535, the Castle's 48F onto 50F, 2026-11-23):
        # 48F is at risk, 47F is not.
        self.assertTrue(deep_fall_guard.at_risk(policy, self._board((ANGBAND, 48, 0))[0]))
        self.assertFalse(deep_fall_guard.at_risk(policy, self._board((ANGBAND, 47, 0))[0]))

    def test_no_step_onto_a_known_trap_on_an_at_risk_floor(self):
        policy = self.policy
        board, east = self._board((ANGBAND, 49, 0), trap_east=True)
        self.assertEqual(policy._step_toward(board, east), "5")
        self.assertEqual(policy.last_reason, "deep-fall-guard:trap-step-refused")
        from hengbot import deep_fall_guard
        saved = set(policy._engagement_avoid_cells)
        try:
            deep_fall_guard.refresh_avoid(policy, board)
            self.assertIn(east, policy._engagement_avoid_cells)
        finally:
            policy._engagement_avoid_cells = saved
        # 47F (its fall lands on 49F at most): the trap is disarmed as before.
        shallow, east = self._board((ANGBAND, 47, 0), trap_east=True)
        self.assertNotEqual(policy._step_toward(shallow, east), "5")

    def test_the_traps_are_detected_before_the_walk_else_the_49f_floor_is_left(self):
        from hengbot import deep_fall_guard

        policy = self.policy
        staff = {"tval": TVAL_STAFF, "sval": SV_STAFF_DETECT_TRAP, "charges": 5, "known": True,
                 "aware": True, "count": 1, "name": "トラップ感知の杖 (5回分)", "charging": False}
        board, _ = self._board((ANGBAND, 49, 0), unsafe=True, item=staff)
        setattr(policy, deep_fall_guard.MEMORY, None)
        key = deep_fall_guard.key(policy, board)
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, deep_fall_guard.DETECT_REASON)
        detected, _ = self._board((ANGBAND, 49, 0), unsafe=False, item=staff)
        setattr(policy, deep_fall_guard.MEMORY, None)
        self.assertIsNone(deep_fall_guard.key(policy, detected))
        bare, _ = self._board((ANGBAND, 49, 0), unsafe=True)
        setattr(policy, deep_fall_guard.MEMORY, None)
        try:
            # The decision (the objectives layer's first rung) reads Recall (h).
            self.assertEqual((policy.choose_key(bare), policy.last_reason),
                             ("rh", deep_fall_guard.RECALL_REASON))
            self.assertTrue(self._post("rh", (ANGBAND, 49, 0), bare,
                                       prompts=(executor_pins.READ_PROMPT,)))
        finally:
            policy._returning_to_town = False
            policy._last_return_trigger = None

    def test_the_recall_is_waited_for_in_place_on_the_undetected_49f(self):
        from hengbot import deep_fall_guard

        policy = self.policy
        board, _ = self._board((ANGBAND, 49, 0), unsafe=True, recalling=True)
        setattr(policy, deep_fall_guard.MEMORY, None)
        self.assertEqual(deep_fall_guard.key(policy, board), "5")
        self.assertEqual(policy.last_reason, deep_fall_guard.WAIT_RECALL_REASON)

    def _post(self, key, floor_key, board, prompts=()):
        """The production executor posts ``key`` on the recorded line moved to ``floor_key``,
        the game showing ``prompts`` before the next board."""
        raw = json.loads(self.row["line"])
        raw["floor"] = dict(raw["floor"], dungeon_id=floor_key[0], level=floor_key[1],
                            in_town=False, town_id=0)
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*(executor_pins.prompt_screen(prompt) for prompt in prompts),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence,
                      "reason": self.policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        return game.accepted

    def test_no_stair_down_onto_a_floor_whose_trap_door_would_reach_50f(self):
        policy = self.policy
        rod = {"tval": TVAL_ROD, "sval": SV_ROD_DETECT_TRAP, "known": True, "aware": True,
               "count": 1, "name": "トラップ感知のロッド", "charging": False}
        cases = (
            ((ANGBAND, 48, 0), None, False),
            # A trap detection carried: the traps of 49F are detected there (deep_fall_guard.key).
            ((ANGBAND, 48, 0), rod, True),
            # 48F's own trap door lands on 50F too (two floors, n1-a life-535): refused.
            ((ANGBAND, 47, 0), None, False),
            # 47F's own trap door lands on 49F at most.
            ((ANGBAND, 46, 0), None, True),
        )
        for floor_key, item, taken in cases:
            board, _ = self._board(floor_key, item=item, down_stairs=True)
            grid = board.grid_at(board.player.position)
            self.assertEqual(policy._is_descent_target(board, grid), taken, (floor_key, item))
        # The climb's 49F falls onto its own 50F landing: no refusal of this rule.
        from hengbot import deep_fall_guard
        mountain, _ = self._board((MOUNTAIN, 48, 0), down_stairs=True)
        self.assertFalse(deep_fall_guard.descent_refused(policy, mountain, 49))
        # The decision on Angband's 47F: the walk goes on instead of the stair.
        board, _ = self._board((ANGBAND, 47, 0), down_stairs=True)
        key = policy.choose_key(board)
        self.assertNotEqual(key, ">")
        self.assertEqual(policy.last_reason, "explore")
        self.assertTrue(self._post(key, (ANGBAND, 47, 0), board))
        shallow, _ = self._board((ANGBAND, 46, 0), down_stairs=True)
        self.assertEqual((policy.choose_key(shallow), policy.last_reason), (">", "descend"))

    def test_teleport_level_is_not_read_where_it_could_go_down_onto_50f(self):
        from hengbot import deep_fall_guard, threat_escape

        policy = self.policy
        scroll = {"tval": TVAL_SCROLL, "sval": SV_SCROLL_TELEPORT_LEVEL, "known": True,
                  "aware": True, "count": 3, "name": "テレポート・レベルの巻物"}
        deep, _ = self._board((ANGBAND, 49, 0), item=scroll)
        shallow, _ = self._board((ANGBAND, 30, 0), item=scroll)
        self.assertTrue(deep_fall_guard.teleport_level_refused(policy, deep))
        self.assertNotIn("teleport-level", threat_escape.escape_means(policy, deep, []))
        self.assertIn("teleport-level", threat_escape.escape_means(policy, shallow, []))

    def test_the_named_stop_spares_the_climbs_own_landing(self):
        from hengbot import deep_climb

        policy = self.policy
        saved = getattr(policy, deep_climb.MEMORY, None)
        try:
            for start, end, stops in (((MOUNTAIN, 49, 0), (MOUNTAIN, 50, 0), False),
                                      ((ANGBAND, 49, 0), (ANGBAND, 50, 0), True)):
                setattr(policy, deep_climb.MEMORY, None)
                deep_climb.observe(policy, self._board(start)[0])
                board = self._board(end)[0]
                deep_climb.observe(policy, board)
                self.assertEqual(deep_climb.stop_key(policy, board) is not None, stops, end)
        finally:
            setattr(policy, deep_climb.MEMORY, saved)


if __name__ == "__main__":
    unittest.main()
