"""A Ring of Speed hunt floor whose feeling rules the ring out is done with (n1-b life-419, 1128).

Supervisor 2026-11-28: n1-b life-419 (Magic-Eater CL50, permanent speed +17) hunted a second Ring
of Speed under the speed ceiling for 14 hours; of its last 58 Angband 80F floors 32 had a final
feeling of 8-10 and took 71% of the decisions, 58% of all after the feeling was known.  The game
(floor/floor-events.cpp get_dungeon_feeling) gives a floor holding an uncursed Ring of Speed a
rating of at least floor_rating_boost(250), so its feeling is 7 or lower at 80F and deeper
(ring_hunt).  Owner 2026-11-28 「80Fから90Fまでは危険度に大きな変化はない。80Fで足りなければもう少し
深く潜っても良い。」 moved the permanent +25 row to 91F: the ceiling is 90F.

Recorded (tests/extract_ring_hunt_feeling_1128_fixture.py, ``ring-hunt-feeling-1128``): the
player-turn boards 14151150-14151330 of the Angband 80F floor entered by Word of Recall at
14150431; the feeling became known (10) at 14151315, where the live bot (ceiling 80F) recorded
``('3', 'explore')``.  Replayed through ``choose_key`` from a fresh production policy (partial
state: the remembered map and the visit's memories are the window's only).

DECLARED CONSTRUCTED:
- the Magic-Eater's absorbed list is not in the snapshot log (the executor reads it on its own
  operation): a *Destruction* staff of 60 charges is listed before the first board, as n1-b
  held one (the live ``mA3`` at 14151294);
- the ceiling cases replay the window with ``floor.level`` set to 90 (the ceiling, its stair down
  refused) and the board's ``floor.feeling`` replaced (10 / 7 / 0);
- the stair case moves the player of the 14151315 board onto the floor's known up staircase
  (5,70), which the window's map gives no walk to;
- the no-ceiling case reads the permanent speed as +25 (``permanent_player_speed`` patched).
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_cap, explored_floor, ring_hunt, speed_valuation
from hengbot.me_device_attacks import observe_lists
from hengbot.model import DUNGEON_ANGBAND, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import (
    MID_SPEED_GATE_LABEL, SPEED_GATE_DEPTH, SPEED_GATE_LABEL, SPEED_GATE_MINIMUM, UP_STAIRS_KEY,
)
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row

FIXTURE = Path(__file__).with_name("fixtures") / "ring-hunt-feeling-1128.jsonl.xz"
KNOWN = 14151315          # the first board of the known feeling (10)
SEEK_LOOT = 14151150      # recorded ('3', 'seek-loot'), feeling 0
PICKUP = 14151153         # recorded ('gaa', 'pickup') on the pile stood on, feeling 0
UP_STAIR = Position(5, 70)
CEILING = SPEED_GATE_DEPTH - 1


def _board(raw, *, level=None, feeling=None, position=None):
    raw = copy.deepcopy(raw)
    if level is not None:
        raw["floor"]["level"] = level
    if feeling is not None:
        raw["floor"]["feeling"] = feeling
    if position is not None:
        raw["player"]["y"], raw["player"]["x"] = position.y, position.x
    return raw


class RingHuntFeeling1128RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.raws = [json.loads(line) for line in lines if line.strip()]
        cls.scratch = TemporaryDirectory()
        cls.replayed = {}

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    @classmethod
    def replay(cls, level, until):
        """(policy before deciding ``until``, its raw board), the window replayed at ``level``
        with the recorded feelings; cached per (level, until) and copied for each use."""
        if (level, until) not in cls.replayed:
            directory = Path(cls.scratch.name) / f"{level}-{until}-{len(cls.replayed)}"
            directory.mkdir()
            policy = _policy(directory, cls.monrace)
            first = _board(cls.raws[0], level=level)
            start = parse_snapshot(copy.deepcopy(first), cls.monrace)
            policy.prime(start)
            policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
            listed = dict(first, turn=first["turn"] - 1, _magic_eater_power_list=power_list(
                "staff", row("*破壊*", 5, current=60, count=6)))
            observe_lists(policy, parse_snapshot(listed, cls.monrace))
            for raw in cls.raws:
                if raw["turn"] == until:
                    break
                board = policy.with_known_skill_exp(
                    parse_snapshot(_board(raw, level=level), cls.monrace))
                with contextlib.redirect_stdout(io.StringIO()):
                    key = policy.choose_key(board)
                if key:
                    policy.confirm_key_posted(key)
            cls.replayed[(level, until)] = (policy, next(r for r in cls.raws if r["turn"] == until))
        policy, raw = cls.replayed[(level, until)]
        return copy.deepcopy(policy), raw

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return key, policy.last_reason, board

    # -- (a) the ceiling floor, feeling in the no-ring band ------------------------------------

    def test_a_no_ring_feeling_on_the_ceiling_floor_ends_the_explore(self):
        policy, raw = self.replay(CEILING, KNOWN)
        key, reason, board = self.decide(policy, _board(raw, level=CEILING, feeling=10))
        # The floor's only known up stair has no walk on this map: the explored floor's way out
        # answers with Word of Recall (deep_stairs finds no stair a walk reaches).  Live (ceiling
        # 80F, the same board at 80F): ('3', 'explore').
        self.assertEqual(reason, explored_floor.REASON, key)
        self.assertEqual(policy._last_return_trigger, explored_floor.TRIGGER)
        self.assertTrue(ring_hunt.finished(policy, board))
        self.assertTrue(explored_floor.dead_end(policy, board))

    def test_a_the_up_stair_underfoot_is_taken(self):
        policy, raw = self.replay(CEILING, KNOWN)
        moved = _board(raw, level=CEILING, feeling=9, position=UP_STAIR)
        key, reason, board = self.decide(policy, moved)
        self.assertTrue(board.grid_at(board.player.position).has_up_stairs)
        # The stair cell is a corridor's dead end: ring_hunt.leave_key answers above the idle
        # layer's opportunistic search of its walls and the probes.
        self.assertEqual((key, reason), (UP_STAIRS_KEY, "deep-stairs:ascend"))

    # -- (b) feeling 7: explored as before ------------------------------------------------------

    def test_b_feeling_7_explores_as_before(self):
        policy, raw = self.replay(CEILING, KNOWN)
        key, reason, board = self.decide(policy, _board(raw, level=CEILING, feeling=7))
        self.assertFalse(ring_hunt.finished(policy, board))
        self.assertEqual(reason, "explore", key)

    # -- (c) feeling not known: as before -------------------------------------------------------

    def test_c_unknown_feeling_explores_as_before(self):
        policy, raw = self.replay(CEILING, KNOWN)
        key, reason, board = self.decide(policy, _board(raw, level=CEILING, feeling=0))
        self.assertFalse(ring_hunt.finished(policy, board))
        self.assertEqual(reason, "explore", key)

    # -- (d) no ceiling: nothing changes --------------------------------------------------------

    def test_d_a_character_meeting_the_25_row_is_no_hunter(self):
        with mock.patch.object(speed_valuation, "permanent_player_speed",
                               return_value=SPEED_GATE_MINIMUM):
            policy, raw = self.replay(CEILING, KNOWN)
            key, reason, board = self.decide(policy, _board(raw, level=CEILING, feeling=10))
            self.assertIsNone(getattr(policy, angband_cap.CEILING))
            self.assertFalse(angband_cap.ring_hunt_floor(policy, board))
            self.assertFalse(ring_hunt.finished(policy, board))
            self.assertNotEqual(reason, explored_floor.REASON, key)
            unchanged = self.replay(CEILING, KNOWN)[0]
            self.assertEqual(
                (key, reason), self.decide(unchanged, _board(raw, level=CEILING, feeling=0))[:2])

    # -- 80F under the ceiling: no ordinary loot fetched ----------------------------------------

    def test_the_recorded_80f_fetches_no_ordinary_loot_once_the_ring_is_ruled_out(self):
        policy, raw = self.replay(80, SEEK_LOOT)
        recorded = self.decide(copy.deepcopy(policy), raw)
        self.assertEqual(recorded[:2], ("3", "seek-loot"))
        key, reason, board = self.decide(policy, _board(raw, feeling=9))
        self.assertNotIn(reason, ("seek-loot", "pickup"), key)
        self.assertTrue(ring_hunt.finished(policy, board))
        self.assertFalse(explored_floor.dead_end(policy, board))  # 81F is admitted now
        self.assertNotIn(Position(21, 30), policy._loot_candidates(board))

    def test_the_pile_stood_on_is_still_picked_up(self):
        policy, raw = self.replay(80, PICKUP)
        self.assertEqual(self.decide(copy.deepcopy(policy), raw)[:2], ("gaa", "pickup"))
        key, reason, board = self.decide(policy, _board(raw, feeling=9))
        self.assertTrue(ring_hunt.finished(policy, board))
        self.assertEqual((key, reason), ("gaa", "pickup"))

    def test_the_public_answer(self):
        policy, raw = self.replay(CEILING, KNOWN)
        for feeling, expected in ((0, True), (7, True)):
            probe = copy.deepcopy(policy)
            board = parse_snapshot(_board(raw, level=CEILING, feeling=feeling), self.monrace)
            ring_hunt.observe(probe, board)
            self.assertIs(ring_hunt.floor_may_hold_ring(probe, board), expected, feeling)
        board = parse_snapshot(_board(raw, level=CEILING, feeling=9), self.monrace)
        ring_hunt.observe(policy, board)
        self.assertIs(ring_hunt.floor_may_hold_ring(policy, board), False)
        shallow = parse_snapshot(_board(raw, level=79, feeling=9), self.monrace)
        self.assertIsNone(ring_hunt.floor_may_hold_ring(policy, shallow))

    # -- the 2026-11-28 ceiling: 81-90F admitted, 91F refused -----------------------------------

    def test_81_to_90f_take_the_10_row_and_91f_the_25_row(self):
        policy, raw = self.replay(80, SEEK_LOOT)
        board = parse_snapshot(raw, self.monrace)
        angband_cap.observe(policy, board)
        self.assertEqual(angband_cap.speed_ceiling(policy, board), 90)
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), 90)
        for depth in (81, 85, 90):
            gaps = policy._missing_required_abilities(board, depth)
            self.assertFalse(gaps & {SPEED_GATE_LABEL, MID_SPEED_GATE_LABEL}, depth)
        self.assertIn(SPEED_GATE_LABEL, policy._missing_required_abilities(board, 91))
        self.assertTrue(angband_cap.climbing_floor((DUNGEON_ANGBAND, 91, 0), policy))
        self.assertFalse(angband_cap.climbing_floor((DUNGEON_ANGBAND, 90, 0), policy))
        self.assertTrue(angband_cap.capped_at(DUNGEON_ANGBAND, 91, policy))


class NoRingFeelingBandTest(unittest.TestCase):
    """ring_hunt's band against a re-reading of floor-events.cpp:111-262."""

    @staticmethod
    def game_feeling(rating):
        boost = ring_hunt.floor_rating_boost
        for feeling, end in ((2, 1000), (3, 800), (4, 600), (5, 400), (6, 300), (7, 200),
                             (8, 100), (9, 0)):
            if rating > boost(end):
                return feeling
        return 10

    def test_the_boost_is_the_games(self):
        boost = ring_hunt.floor_rating_boost
        self.assertEqual([boost(d) for d in (-5, 0, 100, 250, 1001, 5000)],
                         [0, 0, 15000, 75000, 1052051, 1052051])

    def test_a_lone_ring_reads_7_from_80f_down(self):
        for depth in range(80, 101):
            self.assertEqual(self.game_feeling(ring_hunt.floor_rating_boost(
                ring_hunt.ring_rating(depth))), 7, depth)
            self.assertEqual(ring_hunt.no_ring_feelings(depth), frozenset({8, 9, 10}), depth)

    def test_the_band_holds_whatever_else_the_floor_holds(self):
        # Every other term only adds: the feeling of a ring and anything is the ring's or lower.
        ring = ring_hunt.floor_rating_boost(ring_hunt.ring_rating(90))
        for extra in (0, 1, 50, 10_000, 900_000):
            self.assertNotIn(self.game_feeling(ring + extra), ring_hunt.no_ring_feelings(90))

    def test_shallower_the_item_level_term_widens_the_band(self):
        # floor-events.cpp:223: (80 - depth) * 10 above the ring's level; 70F: 350 > 300.
        self.assertEqual(ring_hunt.ring_rating(70), 350)
        self.assertEqual(ring_hunt.no_ring_feelings(70), frozenset({7, 8, 9, 10}))


if __name__ == "__main__":
    unittest.main()
