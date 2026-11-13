"""n1-c life-207 2026-11-13 23:37: summoner:retreat and summoner:hold-reposition walked back
and forth between [41,106] and [41,107] until the loop detector stopped the bot.

Recorded: tests/fixtures/n1c-207-summoner-pingpong-1113/ (tests/extract_n1c_207_summoner_
pingpong_1113_fixture.py): the loop-detected capture of n1-c life-207 (Magic-Eater Lv46, Glass
castle 60F) and the policy checkpoint of the town arrival before the dive.  A summoning 水の鬼
(race 1132) awake 12 cells north.  The retreat out of the open room ('1' x3, '2') reached the
choke [41,107], which the 水の鬼 reaches; the hold (owner 2026-11-02 「撃たれる場所は待つポイント
として不適当なので撃たれない場所で待つ」) recorded it and stepped '4' toward an unshot choke
through [41,106], the open cell beside it, where the retreat chose [41,107] again (the nearest
choke, one step back) and stepped '6'.  25 round trips (the last 18 on these boards).

The cause: both owners record the cell they leave in the left-cell registry (the engagement
claim, left_cells ``shared``), but the retreat's own route search (``_summoner_retreat_route``)
did not read the registry, and it chose a covered cell the hold would not wait at.  The fix
makes the search read the registry (left_cells.refused) and choose, where it can, the cell the
hold keeps (summoner_wait.unfit_hold_point), so the retreat ends where the hold waits.

Every decision is the public ``choose_key`` of the restored arrival policy fed the recorded
boards in order.  DECLARED: the boards between the arrival and the floor (the town visit) are
not fed; the first boards of the floor decide differently from the recorded ones (the arrival
checkpoint does not hold the departure's state), and the recorded boards are still fed in order
(the game moved as recorded).  From the 水の鬼's first shot (turn 4911859) on, every decision
before the fix is the recorded one.  DECLARED CONSTRUCTED: the claim of the retreat's chosen
cell in ``test_a_left_cell_is_no_retreat_goal``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import left_cells
from hengbot.model import Position, parse_snapshot
from hengbot.summoner_wait import HOLD_REPOSITION_REASON, unfit_hold_point
from hengbot.town_arrival_checkpoint import POLICY_FILE
from replay_town_arrival import restore
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-207-summoner-pingpong-1113"
RETREAT = "summoner:retreat"
WATER_DEMON = 1132
HOLD_CELL = Position(41, 107)    # the shot choke the hold leaves
OPEN_CELL = Position(41, 106)    # the open cell beside it
FIRST_SHOT_TURN = 4911859
INTO_CHOKE_TURN = 4911906        # [40,107]: recorded '2' into [41,107]
FIRST_BACK_TURN = 4911912        # [41,106]: recorded '6' back to [41,107]

with gzip.open(FIXTURES / "boards.json.gz", "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
BOARDS = CASE["rows"]


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def recorded():
    return {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}


class Replay:
    """The restored arrival policy deciding the recorded boards in order."""

    def __init__(self, directory: Path):
        visit = directory / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        scratch = directory / "scratch"
        scratch.mkdir()
        self.policy = restore(visit, scratch)
        self.policy._monrace_knowledge.update(knowledge(CASE))
        self.decisions = {}

    def snapshot(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)

    def decide(self, raw):
        key = self.policy.choose_key(self.snapshot(raw))
        key = "" if key is None else str(key)
        if key:
            self.policy.confirm_key_posted(key)
        self.decisions[raw["turn"]] = (key, self.policy.last_reason)
        return key

    def run(self, until=None):
        for raw in BOARDS:
            if raw["turn"] == until:
                return raw
            self.decide(raw)
        return None


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_scene(self):
        rows = recorded()
        self.assertEqual(rows[INTO_CHOKE_TURN], ("2", RETREAT))
        fight = [raw for raw in BOARDS if raw["turn"] >= FIRST_SHOT_TURN and raw["turn"] in rows]
        backs = [raw["turn"] for raw in fight if here(raw) == OPEN_CELL
                 and rows[raw["turn"]] != ("", "loop-detected")]
        holds = [raw["turn"] for raw in fight if here(raw) == HOLD_CELL]
        self.assertEqual(len(backs), 17)
        self.assertEqual({rows[turn] for turn in backs}, {("6", RETREAT)})
        self.assertEqual({rows[turn] for turn in holds}, {("4", HOLD_REPOSITION_REASON)})
        demon = next(m for m in BOARDS[-1]["visible_monsters"] if m["race_id"] == WATER_DEMON)
        self.assertFalse(demon["asleep"])


class SummonerRetreatEndsAtTheHoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._directory = TemporaryDirectory()
        cls.replay = Replay(Path(cls._directory.name))
        cls.replay.run()

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def test_the_hold_still_leaves_the_shot_choke(self):
        rows = recorded()
        for raw in BOARDS:
            if raw["turn"] >= FIRST_SHOT_TURN and here(raw) == HOLD_CELL and raw["turn"] in rows:
                self.assertEqual(self.replay.decisions[raw["turn"]], ("4", HOLD_REPOSITION_REASON))

    def test_the_retreat_does_not_head_for_the_shot_choke(self):
        # Unfixed: ('2', 'summoner:retreat'), into [41,107], the nearest choke.
        self.assertEqual(self.replay.decisions[INTO_CHOKE_TURN], ("1", RETREAT))

    def test_the_retreat_never_steps_back_to_the_choke_the_hold_left(self):
        backs = [raw["turn"] for raw in BOARDS
                 if raw["turn"] >= FIRST_SHOT_TURN and here(raw) == OPEN_CELL]
        self.assertEqual(len(backs), 18)
        for turn in backs:
            # Unfixed: ('6', 'summoner:retreat') back to [41,107] (17 recorded, 1 loop-detected).
            self.assertEqual(self.replay.decisions[turn], ("4", RETREAT), turn)


class RetreatGoalTest(unittest.TestCase):
    """On the first board the retreat walked back, its chosen covered cell."""

    @classmethod
    def setUpClass(cls):
        cls._directory = TemporaryDirectory()
        cls.replay = Replay(Path(cls._directory.name))
        cls.raw = cls.replay.run(until=FIRST_BACK_TURN)

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def route(self, snapshot):
        policy = self.replay.policy
        hostiles = policy._strategic_hostiles(snapshot)
        summoners = [m for m in hostiles if m.can_summon and not m.asleep]
        with left_cells.survival_walks(policy):  # the combat layer's walk
            return policy._summoner_retreat_route(snapshot, summoners, hostiles)

    def test_the_retreat_goal_is_a_cell_the_hold_keeps(self):
        policy = self.replay.policy
        snapshot = self.replay.snapshot(self.raw)
        self.assertIn(HOLD_CELL, left_cells.refused(policy, snapshot))  # the hold's record
        goal, step = self.route(snapshot)
        # Unfixed: ([41,107], [41,107]): the choke the hold left, one step back.
        self.assertNotEqual(goal, HOLD_CELL)
        self.assertNotEqual(step, HOLD_CELL)
        self.assertFalse(unfit_hold_point(policy, snapshot, goal))

    def test_a_left_cell_is_no_retreat_goal(self):
        """DECLARED CONSTRUCTED: the cell the retreat chose is claimed as left (the
        engagement claim every retreating owner makes); the search takes another."""
        policy = self.replay.policy
        snapshot = self.replay.snapshot(self.raw)
        goal, _step = self.route(snapshot)
        saved = (set(policy._engagement_owned_avoid_cells), set(policy._engagement_avoid_cells))
        try:
            policy._claim_engagement_avoid_cells((goal,), snapshot=snapshot,
                                                 owner="threat:avoid-engagement")
            other, _ = self.route(snapshot)
            self.assertIsNotNone(other)
            self.assertNotEqual(other, goal)
        finally:
            policy._engagement_owned_avoid_cells, policy._engagement_avoid_cells = saved


if __name__ == "__main__":
    unittest.main()
