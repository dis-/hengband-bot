"""n1-a life-531: the climb below the band climbs at once and recalls on no escape count.

n1-a life-531 (Warrior Lv50, no *Destruction* means, the unsafe-recall fallback's Mountain climb:
dungeon 14, saved recall depth 50, band 38-42) died on Mountain 49F at 2026-11-22 13:40:13.
Between 13:26 and 13:40 it landed on Mountain 50F six times and never reached the band:

* on 47F-49F it walked after loot and the exploration's frontier (``seek-loot`` / ``explore``):
  deep_climb's climb rung ("up stair before loot or objectives") acted on 50F+ only, and
  ladder_descent's climb rung, below the loot, acts only once an up staircase is known;
* on 47F (13:38:47-48) the floor's second escape latched the return (``emergency:teleport`` under
  ``emergency-lethal-swarm``, then ``emergency-repeat`` on the landing) and the Recall answered n
  to 「ここは最深到達階より浅い階です。この階に戻って来ますか？」 outside the band, so the next visit
  landed on 50F again.

Owner 2026-11-22 (verbatim): 「城の50Fに帰還してすぐ38〜42Fへ登る」, 「上りの間は即死以外でもテレポートを
許すが、そもそも50Fに降りない方をしっかり作ること」 (during the climb the escape is the teleport and
the search for the up stairs goes on without a Recall) and 「鉄獄50Fのとき、城は45Fまでにする。
ギリギリを攻めない。」.

Recorded: the 13:38:55 town-arrival checkpoint of the death capture
(tests/fixtures/n1a-531-climb-fix-1122, tests/extract_n1a_531_climb_fix_1122_fixture.py), its
112 visit rows replayed as recorded, and the capture's boards: the Mountain 50F landing, the last
50F board and every 49F board to the death.

DECLARED CONSTRUCTED:

* the 50F boards between the landing and the up stairs are not fed (the 49F decisions read the
  49F boards);
* the escape count: the floor's first escape counted (``_dive_emergencies`` 1, the 47F's
  ``flee:scroll`` of 13:38:47 recorded before the checkpoint) and its line of fire granted
  (``line_of_fire.counts`` / ``note``) on the 49F boards the second escape is asked on; the
  control moves the same board to the band's 42F (``floor_key``);
* the executor's game for the reset question: the recorded 49F line, its saved Mountain depth 50,
  the read prompt and recall_player's question (src/spell-kind/spells-world.cpp:442-449) before
  the next board (``turn`` + 10); the band and Angband cases move the floor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import deep_climb, dive_floor, escape_count, return_start
from hengbot.cli import _ExecutorInputPort
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-climb-fix-1122"
ANGBAND, MOUNTAIN = 1, 14
RESET_PROMPT = "ここは最深到達階より浅い階です。この階に戻って来ますか？ [y/n]"
# Recorded 2026-11-22 13:39:55: the first 49F walks with no up staircase known.
SEEK_LOOT_49 = (31977995, 31978001)
# Recorded 13:40:11: the emergency ladder's board beside the summoners (emergency:heal).
EMERGENCY_49 = 31978741
KEPT = (*SEEK_LOOT_49, EMERGENCY_49)
# The count's returns (policy_combat ``_emergency_item``, policy ``_latch_repeat_emergency_return``,
# ``_post_emergency_return_trigger``, policy_observation).
COUNT_TRIGGERS = frozenset({"emergency-repeat", "emergency-summoner", "emergency-lethal-swarm",
                            "emergency-ranged-status-lock"})


def _quiet(call):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call()


class ClimbFixTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, steps = _quiet(lambda: load(FIXTURE, Path(cls.scratch.name)))
        cls.town = _quiet(lambda: replay_window("n1a-531-climb-fix", cls.policy, iter(steps)))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        cls.raws = [json.loads(line) for line in lines]
        cls.decided = {}
        cls.policies = {}
        for raw in cls.raws:
            board = parse_snapshot(raw, cls.policy._monrace_knowledge)
            if raw["turn"] in KEPT:
                cls.policies[raw["turn"]] = copy.deepcopy(cls.policy)
            key = _quiet(lambda: cls.policy.choose_key(board))
            cls.decided[raw["turn"]] = (raw, board, key, cls.policy.last_reason)
            if raw["turn"] >= EMERGENCY_49:
                break

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_town_visit_replays_as_recorded(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 112)

    def test_a_49f_climb_board_searches_the_up_stairs_before_the_loot(self):
        for turn in SEEK_LOOT_49:
            with self.subTest(turn=turn):
                _raw, board, key, reason = self.decided[turn]
                self.assertEqual(board.floor_key, (MOUNTAIN, 49, 0))
                policy = self.policies[turn]
                self.assertEqual(dive_floor.climb_dungeon(policy), MOUNTAIN)
                self.assertEqual(dive_floor.band(policy, board), (38, 42))
                self.assertTrue(dive_floor.climb_switch_floor(policy, board, board.floor_key))
                self.assertFalse(deep_climb.on_floor(policy, board))
                self.assertTrue(deep_climb.climb_floor(policy, board))
                # No up staircase known on the board.
                self.assertFalse(any(policy._is_upstairs_target(grid)
                                     for grid in board.grids.values()))
                # Recorded: ('6', 'seek-loot').
                self.assertNotIn(reason, {"seek-loot", "explore"})
                self.assertEqual(reason, "castle-climb:search-upstairs")
                self.assertIsNotNone(key)

    def _second_escape(self, board):
        """The floor's second escape asked on ``board`` (DECLARED CONSTRUCTED: the first counted,
        the line of fire granted): the return triggers started."""
        policy = copy.deepcopy(self.policies[SEEK_LOOT_49[0]])
        policy._dive_emergencies = 1
        policy._returning_to_town = False
        policy._last_return_trigger = None
        started = []
        real = return_start.start

        def record(target, trigger=None):
            started.append(trigger)
            real(target, trigger)

        with mock.patch.object(return_start, "start", record), \
                mock.patch("hengbot.line_of_fire.counts", return_value=True):
            policy._latch_repeat_emergency_return(board, "emergency:teleport")
            # The landing of the second escape (policy_combat's re-assessment).
            policy._dive_emergencies = 2
            landing = policy._post_emergency_return_trigger(board, [])
        return started, landing

    def test_a_climb_floor_second_escape_latches_no_return(self):
        _raw, board, _key, _reason = self.decided[SEEK_LOOT_49[0]]
        self.assertTrue(dive_floor.climb_switch_floor(
            self.policies[SEEK_LOOT_49[0]], board, board.floor_key))
        started, landing = self._second_escape(board)
        self.assertFalse(COUNT_TRIGGERS & set(started))
        self.assertNotEqual(landing, "emergency-repeat")
        # Control: the same board in the band.
        band = replace(board, floor_key=(MOUNTAIN, 42, 0))
        started, landing = self._second_escape(band)
        self.assertIn("emergency-repeat", started)
        self.assertEqual(landing, "emergency-repeat")

    def test_a_climb_floor_relocating_escape_starts_no_return(self):
        """policy_observation: a relocating escape decided on the climb floor, the floor's second,
        observed on the next board, starts no return; in the band it does."""
        from hengbot.policy_constants import RELOCATING_ESCAPE_REASONS

        reason = "flee:scroll"  # recorded 13:38:47 on 47F, the floor's first escape
        self.assertIn(reason, RELOCATING_ESCAPE_REASONS)
        _raw, board, _key, _reason = self.decided[SEEK_LOOT_49[1]]
        for floor, expected in ((49, False), (42, True)):
            with self.subTest(floor=floor):
                policy = copy.deepcopy(self.policies[SEEK_LOOT_49[1]])
                policy._dive_emergencies = 1
                policy._returning_to_town = False
                policy._last_return_trigger = None
                policy.last_reason = reason
                here = board.player.position
                policy._last_position = replace(here, x=here.x + 5)
                policy._floor_key = (MOUNTAIN, floor, 0)
                moved = replace(board, floor_key=(MOUNTAIN, floor, 0))
                with mock.patch("hengbot.line_of_fire.counted", return_value=True):
                    _quiet(lambda: policy.choose_key(moved))
                self.assertEqual(policy._dive_emergencies, 2)
                self.assertEqual(policy._last_return_trigger == "emergency-repeat", expected)

    def test_a_climb_floor_emergency_ladder_latches_no_count_return(self):
        """policy_combat ``_emergency_item``: on the recorded emergency board beside the
        summoners, the floor's second escape (the first counted) starts no return there."""
        _raw, board, _key, _reason = self.decided[EMERGENCY_49]
        for floor, expected in ((49, False), (42, True)):
            with self.subTest(floor=floor):
                policy = copy.deepcopy(self.policies[EMERGENCY_49])
                policy._dive_emergencies = 1
                policy._returning_to_town = False
                policy._last_return_trigger = None
                policy._floor_key = (MOUNTAIN, floor, 0)
                started = []
                real = return_start.start

                def record(target, trigger=None, started=started):
                    started.append(trigger)
                    real(target, trigger)

                moved = replace(board, floor_key=(MOUNTAIN, floor, 0))
                with mock.patch.object(return_start, "start", record):
                    _quiet(lambda: policy.choose_key(moved))
                self.assertEqual(bool(COUNT_TRIGGERS & set(started)), expected, started)

    def _answer(self, floor_key, saved=50):
        """The production executor's answer to the reset question after the recall read."""
        raw = copy.deepcopy(self.decided[SEEK_LOOT_49[0]][0])
        raw["floor"] = dict(raw["floor"], dungeon_id=floor_key[0], level=floor_key[1])
        raw["progress"] = dict(raw["progress"], dungeon_recall_depths={
            **raw["progress"].get("dungeon_recall_depths", {}), str(floor_key[0]): saved})
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(executor_pins.READ_PROMPT),
                        executor_pins.prompt_screen(RESET_PROMPT),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        policy = self.policies[SEEK_LOOT_49[0]]
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        result = port("rh", decision={"sequence": policy._decision_sequence,
                                      "reason": "return:recall"})
        self.assertTrue(result, port.last_result.reason)
        return game.accepted[-1]

    def test_a_recall_read_on_a_climb_floor_resets_the_saved_depth(self):
        policy = self.policies[SEEK_LOOT_49[0]]
        self.assertEqual(getattr(policy, dive_floor.RECALL_RESET), (MOUNTAIN, 38, 42))
        cases = (
            ((MOUNTAIN, 49, 0), "y"),   # recorded floor: the next visit lands on 49F, not 50F
            ((MOUNTAIN, 47, 0), "y"),   # the 47F of 13:38:48 answered n
            ((MOUNTAIN, 40, 0), "y"),   # the band, as before
            ((ANGBAND, 47, 0), "n"),    # no climb switch there
        )
        for floor_key, expected in cases:
            with self.subTest(floor_key=floor_key):
                self.assertEqual(self._answer(floor_key), expected)
        # The next town board: a 47F landing passes the switch and every departure gate.
        town = replace(self.town_board(), dungeon_recall_depths={
            **self.town_board().dungeon_recall_depths, MOUNTAIN: 47})
        self.assertTrue(dive_floor.reaches_band(policy, town, MOUNTAIN))
        self.assertTrue(dive_floor.refused_dive_held(policy, town))
        self.assertTrue(policy._recall_destination_safe(town, MOUNTAIN))
        self.assertTrue(policy._destination_depth_allowed(town, 47))

    def town_board(self):
        """The last recorded town board of the visit (the Recall wait)."""
        _raw, board, _key, _reason = self.decided[self.raws[0]["turn"]]
        return replace(board, floor_key=(0, 0, 0), town_flag=True)


if __name__ == "__main__":
    unittest.main()
