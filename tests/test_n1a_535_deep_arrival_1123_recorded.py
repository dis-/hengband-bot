"""n1-a life-535: a trap door drops two floors; no recall lands where the deep fall guard leaves.

n1-a life-535 (Warrior Lv40, no *Destruction* means) was stopped at 2026-11-23 00:59:50 by
``dungeon:blocked:deep-arrival-without-destruction`` on the Castle's 50F.  The way there:

* 00:19-00:21 the town recalled it to Angband's 49F five times, and each time the deep fall
  guard read Recall at once (``deep-fall-guard:recall``: no trap detection on 49F);
* the no-depth-progress lease then sent it to the Castle, whose recall depth was 48
  (``town:recall-to-alt-dungeon``, 00:59:29);
* on the Castle's 48F the exploration walked east, (38,136) to (38,143), the guard silent (a fall
  from 48F was taken to land on 49F), and the step at turn 5123385 fell through a trap door onto
  50F (the game's diary: 「48階(城): 落とし戸に落ちた」, 「城の最深階50階に到達した」).

The viewing server's diaries count 106 trap door falls of one floor and 64 of two
(deep_fall_guard ``TRAP_DOOR_DROPS``).  Owner 2026-11-22 「そもそも50Fに降りない方をしっかり作る
こと」, 「城は45Fまでにする。ギリギリを攻めない。」.

Recorded: the 00:58:36 town-arrival checkpoint of n1-a life-535
(tests/fixtures/n1a-535-deep-arrival-1123, its 148 town rows replayed as recorded, up to the
Recall to the Castle waited for) and the capture's 48F boards of turns 5123328-5123386
(``boards.jsonl.xz``, the state.jsonl lines of capture 20261123-005954).

DECLARED CONSTRUCTED:

* the town visit replays under the recall gates it was recorded with: ``landing_refused`` (new)
  answers False while the 148 rows replay, so the recorded decisions stand (with it the
  departure picks the Castle climb, ``test_the_refused_landings_fall_back_to_the_castle_climb``);
* the executor's game: the recorded 48F board the key is posted on, the game showing the read
  prompt, then the same board ten game turns on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-deep-arrival-1123"
ANGBAND, CASTLE, MOUNTAIN = 1, 12, 14
DEPARTURE_ROW = 122   # town:recall-to-alt-dungeon (the Castle, recall depth 48)
FALL_STEP = Position(38, 143)


class DeepArrivalTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
            # DECLARED CONSTRUCTED (module docstring): the recall gates the visit was recorded
            # with.
            with mock.patch("hengbot.deep_fall_guard.landing_refused", return_value=False,
                            create=True):
                cls.town = replay_window("n1a-535-deep-arrival", cls.policy, iter(steps))
            cls.departure = steps[DEPARTURE_ROW][1]()
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        cls.raws = []
        seen = set()
        for line in lines:
            raw = json.loads(line)
            if raw.get("type") == "player_turn" and raw["turn"] not in seen:
                seen.add(raw["turn"])
                cls.raws.append(raw)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _board(self, raw):
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def test_the_town_visit_replays_as_recorded(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 148)
        self.assertEqual(self.journal[DEPARTURE_ROW]["reason"], "town:recall-to-alt-dungeon")
        # The lease that sent it to the Castle, not the climb (whose band stops at 45F).
        self.assertEqual((self.policy._alternate_dungeon, self.policy._alternate_dungeon_reason),
                         (CASTLE, "no_depth_progress"))

    def test_the_castle_48f_walk_is_at_risk_and_reads_recall(self):
        from hengbot import deep_fall_guard

        walk = [raw for raw in self.raws if raw["floor"]["level"] == 48]
        self.assertEqual(self._board(walk[-1]).player.position, FALL_STEP)
        self.assertEqual(self._board(self.raws[-1]).floor_key, (CASTLE, 50, 0))
        first = self._board(walk[0])
        self.assertTrue(deep_fall_guard.at_risk(self.policy, first))
        self.assertFalse(deep_fall_guard.holds_detection(self.policy, first))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            key = self.policy.choose_key(first)
        # Recorded: explore '6' (east, toward the trap door at (38,144)).
        self.assertEqual(self.policy.last_reason, deep_fall_guard.RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)
        self.assertTrue(self._post(key, walk[0]))

    def test_a_fall_of_two_floors_is_read_everywhere(self):
        from hengbot import deep_fall_guard

        policy = self.policy
        first = self._board(self.raws[0])
        # 47F: a fall lands on 49F at most.
        self.assertFalse(deep_fall_guard.fall_unsanctioned(policy, CASTLE, 47))
        self.assertTrue(deep_fall_guard.fall_unsanctioned(policy, CASTLE, 48))
        self.assertTrue(deep_fall_guard.fall_unsanctioned(policy, ANGBAND, 48))
        # The Mountain's last floor is 50F: its 49F falls onto 50F only.
        self.assertTrue(deep_fall_guard.fall_unsanctioned(policy, MOUNTAIN, 49))
        # No stair down onto 48F without a detection; onto 47F as before.
        self.assertTrue(deep_fall_guard.descent_refused(policy, first, 48))
        self.assertFalse(deep_fall_guard.descent_refused(policy, first, 47))
        self.assertTrue(deep_fall_guard.teleport_level_refused(policy, first))

    def test_the_departure_refuses_the_landings_the_guard_leaves(self):
        from hengbot import deep_fall_guard

        policy, town = self.policy, self.departure
        self.assertTrue(town.in_town)
        self.assertEqual({did: town.dungeon_recall_depths[did] for did in (ANGBAND, CASTLE, MOUNTAIN)},
                         {ANGBAND: 49, CASTLE: 48, MOUNTAIN: 48})
        for did in (ANGBAND, CASTLE, MOUNTAIN):
            depth = policy._dungeon_entry_depth(town, did, via_recall=True)
            self.assertTrue(deep_fall_guard.landing_refused(policy, town, did, depth), did)
            # Recorded: Angband five times, then the Castle.
            self.assertFalse(policy._recall_destination_safe(town, did), did)
            self.assertFalse(policy._fallback_landing_allowed(town, did, depth, depth_floor=False),
                             did)

    def test_the_refused_landings_fall_back_to_the_castle_climb(self):
        from hengbot import deep_climb, dive_floor

        policy = copy.deepcopy(self.policy)
        town = self.departure
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            alternate = policy._activate_safe_recall_fallback(
                town, policy._dungeon_entry_depth(town, ANGBAND, via_recall=True))
        self.assertEqual(alternate, CASTLE)
        self.assertEqual(dive_floor.climb_dungeon(policy), CASTLE)
        self.assertLessEqual(dive_floor.band(policy, town)[1], dive_floor.CLIMB_BAND_DEEPEST)
        # Its 48F landing passes the gate and is climbed from at once.
        self.assertTrue(policy._recall_destination_safe(town, CASTLE))
        board = self._board(self.raws[0])
        self.assertTrue(deep_climb.climb_floor(policy, board))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            policy.choose_key(board)
        self.assertTrue(policy.last_reason.startswith(deep_climb.CLIMB_REASON),
                        policy.last_reason)

    def _post(self, key, raw):
        """The production executor posts ``key`` on the recorded ``raw`` line, the game showing
        the read prompt, then the same board ten game turns on."""
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(executor_pins.READ_PROMPT),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence,
                      "reason": self.policy.last_reason},
            snapshot=self._board(raw), posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        return game.accepted


if __name__ == "__main__":
    unittest.main()
