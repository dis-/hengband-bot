"""Recorded Q31 and Q2 boards: the emergency recall hold on a ONCE quest floor.

Owner 2026-11-03: 「回復の手段がある間は回復か休憩を選び、帰還は作戦の撤退の線以下か、
逃げ手段が尽きた時だけにします。」

Source: tests/fixtures/once-quest-recall-20261103.json.gz (n1-c life-116,
tests/extract_once_quest_recall_fixture.py).  Decision 4142 (turn 1986976) read
Word of Recall at HP 174/354 with no enemy in view and 12 Teleport scrolls; the
placement sweep's walk reached the low-HP walk gate, whose only heal candidates
were 9 Cure Critical (not a heal kind on Q31).  The recall failed the ONCE quest.

Owner 2026-11-03 (later): 「敵が見えず、攻撃も受けていない間は帰還を読まず、薬か休憩で回復します。」

Boards, knowledge and decision rows are measured.  DECLARED CONSTRUCTED: the
HP of the abort-line board and the removed scrolls of the exhausted board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import REST_MACRO
from hengbot.quest_knowledge import load_quest_knowledge
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_input_executor import prompt_screen


FIXTURE = Path(__file__).with_name("fixtures") / "once-quest-recall-20261103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
INCIDENT = CASE["boards"][0]
RECALL_READ = ("re", "emergency:recall")
RECALL_READ_QUEST_FAIL = "emergency:recall-quest-fail"
TELEPORT_SVALS = {8, 9}  # Phase Door, Teleportation
TVAL_SCROLL = 70
TVAL_POTION = 75
Q2_FIXTURE = Path(__file__).with_name("fixtures") / "q2-residual-dark-placement-20261102.json.gz"
with gzip.open(Q2_FIXTURE, "rt", encoding="utf-8") as _stream:
    Q2_CASE = json.load(_stream)
Q2_BOARD = Q2_CASE["boards"][5]
with gzip.open(Path(__file__).with_name("fixtures") / "q2-patrol-breeder-20261103.json.gz", "rt",
               encoding="utf-8", errors="surrogateescape") as _stream:
    WORM_CASE = json.load(_stream)
Q2_HEAL_SVALS = {36, 37}  # Cure Critical, Healing
COMMAND_PROMPTS = {"q": "どの薬を飲みますか? ", "r": "どの巻物を読みますか? ", "R": "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &"}


def decide(board):
    # Primed on the board itself: no hit observed, as on the recorded board.
    policy = loops.new_policy(dict(CASE, boards=[board]), CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge[31] = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))[31]
    key = str(policy.choose_key(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)))
    return key, policy.last_reason


class OnceQuestRecallRecordedTest(unittest.TestCase):
    def test_no_enemy_above_the_abort_line_rests_instead_of_recalling(self):
        recorded = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
        self.assertEqual(recorded[INCIDENT["turn"]], RECALL_READ)
        self.assertEqual(INCIDENT["visible_monsters"], [])
        self.assertEqual(decide(INCIDENT), (REST_MACRO, "rest"))

        at_abort_line = copy.deepcopy(INCIDENT)
        at_abort_line["player"]["hp"] = at_abort_line["player"]["max_hp"] // 4
        self.assertEqual(decide(at_abort_line), (REST_MACRO, "rest"))

        exhausted = copy.deepcopy(INCIDENT)
        exhausted["inventory"] = [
            item for item in exhausted["inventory"]
            if not (item["tval"] == TVAL_SCROLL and item["sval"] in TELEPORT_SVALS)]
        self.assertEqual(decide(exhausted)[1], RECALL_READ[1])


def q2_board(hp, *, scrolls=True, potions=False, source=None):
    """A recorded Q2 board (default: the empty up-stair cell) at ``hp``, potions spent."""
    board = copy.deepcopy(source or Q2_BOARD)
    board["player"]["hp"] = hp
    board["inventory"] = [
        item for item in board["inventory"]
        if (potions or not (item["tval"] == TVAL_POTION and item["sval"] in Q2_HEAL_SVALS))
        and (scrolls or not (item["tval"] == TVAL_SCROLL and item["sval"] in TELEPORT_SVALS))]
    return board


def with_worm(board):
    """DECLARED CONSTRUCTED: a recorded worm's row, three cells from the player."""
    worm = copy.deepcopy(WORM_CASE["boards"][-1]["visible_monsters"][0])
    worm.update(y=board["player"]["y"] + 3, x=board["player"]["x"])
    board["visible_monsters"] = [worm]
    return board


class QuestRecallHoldRecordedTest(nokey.PostedKey):
    """Q2, abort_conditions {"hp_ratio": 0.30, "allowed": false}, recall carried.

    Source: tests/fixtures/q2-residual-dark-placement-20261102.json.gz (n1-b life-295,
    warrior Lv22, HP 430/430, no enemy in view, 15 Teleportation, 10 Recall), the board
    on the up-stair cell (1,4), where a strategy that allows a withdrawal leaves, and
    tests/fixtures/q2-patrol-breeder-20261103.json.gz (n1-c life-120, 36 worms in view).
    No capture holds an emergency recall read on Q1, Q2 or Q34 (nor a board of Q1 or
    Q34 carrying both scrolls), so the HP, the removed potions and scrolls, the previous
    board of a hit and the allowed flag of the withdrawal case are DECLARED CONSTRUCTED.
    The hold reads the strategy data alone: Q2 stands for the other quests.
    """

    def drive(self, board, *, previous=None, allowed=None):
        # Primed on the previous board (a hit), else the board itself (no hit).
        policy = loops.new_policy(
            dict(Q2_CASE, boards=[previous or board], home=None), Q2_CASE["skill"],
            monraces=WORM_CASE["monraces"])
        policy._quest_knowledge[2] = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))[2]
        if allowed is not None:
            policy._quest_strategies[2] = replace(
                policy._quest_strategies[2],
                abort_conditions=dict(policy._quest_strategies[2].abort_conditions, allowed=allowed))
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)))
        self.post(policy, board, key, screens=[
            prompt_screen(text) for command, text in COMMAND_PROMPTS.items() if key.startswith(command)])
        return key, policy.last_reason

    def test_recorded_board_is_a_quest_walk_on_the_up_stair(self):
        self.assertEqual((Q2_BOARD["player"]["y"], Q2_BOARD["player"]["x"]), (1, 4))
        self.assertEqual((Q2_BOARD["player"]["hp"], Q2_BOARD["player"]["max_hp"]), (430, 430))
        self.assertEqual(Q2_BOARD["visible_monsters"], [])
        self.assertTrue(self.drive(q2_board(430))[1].startswith("quest-strategy:q2-"))

    def test_above_the_line_with_a_scroll_rests_instead_of_recalling(self):
        self.assertEqual(self.drive(q2_board(130)), (REST_MACRO, "rest"))  # 30.2%

    def test_no_scroll_above_the_line_reads_recall(self):
        self.assertEqual(self.drive(q2_board(200, scrolls=False))[1], RECALL_READ[1])

    def test_at_and_below_the_line_with_no_enemy_recovers(self):
        rest = (REST_MACRO, "rest")
        self.assertEqual(self.drive(q2_board(129)), rest)  # exactly 30%
        self.assertEqual(self.drive(q2_board(100, scrolls=False)), rest)
        self.assertEqual(self.drive(q2_board(100, potions=True))[1], "item:heal")

    def test_no_enemy_on_a_strategy_that_allows_a_withdrawal_stays_on_the_stair(self):
        self.assertEqual(self.drive(q2_board(100), allowed=True), (REST_MACRO, "rest"))

    def test_below_the_line_a_visible_enemy_keeps_the_read(self):
        worms = WORM_CASE["boards"][-1]
        board = q2_board(60, scrolls=False, source=worms)  # a lethal 40-point hit
        previous = q2_board(100, scrolls=False, source=worms)
        self.assertEqual(self.drive(board, previous=previous)[1], RECALL_READ_QUEST_FAIL)

    def test_below_the_line_a_visible_enemy_never_withdraws_where_none_is_allowed(self):
        board, previous = with_worm(q2_board(100)), with_worm(q2_board(120))
        self.assertEqual(self.drive(board, previous=previous)[1], "quest-strategy:q2-fire")

    def test_below_the_line_an_unseen_hit_keeps_the_read(self):
        board = q2_board(100, scrolls=False, source=Q2_CASE["boards"][0])
        previous = q2_board(120, scrolls=False, source=Q2_CASE["boards"][0])
        board["messages"] = ["何かに噛まれた。"]
        self.assertEqual(self.drive(board, previous=previous)[1], RECALL_READ_QUEST_FAIL)


if __name__ == "__main__":
    unittest.main()
