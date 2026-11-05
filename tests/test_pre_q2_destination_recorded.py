"""Owner 2026-11-06 「開いた中で条件を満たす階へ」, before Q2 with the Yeek cave conquered.

「深さの条件を満たす開いたダンジョンのうち、一番深い階へ行きます。迷宮も候補です。条件を
満たす所がなければイークの洞穴のままです。」

n1-b life-318 (Magic-Eater Lv24, HP 318), visit of 2026-11-06 00:51: the Yeek cave is
conquered, Q2 is not taken, and it read 'rgb', town:recall-to-yeek-cave, at 00:52:13
though it holds Orc cave 19F.  Replayed through choose_key, the same visit reads 'rgc'.

Fixture: tests/fixtures/pre-q2-destination-1106 (tests/extract_pre_q2_destination_fixture.py).
DECLARED CONSTRUCTED: every test but the first takes the recorded read board and changes
what its name says (abilities, opened dungeons, conquests, Q2, the valve's counters).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
from pathlib import Path
import unittest

from hengbot import random_quest_hold
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE
from hengbot.policy_constants import QUEST_STATUS_FINISHED
from hengbot.spectator import spectator_recall_destination
from test_me_stops_1103_recorded import Visit


FIXTURE = Path(__file__).with_name("fixtures") / "pre-q2-destination-1106"
ORC_CAVE, LABYRINTH, FOREST, CASTLE, MOUNTAIN, CHAMELEON = 3, 4, 7, 12, 14, 18
DEEPEST = random_quest_hold.DEEPEST_OPEN_REASON
CLOSED = random_quest_hold.TARGET_REASON
EVERY_ABILITY_TO_49F = ("free_action", "resist_conf", "resist_chaos", "resist_neth")


class PreQ2DestinationRecordedTest(unittest.TestCase):
    def setUp(self):
        self.visit = Visit(FIXTURE)
        self.addCleanup(self.visit.close)
        self.policy = self.visit.policy
        # The recorded visit adds Home records; this keeps them to this test.
        self.policy._home_disposal.history_path = self.visit.scratch / "home-history.jsonc"
        self.rows = list(self.visit.rows)
        self.recorded, supply = self.rows[-1]
        self.read_board = supply()

    def board(self, **changes):
        return replace(self.read_board, **changes)

    def with_abilities(self, *names):
        board = self.read_board
        return replace(board, player=replace(
            board.player, abilities=board.player.abilities | frozenset(names)))

    def target(self, board):
        self.policy.choose_key(board)
        return self.policy._target_dungeon_id, self.policy._target_dungeon_reason

    def test_the_visit_reads_recall_for_orc_cave_19f(self):
        self.assertEqual((self.recorded["key"], self.recorded["reason"]),
                         ("rgb", "town:recall-to-yeek-cave"))
        reads = []
        for _row, supply in self.rows:
            board = supply()
            key = self.policy.choose_key(board)
            if self.policy.last_reason.startswith("town:recall-to"):
                reads.append((str(key), self.policy.last_reason, board))
            self.visit.post(key)
        key, reason, board = reads[0]
        # The letter c is the third row of the prompt, entered_dungeon_ids (1, 2, 3, ...).
        self.assertEqual((key, reason), ("rgc", "town:recall-to-alt-dungeon"))
        self.assertEqual(board.entered_dungeon_ids[2], ORC_CAVE)
        self.assertEqual(self.policy._town_recall_destination(board), ("alt-dungeon", ORC_CAVE))
        destination = spectator_recall_destination(self.policy, board)
        self.assertEqual(
            (destination["dungeon_id"], destination["depth"], destination["reason"]),
            (ORC_CAVE, 19, DEEPEST))

    def test_the_depth_conditions_choose_the_floor(self):
        # Castle 20F asks free action, Mountain 25F also confusion.  Chameleon 30F stays
        # refused whatever is worn, and Forest 15F and Angband are never candidates.
        for abilities, expected in (
                ((), ORC_CAVE),
                (("resist_conf",), ORC_CAVE),
                (("free_action",), CASTLE),
                (("free_action", "resist_conf"), MOUNTAIN),
                (EVERY_ABILITY_TO_49F, MOUNTAIN)):
            with self.subTest(abilities=abilities):
                self.assertEqual(self.target(self.with_abilities(*abilities)), (expected, DEEPEST))

    def test_the_choice_is_the_deepest_recall_depth_not_bounded_by_the_yeek_depth(self):
        board = self.board(dungeon_recall_depths={
            **self.read_board.dungeon_recall_depths, ORC_CAVE: 12, LABYRINTH: 16})
        self.assertEqual(self.target(board), (LABYRINTH, DEEPEST))
        self.assertEqual(self.policy._dungeon_entry_depth(board, LABYRINTH, via_recall=True), 16)

    def test_a_character_with_the_yeek_cave_open_stays_on_its_path(self):
        board = self.board(conquered_dungeon_ids=(), yeek_cave_conquered=False)
        self.policy._guardian_fight_viable = lambda snapshot, info: False
        self.assertEqual(self.target(board), (DUNGEON_YEEK_CAVE, CLOSED))

    def test_without_a_passing_floor_it_stays_in_the_yeek_cave(self):
        board = self.board(entered_dungeon_ids=(
            DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, FOREST, CASTLE, MOUNTAIN, CHAMELEON))
        self.assertEqual(self.target(board), (DUNGEON_YEEK_CAVE, CLOSED))

    def test_a_chosen_floor_that_stops_passing_goes_back_to_the_yeek_cave(self):
        self.assertEqual(self.target(self.with_abilities("free_action")), (CASTLE, DEEPEST))
        only_castle = (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, CASTLE)
        self.assertEqual(self.target(self.board(entered_dungeon_ids=only_castle)),
                         (DUNGEON_YEEK_CAVE, CLOSED))

    def test_the_labyrinth_is_a_candidate_until_conquered(self):
        opened = (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, LABYRINTH)
        self.assertEqual(self.target(self.board(entered_dungeon_ids=opened)), (LABYRINTH, DEEPEST))
        conquered = (DUNGEON_YEEK_CAVE, LABYRINTH)
        self.assertEqual(
            self.target(self.board(entered_dungeon_ids=opened, conquered_dungeon_ids=conquered)),
            (DUNGEON_YEEK_CAVE, CLOSED))

    def test_a_guardian_floor_the_kit_cannot_pass_is_not_chosen(self):
        self.policy._guardian_fight_viable = lambda snapshot, info: False
        depths = {**self.read_board.dungeon_recall_depths, ORC_CAVE: 22}
        board = replace(
            self.with_abilities("free_action", "resist_conf"), dungeon_recall_depths=depths,
            entered_dungeon_ids=(DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, ORC_CAVE, LABYRINTH))
        self.assertEqual(self.target(board), (LABYRINTH, DEEPEST))

    def test_a_dive_keeps_the_target_it_left_with(self):
        self.assertEqual(self.target(self.with_abilities("free_action")), (CASTLE, DEEPEST))
        random_quest_hold.settle_target(self.policy, self.board(town_flag=False))
        self.assertEqual(self.policy._target_dungeon_id, CASTLE)
        self.assertEqual(self.target(self.board()), (ORC_CAVE, DEEPEST))

    def stepped_down(self, **counters):
        """The valve on a board back from Orc cave 19F, and the target it leaves."""
        self.assertEqual(self.target(self.board()), (ORC_CAVE, DEEPEST))
        back = self.board(recall_dungeon_id=ORC_CAVE, recall_depth=19)
        for name, count in counters.items():
            setattr(self.policy, name, count)
        return back, self.target(back)

    def test_over_extended_dives_step_down_and_do_not_bounce_back(self):
        back, target = self.stepped_down(_target_empty_dives=3)
        self.assertEqual(target, (LABYRINTH, "over_extended_dives"))
        self.assertEqual(self.policy._last_overextended_depth, 19)
        self.assertEqual(self.target(back), (LABYRINTH, "over_extended_dives"))
        # Nothing shallower is left: the streak restarts and the target stays.
        self.policy._target_empty_dives = 3
        self.assertEqual(self.target(back), (LABYRINTH, "over_extended_dives"))
        self.assertEqual(self.policy._target_empty_dives, 0)

    def test_dives_without_depth_progress_step_down_and_stay(self):
        back, target = self.stepped_down(_no_depth_progress_dives=5)
        self.assertEqual(target, (LABYRINTH, "no_depth_progress"))
        self.assertEqual(self.target(back), (LABYRINTH, "no_depth_progress"))

    def test_q2_resolved_gives_angband_back(self):
        self.assertEqual(self.target(self.board()), (ORC_CAVE, DEEPEST))
        board = self.board()
        row = replace(next(iter(board.quests.values())),
                      id=random_quest_hold.GATING_QUEST_ID, status=QUEST_STATUS_FINISHED)
        resolved = replace(board, quests={**board.quests, row.id: row})
        self.assertEqual(self.target(resolved), (DUNGEON_ANGBAND, "angband_recall_unlocked"))
        # Without the Angband recall the ordinary selection starts from the Yeek cave again.
        self.assertEqual(self.target(self.board()), (ORC_CAVE, DEEPEST))
        locked = replace(resolved, angband_recall_unlocked=False)
        self.assertEqual(self.target(locked), (DUNGEON_YEEK_CAVE, "initial_yeek_cave"))

    def test_a_mining_set_still_walks_to_the_yeek_cave(self):
        self.assertEqual(self.target(self.board()), (ORC_CAVE, DEEPEST))
        self.policy._fundraising_mode = "mine"
        self.assertEqual(self.policy._active_dungeon_target(), DUNGEON_YEEK_CAVE)


if __name__ == "__main__":
    unittest.main()
