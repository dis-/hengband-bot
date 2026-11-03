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
from hengbot import cli, once_quest_recall
from hengbot.policy_constants import ONCE_QUEST_TICK_REST_REASON, REST_MACRO
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
TICK_REST = (REST_MACRO, ONCE_QUEST_TICK_REST_REASON)
POISONED = {"poisoned": True}
CUT = {"cut": True, "cut_rank": 1}
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
        self.assertEqual(decide(exhausted), (REST_MACRO, "rest"))


def q2_board(hp, *, scrolls=True, potions=False, source=None):
    """A recorded Q2 board (default: the empty up-stair cell) at ``hp``, potions spent."""
    board = copy.deepcopy(source or Q2_BOARD)
    board["player"]["hp"] = hp
    board["inventory"] = [
        item for item in board["inventory"]
        if (potions or not (item["tval"] == TVAL_POTION and item["sval"] in Q2_HEAL_SVALS))
        and (scrolls or not (item["tval"] == TVAL_SCROLL and item["sval"] in TELEPORT_SVALS))]
    return board


def with_status(board, status):
    board["player"]["status"].update(status)
    return board


def with_worm(board):
    """DECLARED CONSTRUCTED: a recorded worm's row, three cells from the player."""
    worm = copy.deepcopy(WORM_CASE["boards"][-1]["visible_monsters"][0])
    worm.update(y=board["player"]["y"] + 3, x=board["player"]["x"])
    board["visible_monsters"] = [worm]
    return board


class Q2Driver(nokey.PostedKey):
    def new_policy(self, primed_on):
        policy = loops.new_policy(
            dict(Q2_CASE, boards=[primed_on], home=None), Q2_CASE["skill"],
            monraces=WORM_CASE["monraces"])
        policy._quest_knowledge[2] = load_quest_knowledge(Path("C:/hengband/lib/edit/quests"))[2]
        return policy

    def drive(self, board, *, previous=None, allowed=None):
        # Primed on the previous board (a hit), else the board itself (no hit).
        policy = self.new_policy(previous or board)
        if allowed is not None:
            policy._quest_strategies[2] = replace(
                policy._quest_strategies[2],
                abort_conditions=dict(policy._quest_strategies[2].abort_conditions, allowed=allowed))
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)))
        self.post(policy, board, key, screens=[
            prompt_screen(text) for command, text in COMMAND_PROMPTS.items() if key.startswith(command)])
        return key, policy.last_reason


class QuestRecallHoldRecordedTest(Q2Driver):
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

    def test_recorded_board_is_a_quest_walk_on_the_up_stair(self):
        self.assertEqual((Q2_BOARD["player"]["y"], Q2_BOARD["player"]["x"]), (1, 4))
        self.assertEqual((Q2_BOARD["player"]["hp"], Q2_BOARD["player"]["max_hp"]), (430, 430))
        self.assertEqual(Q2_BOARD["visible_monsters"], [])
        self.assertTrue(self.drive(q2_board(430))[1].startswith("quest-strategy:q2-"))

    def test_above_the_line_with_a_scroll_rests_instead_of_recalling(self):
        self.assertEqual(self.drive(q2_board(130)), (REST_MACRO, "rest"))  # 30.2%

    def test_no_scroll_above_the_line_with_no_enemy_rests(self):
        self.assertEqual(self.drive(q2_board(200, scrolls=False)), (REST_MACRO, "rest"))

    def test_no_scroll_above_the_line_with_an_enemy_reads_recall(self):
        worms = WORM_CASE["boards"][-1]
        board = q2_board(100, scrolls=False, source=worms)  # 36%, a lethal 100-point hit
        previous = q2_board(200, scrolls=False, source=worms)
        self.assertEqual(self.drive(board, previous=previous)[1], RECALL_READ_QUEST_FAIL)

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


class QuestRecallTickRestRecordedTest(Q2Driver):
    """Owner 2026-11-03: 「敵がいないなら毒切り傷でも休む。」 The same boards.

    DECLARED CONSTRUCTED as above, plus the poison, cut and confusion flags and each tick's
    HP loss.  The game's interrupted rest is not simulated: the stop guards are fed
    one board per tick, each a later turn on the same cell.
    """

    TICKS = 45  # more than the cell guard's window of 40 decisions

    def tick(self, status, *, scrolls=True, hp=100, loss=5):
        board = with_status(q2_board(hp, scrolls=scrolls), status)
        previous = with_status(q2_board(hp + loss, scrolls=scrolls), status)
        return board, previous

    def test_a_tick_rests_and_spends_no_scroll(self):
        for status in (POISONED, CUT):
            board, previous = self.tick(status)
            self.assertEqual(self.drive(board, previous=previous), TICK_REST)

    def test_a_tick_with_no_scroll_rests(self):
        for status in (POISONED, CUT):
            board, previous = self.tick(status, scrolls=False)
            self.assertEqual(self.drive(board, previous=previous), TICK_REST)

    def test_a_tick_with_a_potion_drinks(self):
        board = with_status(q2_board(100, potions=True), POISONED)
        previous = with_status(q2_board(105, potions=True), POISONED)
        self.assertEqual(self.drive(board, previous=previous)[1], "item:heal")

    def test_a_tick_while_confused_keeps_its_wait(self):
        board, previous = self.tick({**POISONED, "confused": True})
        self.assertEqual(self.drive(board, previous=previous)[1], "emergency:wait")

    def test_an_unseen_hit_during_a_tick_is_still_a_threat(self):
        for hp in (100, 200):  # below the line, and above it with a scroll (the hold stands)
            board, previous = self.tick(POISONED, hp=hp)
            board["messages"] = ["何かに噛まれた。"]
            self.assertNotEqual(self.drive(board, previous=previous), TICK_REST, hp)

    def test_a_walk_from_a_rung_above_the_navigator_spends_no_scroll(self):
        # DECLARED CONSTRUCTED: no recorded rung walks here, so the gate is asked directly.
        board, previous = self.tick(POISONED)
        policy = self.new_policy(previous)
        snapshot = parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)
        policy.choose_key(snapshot)
        self.assertEqual(policy._low_hp_walk_gate(snapshot, "6"), REST_MACRO)
        self.assertEqual(policy.last_reason, ONCE_QUEST_TICK_REST_REASON)

    def test_an_enemy_above_the_line_holds_only_with_a_scroll(self):
        # DECLARED CONSTRUCTED: the scroll is read first on every rung but the guardian's
        # teleport-only one, so the hold is asked directly.
        for scrolls, expected in ((True, True), (False, False)):
            board = with_worm(q2_board(200, scrolls=scrolls))
            policy = self.new_policy(board)
            snapshot = parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)
            policy.choose_key(snapshot)
            self.assertEqual(once_quest_recall.held(policy, snapshot), expected, scrolls)

    def test_ticks_in_a_row_reach_no_stop(self):
        first = with_status(q2_board(self.TICKS + 100), POISONED)
        policy = self.new_policy(first)
        stalled, signature, position = 0, None, None
        for tick in range(self.TICKS):
            board = copy.deepcopy(first)
            board["player"]["hp"] -= tick + 1
            board["turn"] += 10 * (tick + 1)
            snapshot = parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            self.assertEqual((key, policy.last_reason), TICK_REST, tick)
            self.post(policy, board, key, screens=[prompt_screen(COMMAND_PROMPTS["R"])])
            policy.confirm_key_posted(key)
            command = cli._command_state_signature(snapshot, policy.last_reason, key)
            stalled = cli._advance_stalled_command_count(
                stalled, signature=command, previous_signature=signature)
            signature = command
            self.assertEqual(stalled, 0, tick)
            self.assertFalse(cli._cell_loop_guard_applies(snapshot, policy.last_reason, position), tick)
            position = snapshot.player.position
        self.assertEqual(policy._stuck_escape_streak, 0)


if __name__ == "__main__":
    unittest.main()
