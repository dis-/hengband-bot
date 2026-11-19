"""A begun loot walk holds against the approach to *Destruction* (n1-c life-217, Angband 80F).

n1-c life-217 (Magic-Eater Lv 42), Angband 80F, 2026-11-19 12:40, loop-detected (build
bot-23df91ff8).  蛇たちの父『イグ』 (T1, asleep) was known by telepathy at (14,23) behind rock.
seek-loot was walking to the rod at (16,46) (decision 11046 at (15,37)).  At (14,36) Yig was 13
off, the use due, and destruction_loot, asked to begin its fetch, continued the ordinary walk
instead (loot_walk ``fetch_yield_key``): '9' to (13,37).  At (13,37) Yig was 14 off, the use not
due, and the approach (threat_tiers ``approach_key``) stepped '1' straight back without asking
the walk.  About 20 rounds; the ping-pong guard escalated, livelock:recall-escape read the
Recall (turn 4546103), and the loop detector stopped the bot 86 game turns into the countdown.

Owner 2026-11-18 (maintainability Q3, 「命の危険が無ければ取り終える」: 品を取りに歩き始めたら、即死の
見込み・見える強敵が出ない限り、取り終えるまでほかの歩きに譲らない、上限40回は残す) and 2026-11-17
(「価値の高い品は先に拾ってから撃つ」): the approach's step is a walk (reasons.WALK), so it now asks
the begun loot walk first (loot_walk ``approach_yield_key``); the use itself is not held.  The
driver's loop stop waits for a Recall read on the floor within its longest delay
(recall_wait_reach ``countdown_running``).

Recorded (tests/fixtures/n1c-217-approach-loot-20261119.json.gz, see
tests/extract_n1c_217_approach_loot_1119_fixture.py): the 4 player-turn boards 4546126-4546136,
decided through one policy's ``choose_key``.  DECLARED RECONSTRUCTED: the absorbed *Destruction*
list row (22 charges at 95%: the capture keeps the racial power list only; decision 11015 used
it and the (14,36) rows count it among the escape means), and the ordinary loot walk in
progress toward (16,46) (loot_walk ``note_walk``, as decision 11046 noted it; the capture's
boards begin after it).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot import destruction_loot, loot_walk, me_capability, recall_wait_reach, threat_tiers
from hengbot.cli import _loop_stop_due
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-approach-loot-20261119.json.gz"
NORTH, SOUTH = Position(13, 37), Position(14, 36)
ROD = Position(16, 46)
YIG = 814
RECALL_READ_TURN = 4546103
STOP_TURN = 4546189


class ApproachLootRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.directories = []

    @classmethod
    def tearDownClass(cls):
        for directory in cls.directories:
            directory.cleanup()

    def policy(self, *, walking: bool):
        directory = TemporaryDirectory()
        self.directories.append(directory)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(policy, 0)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        if walking:
            policy._loot_target = ROD
            loot_walk.note_walk(policy, first, ROD, "seek-loot", None)
        return policy

    def board(self, policy, index):
        return policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(self.data["boards"][index]), self.monrace))

    def replay(self, policy):
        rows = []
        for index in range(len(self.data["boards"])):
            board = self.board(policy, index)
            key = policy.choose_key(board)
            rows.append((board.player.position, key, policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
        return rows

    def test_the_record_alternates_the_approach_and_seek_loot(self):
        rows = [row for row in self.data["decisions"] if row["turn"] >= 4546080
                and row["reason"] in (threat_tiers.APPROACH_REASON, "seek-loot")]
        for row in rows:
            cell = Position(row["position"]["y"], row["position"]["x"])
            if row["reason"] == "seek-loot":
                self.assertEqual((cell, row["key"]), (SOUTH, "9"), row)
                self.assertEqual(row["loot_target"], {"y": ROD.y, "x": ROD.x}, row)
            elif cell == NORTH:
                self.assertEqual(row["key"], "1", row)
        self.assertGreaterEqual(sum(row["reason"] == "seek-loot" for row in rows), 15)
        self.assertEqual(self.data["decisions"][-1]["reason"], "loop-detected")

    def test_the_use_is_due_south_and_not_north(self):
        policy = self.policy(walking=False)
        for index, cell in ((0, NORTH), (1, SOUTH)):
            board = self.board(policy, index)
            self.assertEqual(board.player.position, cell)
            strong = threat_tiers._sensed_strong(policy, board)[1]
            yig = next(monster for monster in strong if monster.race_id == YIG)
            self.assertEqual(threat_tiers.destruction_use.in_sure_radius(board, yig), cell == SOUTH)

    def test_the_approach_walks_on_with_no_loot_walk_begun(self):
        """Owner 2026-11-10 「積極的に*破壊*で消しにいく」: unchanged where nothing is fetched."""
        policy = self.policy(walking=False)
        position, key, reason = self.replay(policy)[0]
        self.assertEqual((position, key, reason), (NORTH, "1", threat_tiers.APPROACH_REASON))

    def test_the_begun_loot_walk_is_not_taken_over_by_the_approach(self):
        """The record's flip: north the approach stepped '1' back into (14,36); now the walk to
        the rod goes on east from both cells."""
        rows = self.replay(self.policy(walking=True))
        for position, key, reason in rows:
            self.assertEqual(reason, "seek-loot", (position, key, reason))
            self.assertNotEqual(key, "1", (position, key, reason))
        self.assertEqual(rows[0][:2], (NORTH, "6"))
        self.assertEqual(rows[1][:2], (SOUTH, "9"))

    def test_the_remembered_approach_holds_for_the_loot_walk_as_well(self):
        """With the T1s lost from detection (n1-b life-377's remembered approach) the begun walk
        is continued the same way.  The next north board with its T1s taken out of detection."""
        policy = self.policy(walking=False)
        first = self.board(policy, 0)
        key = policy.choose_key(first)
        self.assertEqual((key, policy.last_reason), ("1", threat_tiers.APPROACH_REASON))
        policy.confirm_key_posted(key)
        policy._loot_target = ROD
        loot_walk.note_walk(policy, first, ROD, "seek-loot", None)
        raw = copy.deepcopy(self.data["boards"][2])
        strong = {monster.index for monster in threat_tiers._sensed_strong(policy, first)[1]}
        raw["detected_monsters"] = [row for row in raw["detected_monsters"] if row["index"] not in strong]
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        self.assertEqual(board.player.position, NORTH)
        self.assertEqual(threat_tiers._sensed_strong(policy, board)[1], [])
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("6", "seek-loot"))

    def test_the_hold_is_bounded_by_the_fetch_bound(self):
        """Owner Q3 「上限40回は残す」: past destruction_loot's bound the approach steps."""
        policy = self.policy(walking=True)
        board = self.board(policy, 0)
        destruction_loot._memory(policy, board)["decisions"] = destruction_loot.DECISIONS_MAX
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("1", threat_tiers.APPROACH_REASON))

    def test_the_loop_stop_waits_for_the_recall_countdown(self):
        floor = tuple(self.data["boards"][0]["floor"][name]
                      for name in ("dungeon_id", "level", "quest_id"))
        policy = SimpleNamespace()

        def observe(turn, recalling):
            snapshot = SimpleNamespace(floor_key=floor, turn=turn,
                                       player=SimpleNamespace(recalling=recalling))
            recall_wait_reach.observe(policy, snapshot)
            return snapshot

        observe(RECALL_READ_TURN, False)
        observe(RECALL_READ_TURN + 3, True)
        cells = [(floor, NORTH.y, NORTH.x), (floor, SOUTH.y, SOUTH.x)] * 20
        at_stop = observe(STOP_TURN, True)
        self.assertTrue(recall_wait_reach.countdown_running(policy, at_stop))
        self.assertFalse(_loop_stop_due(cells, 40, policy, at_stop))
        past = observe(RECALL_READ_TURN + 10 * (recall_wait_reach.DELAY_MAX_TICKS + 2), True)
        self.assertFalse(recall_wait_reach.countdown_running(policy, past))
        self.assertTrue(_loop_stop_due(cells, 40, policy, past))

    def test_an_unseen_read_holds_no_loop_stop(self):
        floor = (1, 80, 0)
        policy = SimpleNamespace()
        snapshot = SimpleNamespace(floor_key=floor, turn=STOP_TURN,
                                   player=SimpleNamespace(recalling=True))
        recall_wait_reach.observe(policy, snapshot)
        self.assertFalse(recall_wait_reach.countdown_running(policy, snapshot))


if __name__ == "__main__":
    unittest.main()
