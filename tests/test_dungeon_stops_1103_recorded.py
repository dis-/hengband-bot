"""The dungeon-family loop-detected stops of the 2026-11-03 night (build 91357d2d0).

Every board is decided through the public choose_key on the recorded boards;
a step is posted through the production executor.  Nothing but the marked
seeds is constructed.  Fixtures: tests/extract_dungeon_stops_1103_fixtures.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import town_last_stand
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).with_name("fixtures") / "dungeon-stops-1103"


def fixture(name: str) -> dict:
    return json.loads(lzma.decompress((FIXTURES / name).read_bytes()))


class RecordedBoards(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def fresh_policy(self, first_board: dict, terrain: dict | None = None):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(first_board), policy._monrace_knowledge))
        # The captured process already held the skill list.
        policy.consume_skill_knowledge({
            "player": {"level": first_board["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        if terrain is not None:
            for name in ("known", "marked", "floor", "wall", "door", "rubble"):
                getattr(policy, f"_remembered_{name}_t").update(
                    tuple(cell) for cell in terrain[f"{name}_t"])
            policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
            policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        return policy

    @staticmethod
    def decide(policy, raw: dict):
        return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class TownAdjacentMeleeUnderErrandHold(RecordedBoards):
    """n1-c life-123, 2026-11-03 22:44 (no-wait:flee <-> town:kill-mob-approach).

    A 貧しげな傭兵 (5d8, one 1d10 blow) met a Lv18 character with three blows
    of a (+4,+13) pike while the home errand held the town.  Beside it,
    _town_kill_mob_key delegated to the ordinary melee rung, whose combat
    family the errand hold refused (_town_producer_entry asked
    _town_gate_exempt with the family alone); nothing answered, the idle WAIT
    was rewritten into no-wait:escape-scroll (all 15 Teleport scrolls were
    read over the visit), then into no-wait:flee, and at distance 2 the hunt
    walked back.  1 500 decisions later the loop guard stopped the bot.
    Decision row 21 is the first adjacent board of the visit.
    """

    ADJACENT_ROW = 21
    TRAVEL_BESIDE_MONSTER_ROW = 4

    def replay_to(self, last_row, raw):
        """The visit decided up to ``last_row`` as recorded; its key and board.

        DECLARED CONSTRUCTED: a722b754e2 walks a town move beside a visible
        monster (the game refuses the travel, n1-c life-122).  The earlier rows
        hold that off, and the fight on an interrupted travel's first board (town
        fights are survival, owner 2026-10-31), to stay on the recorded boards, which
        followed the travel; ``last_row`` itself decides on production code.
        """
        visit = Path(raw) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / "town-melee-policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / "town-melee-journal.jsonl.xz").read_bytes())))
        rows = journal(visit)
        scratch = Path(raw) / "scratch"
        scratch.mkdir()
        policy = restore(visit, scratch)
        for row, (recorded, supply) in enumerate(decisions(policy, visit, scratch)):
            board = supply()
            if row == last_row:
                return policy, rows, board, policy.choose_key(board)
            with mock.patch.object(HengbotPolicy, "_native_travel_refused_beside_monster",
                                   staticmethod(lambda _snapshot: False)),                     mock.patch.object(town_last_stand, "fights_beside",
                                      lambda _policy, _snapshot: False):
                key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            policy.confirm_key_posted(key)
        self.fail(last_row)

    def test_interrupted_travel_beside_a_hostile_is_fought_on_its_first_board(self):
        with TemporaryDirectory() as raw:
            policy, rows, board, key = self.replay_to(self.TRAVEL_BESIDE_MONSTER_ROW, raw)
        self.assertEqual((rows[self.TRAVEL_BESIDE_MONSTER_ROW]["key"],
                          rows[self.TRAVEL_BESIDE_MONSTER_ROW]["reason"]),
                         ("\x1b`n(.", "store:entry-interrupted-replan"))
        self.assertTrue(any(board.player.position.distance_to(monster.position) <= 1
                            for monster in board.visible_monsters))
        # a722b754e2 walked one step here and the next board fought.
        self.assertEqual((key, policy.last_reason), ("7", "melee"))

    def test_first_adjacent_board_is_fought(self):
        with TemporaryDirectory() as raw:
            policy, rows, board, key = self.replay_to(self.ADJACENT_ROW, raw)
            # 91357d2d0 read a Teleport scroll here.
            self.assertEqual((rows[self.ADJACENT_ROW]["key"], rows[self.ADJACENT_ROW]["reason"]),
                             ("rf", "no-wait:escape-scroll"))
        monster = next(iter(board.visible_monsters))
        self.assertEqual(monster.name, "貧しげな傭兵")
        self.assertEqual(board.player.position.distance_to(monster.position), 1)
        self.assertEqual((key, policy.last_reason), ("2", "melee"))
        self.post(policy, json.loads(rows[self.ADJACENT_ROW]["line"]), key,
                  json.loads(rows[self.ADJACENT_ROW + 1]["line"]))



class GivenUpDoorOnTheCommittedDescentRoute(RecordedBoards):
    """n1-c life-123, 2026-11-03 22:07 (approach-descent 'o4' repeated).

    The committed descent route ran through a locked door.  DOOR_OPEN_LIMIT
    gave the door up after three picks, but the committed path's step test
    (_is_step_open) still read a closed door as open, unlike rubble, so the
    route kept picking it ("鍵をはずせなかった。") until the loop guard.
    Fresh policy, stop's remembered terrain (DECLARED RECONSTRUCTED).
    """

    def test_door_is_given_up_after_its_limit(self):
        case = fixture("descent-door.json.xz")
        self.assertEqual(
            {(row["key"], row["reason"]) for row in case["rows"][4:]},
            {("o4", "approach-descent")})
        policy = self.fresh_policy(case["boards"][0], case["terrain"])
        at_door = [(raw, row) for raw, row in zip(case["boards"], case["rows"])
                   if (row["position"]["y"], row["position"]["x"]) == (30, 90)]
        keys = [self.decide(policy, raw) for raw, _row in at_door[:4]]
        self.assertEqual(keys[:3], ["o4", "o4", "o4"])
        self.assertIn((30, 89), policy._blocked_doors)
        self.assertNotEqual(keys[3], "o4")
        self.assertFalse(policy._nav_ledger.descent_path
                         and policy._nav_ledger.descent_path[0] == Position(30, 89))
        retry = self.fresh_policy(case["boards"][0], case["terrain"])
        key = self.decide(retry, at_door[0][0])
        self.post(retry, at_door[0][0], key, at_door[1][0])


class UnseenAreaDoesNotWriteOffTheFrontier(RecordedBoards):
    """n1-b life-306, 2026-11-03 23:04 (breakout:least-visited back and forth).

    In the Labyrinth at 12F an unseen attacker's half plane cut the corridor
    while the oscillation asked for the global frontier: its route search
    found no way through the temporary area and marked the maze's open
    corridor end (6, 11) as probed for the floor.  Later exploration had
    nothing left, and the player wandered the pocket beyond a corridor trap
    until the loop guard.  This whole floor replays decision for decision on
    91357d2d0 from a fresh policy.
    """

    DARK_BREATH_SEQUENCE = 25251

    def test_open_corridor_end_survives_and_is_walked_to(self):
        case = fixture("maze-frontier.json.xz")
        self.assertIn([6, 11], case["probed"])
        self.assertEqual(case["rows"][-1]["reason"], "breakout:least-visited")
        policy = self.fresh_policy(case["boards"][0])
        recorded = {row["turn"]: row for row in case["rows"]}
        key = None
        for raw in case["boards"]:
            key = self.decide(policy, raw)
            row = recorded[raw["turn"]]
            if row["decision_sequence"] == self.DARK_BREATH_SEQUENCE:
                # Owner 2026-11-10 (G1) 「飲まずに戦うか待つ」: a シャドウ・ハウンド's darkness
                # breath at HP 408/412 is a short blindness; the recorded Cure Critical
                # Wounds is kept and the player waits for sight (status_cure.short_blind_key).
                self.assertEqual((key, policy.last_reason), ("5", "blind:short-wait"))
            elif row["decision_sequence"] < 25258:
                self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))
        self.assertNotIn(Position(6, 11), policy._probed_frontiers)
        # The stop board: exploration still owns the floor.
        self.assertEqual((key, policy.last_reason), ("1", "explore"))
        self.post(policy, case["boards"][-2], key, case["boards"][-1])


class ConfinedWalkReachesTheStuckEscape(RecordedBoards):
    """n1-a life-474, 2026-11-03 21:13 (breakout:least-visited back and forth).

    Orc cave 23F, explored out, no down stairs known.  The oscillation branch
    answered a two-square nook with a local least-visited step ahead of the
    ladder that owns such a floor (secret walls, known stairs), and the
    forced nav:break-oscillation step reset the stuck streak at 42 of
    STUCK_ESCAPE_LIMIT 60, so the loop guard (40 confined decisions) stopped
    the bot first.  Stop's terrain, probed frontiers and visit counts
    (DECLARED RECONSTRUCTED); the streak starts at the 8 recorded searches.
    On the recorded boards the ladder now walks to the known up stairs.
    """

    def test_no_local_wander_and_the_known_stairs_are_walked_to(self):
        case = fixture("cave-stuck.json.xz")
        self.assertEqual(case["searches_before"], ["search"] * 8)
        self.assertIn("nav:break-oscillation", {row["reason"] for row in case["rows"]})
        policy = self.fresh_policy(case["boards"][0], case["terrain"])
        policy._probed_frontiers.update(Position(*cell) for cell in case["probed"])
        for row in case["visits"]:
            policy._visit_counts[Position(*row["key"])] = row["count"]
        # The live floor had open_frontiers 0 (decision log map_memory): its
        # two remembered doors no longer counted.
        policy._blocked_doors.update(tuple(cell) for cell in case["terrain"]["door_t"])
        policy._stuck_escape_streak = len(case["searches_before"])
        reasons, keys, streaks = [], [], []
        for raw in case["boards"]:
            keys.append(self.decide(policy, raw))
            reasons.append(policy.last_reason)
            streaks.append(policy._stuck_escape_streak)
        self.assertNotIn("breakout:least-visited", reasons)
        # The floor's own exit: the known up stairs at (60, 132), to the west.
        walk = reasons.index("stuck:seek-stairs")
        self.assertEqual(keys[walk], "4")
        # The forced step does not restart the count.
        forced = reasons.index("nav:break-oscillation")
        self.assertGreaterEqual(streaks[forced + 1], streaks[forced])
        self.post(policy, case["boards"][walk], keys[walk], case["boards"][walk + 1])


if __name__ == "__main__":
    unittest.main()
