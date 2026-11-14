"""The two-escape return counts an escape only when a cause had a line of fire (owner 2026-11-14).

Owner 2026-11-14 (verbatim): 「テレポートを使い逃げにカウントするのは射線が通っている場合のみに
したい。」  line_of_fire owns the reading: the game's projectable (range 18) over the board, an
unknown grid stopping it; every counted escape reason is counted by it, and the latches that start
the return on the second escape before it is counted ask it too.  The owner's 「数える」 of the
same day keeps summons:leave-teleport and no-wait:escape-scroll counted (line_of_fire.PROOF_REASONS).

Recorded: tests/fixtures/escape-los-1114.jsonl.gz (tests/extract_escape_los_1114_fixture.py),
n1-c life-207, ガラスの城 60F.  Each case is one fresh policy replaying the case's boards in order
through the public ``choose_key``; the count is the real observation's on the next board.  The
recorded boards do not show the keys' effects (a teleport read stays where it was), so the replay
reads the same escape again on the next board: each case reads the count's step across one board.
DECLARED CONSTRUCTED: the depth gate walled off (``_missing_required_abilities`` empty), as
tests/test_deaths_1109_recorded: the fresh process does not have the live one's resistances read
and would start a return (``resist-gap``) the live one did not; the live character used its
absorbed *Destruction* on several of these boards, which the fresh process has not listed.

* 1654, 7836354 (16:53:59, the live board decided sensed-t1:approach-destruction): Teleportation
  with no hostile in view, the 即死 test's causes (ニカデーモン, レッサー・バルログ) detected beyond
  unknown grids -- no line of fire, not counted, and with one escape counted already it latches
  no return.  The old reading (``_may_project``) reads unknown grids open and finds lines.
* 1654, 7836363: the レッサー・バルログ in view three cells off -- counted.
* 1654, 7836366 (16:53:59, the live emergency:teleport of the brief): nothing in view, but the
  レッサー・バルログ detected four cells off on known glass floor (GLASS_FLOOR: LOS and PROJECTION,
  TerrainDefinitions.jsonc id 199) has the line -- counted, as the game's projectable reads it.
* 1654, 7836462 (16:54:01): テレサ beside the player -- counted.
* 1629, 7730821 (16:29:42): the sensed-T1 leave from the ヘル・ワイアーム with no line -- not counted;
  7730828: the same leave with the wyrm five cells off on known glass floor -- counted.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import line_of_fire, threat_tiers
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import GridState, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "escape-los-1114.jsonl.gz"
FIXTURE_SHA256 = "bd7a897acf9b3bb2a5f604dcc053cda87023989d3ec762d72f23f2a8e1fdbab3"
EDIT = Path(r"C:\hengband\lib\edit")
BALROG, HELL_WYRM = 940, 1192


def no_depth_gate():
    return mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                             lambda self, *args, **kwargs: frozenset())


class EscapeLineOfFireRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.cases = {}
        for row in rows:
            cls.cases.setdefault(row["role"], []).append(row["board"])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def policy(self):
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        return policy

    def decide(self, policy, raw):
        snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
        key = policy.choose_key(snapshot)
        if key:
            policy.confirm_key_posted(key)
        return snapshot

    def step(self, role, turn, *, before=None):
        """(policy, the board of ``turn`` as decided, its reason, the count after that board's
        observation, after the next board's).  ``before``: run on the policy just before ``turn``
        is decided."""
        boards = self.cases[role]
        index = next(i for i, raw in enumerate(boards) if raw["turn"] == turn)
        policy = self.policy()
        with no_depth_gate():
            for raw in boards[:index]:
                self.decide(policy, raw)
            if before is not None:
                before(policy)
            snapshot = self.decide(policy, boards[index])
            reason = policy.last_reason
            counted = policy._dive_emergencies  # the previous board's escape counted already
            self.decide(policy, boards[index + 1])
        return policy, snapshot, reason, counted, policy._dive_emergencies

    def hostile(self, snapshot, race):
        return [m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                if m.hostile and m.race_id == race]

    def test_a_teleport_with_no_cause_in_the_line_of_fire_is_no_escape(self):
        policy, snapshot, reason, before, after = self.step("1654", 7836354)
        self.assertEqual(reason, "emergency:teleport")
        self.assertFalse([m for m in snapshot.visible_monsters if m.hostile])
        causes = line_of_fire.instant_death_causes(policy, snapshot)
        self.assertTrue(causes)
        self.assertFalse(any(line_of_fire.in_fire(policy, snapshot, m) for m in causes))
        # The old reading: unknown grids open, so the projection reaches through them.
        self.assertTrue(any(policy._may_project(snapshot, m.position, snapshot.player.position)
                            for m in causes))
        self.assertEqual((before, after), (0, 0))

    def test_a_teleport_counted_nowhere_latches_no_return(self):
        def one_counted(policy):
            policy._dive_emergencies = 1  # DECLARED CONSTRUCTED: one escape counted on 60F
            self.assertFalse(policy._returning_to_town)
        policy, _, reason, before, after = self.step("1654", 7836354, before=one_counted)
        self.assertEqual(reason, "emergency:teleport")
        self.assertEqual((before, after), (1, 1))
        self.assertNotEqual(policy._last_return_trigger, "emergency-repeat")
        self.assertFalse(policy._returning_to_town)

    def test_damage_from_an_unseen_attacker_stands_for_the_line(self):
        """DECLARED CONSTRUCTED: an unseen attacker's loss on 7836354 (``unseen_correction``),
        the owner's 「数える」 of the same day: the damage reaching the player is the proof."""
        with mock.patch("hengbot.threat_projection.unseen_correction", lambda *args: 120):
            _, _, reason, before, after = self.step("1654", 7836354)
        self.assertEqual(reason, "emergency:teleport")
        self.assertEqual(after, before + 1)

    def test_a_balrog_in_view_counts(self):
        _, snapshot, reason, before, after = self.step("1654", 7836363)
        self.assertEqual(reason, "emergency:teleport")
        self.assertTrue([m for m in snapshot.visible_monsters if m.race_id == BALROG])
        self.assertEqual(after, before + 1)

    def test_a_detected_balrog_with_an_open_line_counts(self):
        policy, snapshot, reason, before, after = self.step("1654", 7836366)
        self.assertEqual(reason, "emergency:teleport")
        self.assertFalse([m for m in snapshot.visible_monsters if m.hostile])
        board = getattr(policy, line_of_fire.BOARD)  # the next board's; the balrog's line:
        balrog = next(m for m in self.hostile(snapshot, BALROG) if m.position == Position(36, 85))
        self.assertTrue(line_of_fire.in_fire(policy, snapshot, balrog))
        self.assertIsNot(board, snapshot)
        self.assertEqual(after, before + 1)

    def test_tessa_beside_the_player_counts(self):
        _, snapshot, reason, before, after = self.step("1654", 7836462)
        self.assertEqual(reason, "emergency:teleport")
        self.assertTrue(any(m.position.distance_to(snapshot.player.position) <= 1
                            for m in snapshot.visible_monsters if m.hostile))
        self.assertEqual(after, before + 1)

    def test_the_sensed_wyrm_counts_only_with_its_line(self):
        policy, snapshot, reason, before, after = self.step("1629", 7730821)
        self.assertEqual(reason, "sensed-t1:teleport")
        wyrm = self.hostile(snapshot, HELL_WYRM)
        self.assertTrue(wyrm)
        self.assertFalse(any(line_of_fire.in_fire(policy, snapshot, m) for m in wyrm))
        self.assertEqual(after, before)
        policy, snapshot, reason, before, after = self.step("1629", 7730828)
        self.assertEqual(reason, "sensed-t1:teleport")
        wyrm = self.hostile(snapshot, HELL_WYRM)
        self.assertEqual([m.position for m in wyrm], [Position(26, 50)])
        self.assertTrue(line_of_fire.in_fire(policy, snapshot, wyrm[0]))
        self.assertEqual(after, before + 1)


class LineOfFireReadingTest(unittest.TestCase):
    """The reading itself on a constructed corridor (DECLARED CONSTRUCTED)."""

    class Board:
        def __init__(self, grids, player):
            self.grids = grids
            self.player = mock.Mock(position=player)
            self.visible_monsters = ()
            self.detected_monsters = ()

        def grid_at(self, position):
            return self.grids.get(position)

    @staticmethod
    def floor(y, x, *, known=True, wall=False):
        return GridState(position=Position(y, x), known=known, passable=not wall,
                         wall=wall, has_monster=False, has_down_stairs=False,
                         has_up_stairs=False, unsafe=False, allows_los=not wall)

    def policy(self):
        return HengbotPolicy()

    def corridor(self, length, overrides=None):
        grids = {Position(5, x): self.floor(5, x) for x in range(0, length + 1)}
        for x, grid in (overrides or {}).items():
            grids[Position(5, x)] = grid(5, x)
        return self.Board(grids, Position(5, 0))

    def test_an_open_corridor_reaches_within_the_range(self):
        board = self.corridor(18)
        self.assertTrue(line_of_fire.reaches(self.policy(), board, Position(5, 18)))

    def test_the_range_is_the_games(self):
        board = self.corridor(19)
        self.assertFalse(line_of_fire.reaches(self.policy(), board, Position(5, 19)))

    def test_the_sensed_leave_reads_the_games_range(self):
        """The sensed-T1 leave's note (threat_tiers.note_line_of_fire): a T1 nineteen cells down
        an open corridor has no line of fire (the old straight line read no range limit)."""
        policy = self.policy()
        board = self.corridor(19)
        far = mock.Mock(position=Position(5, 19))
        self.assertTrue(policy._has_line_of_fire(board, far.position, board.player.position))
        threat_tiers.note_line_of_fire(policy, board, [far])
        self.assertFalse(getattr(policy, line_of_fire.RECORD))
        threat_tiers.note_line_of_fire(policy, board, [mock.Mock(position=Position(5, 18))])
        self.assertTrue(getattr(policy, line_of_fire.RECORD))

    def test_an_unknown_grid_stops_the_line(self):
        board = self.corridor(6, {3: lambda y, x: self.floor(y, x, known=False)})
        self.assertFalse(line_of_fire.reaches(self.policy(), board, Position(5, 6)))
        del board.grids[Position(5, 3)]
        self.assertFalse(line_of_fire.reaches(self.policy(), board, Position(5, 6)))

    def test_a_wall_stops_the_line(self):
        board = self.corridor(6, {3: lambda y, x: self.floor(y, x, wall=True)})
        self.assertFalse(line_of_fire.reaches(self.policy(), board, Position(5, 6)))

    def test_the_proof_reasons_count_without_a_line(self):
        policy = self.policy()
        board = self.corridor(2)
        line_of_fire.new_board(policy, board)
        line_of_fire.note(policy, board, [])
        self.assertFalse(line_of_fire.counted(policy, "emergency:teleport"))
        for reason in ("summons:leave-teleport", "no-wait:escape-scroll"):
            self.assertTrue(line_of_fire.counted(policy, reason))


if __name__ == "__main__":
    unittest.main()
