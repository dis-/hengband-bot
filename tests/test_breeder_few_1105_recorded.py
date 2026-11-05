"""breeder-few-1105: few breeders in view are judged by the kills of the window.

Owner 2026-11-05 「少ない時は倒した数で判断」, the option: 「見える数が5体未満なら、窓の中で
倒せていれば続けます。5体以上なら今の比較です。」

Recorded: n1-b life-316 in Q2 下水道 (tests/fixtures/q2-live-20261105.json.gz).  The window
that opened at turn 1064948 with two blue icky things ended at 1065213 with three, and the
next board read Recall at full HP.  The log holds 11 kill lines of the race in that window; 8
on these decision boards, because the fixture keeps each board's own messages (the live
process merged a skipped board's into the next: the decision log's row of 1065056 has it).

DECLARED CONSTRUCTED: FewBreedersEdgesTest repeats the recorded board of 1065213 with its
blue icky things cut or copied to the count, its messages replaced and its turn advanced;
the skill row is the n1-c life-098 row of the breeder-swarm fixture; the recorded boards do
not follow from the keys decided here (the test reads the window, which depends on the
boards only).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hengbot import policy_state
from hengbot.breeder_stalemate import FEW_BREEDERS, FLEE_AFTER_PLAYER_ACTIONS
from hengbot.policy import ConservativePolicy
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_breeder_swarm_1102_recorded as swarm
from tests.test_q2_live_1105_recorded import RESTART, new_policy

BLUE = 252
LATCHED_TURN = 1065213
RECALL = "breeder-breakthrough:recall"
QUEST_FLOOR = (0, 15, 2)
ROWS = [row for row in RESTART if row["board"]["turn"] <= LATCHED_TURN]
AFTER = next(row for row in RESTART if row["board"]["turn"] > LATCHED_TURN)
TEMPLATE = ROWS[-1]["board"]
KILL = "青ベトベトは死んだ。"


def blues(count, action, messages=()):
    """DECLARED CONSTRUCTED: the last recorded board of the window with ``count`` blues."""
    raw = copy.deepcopy(TEMPLATE)
    blue = next(m for m in raw["visible_monsters"] if m["race_id"] == BLUE)
    others = [m for m in raw["visible_monsters"] if m["race_id"] != BLUE]
    # Indices are stable per slot, so a lower count is a blue gone and a higher one a new blue.
    raw["visible_monsters"] = others + [
        dict(blue, index=800 + i, y=blue["y"] + i % 3, x=blue["x"] + i // 3)
        for i in range(count)]
    raw["grid_map"]["cells"] = [cell for cell in raw["grid_map"]["cells"] if cell.get("m") is None]
    raw["turn"] += 10 * action
    raw["messages"] = list(messages)
    return raw


def opened_window(start, messages=()):
    """A policy whose window has just opened on the race: a blue gone with exp up."""
    first = blues(start, 1)
    first["player"]["exp"] -= 1
    policy = new_policy({"board": first})
    for raw in (first, blues(start - 1, 2, messages)):
        loops.decide(policy, raw)
    return policy


class RecordedWindowTest(swarm.PostedSwarmKey):
    def run_recorded(self):
        policy = new_policy(ROWS[0])
        for row in ROWS:
            loops.decide(policy, copy.deepcopy(row["board"]))
        return policy

    def test_the_recorded_window_went_from_two_to_three(self):
        counts = {row["board"]["turn"]: sum(m["race_id"] == BLUE for m in row["board"]["visible_monsters"])
                  for row in ROWS}
        self.assertEqual((counts[1064948], counts[LATCHED_TURN]), (2, 3))
        self.assertEqual(sum(KILL in row["board"]["messages"] or "青ベトベトを葬り去った。" in row["board"]["messages"]
                             for row in ROWS if 1064948 < row["board"]["turn"] <= LATCHED_TURN), 8)

    def test_window_3_does_not_latch_and_the_next_board_reads_no_recall(self):
        policy = self.run_recorded()
        self.assertIsNone(policy._breeder_breakthrough_floor)
        # The next window opens at the three in view, with no kill of its own yet.
        self.assertEqual((policy._breeder_engagement_start_count, policy._breeder_engagement_actions,
                          policy._breeder_engagement_killed), (3, 0, False))
        key = loops.decide(policy, copy.deepcopy(AFTER["board"]))
        self.assertEqual(AFTER["reason"], RECALL)
        self.assertNotEqual(policy.last_reason, RECALL, key)
        self.post(policy, AFTER["board"], key)


class FewBreedersEdgesTest(swarm.PostedSwarmKey):
    def end_of_window(self, start, end, messages, *, opening=(), middle=None):
        """Open at ``start``; ``messages`` on the middle board; end at ``end``."""
        policy = opened_window(start, opening)
        self.assertEqual(policy._breeder_engagement_start_count, start)
        for action in range(3, 3 + FLEE_AFTER_PLAYER_ACTIONS):
            words = messages if action == 10 else ()
            count = end if action == 2 + FLEE_AFTER_PLAYER_ACTIONS else start
            if action == 10 and middle is not None:
                count = middle
            loops.decide(policy, blues(count, action, words))
        return policy

    def assert_abandoned(self, policy):
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)
        following = blues(3, 40)
        key = loops.decide(policy, following)
        self.assertEqual(policy.last_reason, RECALL)
        self.post(policy, following, key)

    def test_few_and_no_kill_is_abandoned(self):
        self.assert_abandoned(self.end_of_window(2, 3, ()))

    def test_few_and_a_kill_goes_on(self):
        policy = self.end_of_window(2, 3, ("青ベトベトを葬り去った。 <x2>",))
        self.assertIsNone(policy._breeder_breakthrough_floor)
        self.assertEqual(policy._breeder_engagement_start_count, 3)

    def test_the_first_attacks_kill_is_in_the_window(self):
        policy = self.end_of_window(2, 3, (), opening=(KILL,))
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_a_kill_of_the_last_one_in_view_counts(self):
        policy = self.end_of_window(2, 3, (KILL,), middle=0)
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_the_combat_personality_line_counts(self):
        policy = self.end_of_window(2, 3, ("せっかくだから青ベトベトを葬り去った。",))
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_a_restart_keeps_the_kill(self):
        with tempfile.TemporaryDirectory() as folder:
            record = Path(folder) / "floor.json"

            class Restarted(ConservativePolicy):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._breeder_floor_record_path = record

            policy = opened_window(2)
            policy._breeder_floor_record_path = record
            for action in range(3, 12):
                loops.decide(policy, blues(2, action, (KILL,) if action == 5 else ()))
            # A new process: the CLI points the record path before its first board.
            with mock.patch.object(loops, "ConservativePolicy", Restarted):
                restarted = new_policy({"board": blues(2, 12)})
            self.assertEqual(restarted._breeder_engagement_start_count, 2)
            self.assertIs(restarted._breeder_engagement_killed, True)
            for action in range(12, 3 + FLEE_AFTER_PLAYER_ACTIONS):
                count = 3 if action == 2 + FLEE_AFTER_PLAYER_ACTIONS else 2
                loops.decide(restarted, blues(count, action))
            self.assertIsNone(restarted._breeder_breakthrough_floor)
            self.assertEqual(restarted._breeder_engagement_start_count, 3)

    def test_a_checkpoint_from_before_this_rule_decides_on(self):
        policy = opened_window(2)
        del policy.__dict__["_breeder_engagement_killed"]
        policy_state.normalize_policy_state(policy)
        for action in range(3, 3 + FLEE_AFTER_PLAYER_ACTIONS):
            loops.decide(policy, blues(3, action))
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)

    def test_the_kill_is_not_carried_into_the_next_window(self):
        policy = self.end_of_window(2, 3, (KILL,))
        for action in range(30, 30 + FLEE_AFTER_PLAYER_ACTIONS):
            loops.decide(policy, blues(3, action))
        self.assert_abandoned(policy)

    def test_another_race_or_an_unseen_kill_is_no_kill(self):
        for line in ("大蜘蛛は死んだ。", "何かは死んだ。", "何かを殺した。"):
            with self.subTest(line):
                self.assertEqual(
                    self.end_of_window(2, 3, (line,))._breeder_breakthrough_floor, QUEST_FLOOR)

    def test_five_or_more_that_grew_is_abandoned_with_kills(self):
        self.assert_abandoned(self.end_of_window(4, FEW_BREEDERS, (KILL,)))

    def test_four_at_the_end_is_few(self):
        self.assertIsNone(self.end_of_window(3, FEW_BREEDERS - 1, (KILL,))._breeder_breakthrough_floor)

    def test_five_or_more_that_fell_goes_on_without_a_kill(self):
        policy = self.end_of_window(7, FEW_BREEDERS, ())
        self.assertIsNone(policy._breeder_breakthrough_floor)

    def test_a_floor_without_a_plan_keeps_the_comparison(self):
        # The 11-03 rule: no plan, three in view at both ends, with a kill.
        first = blues(3, 1)
        first["floor"]["quest_id"] = 0
        policy = new_policy({"board": first})
        for action in range(1, 2 + FLEE_AFTER_PLAYER_ACTIONS):
            raw = blues(3, action, (KILL,))
            raw["floor"]["quest_id"] = 0
            loops.decide(policy, raw)
        self.assertIsNotNone(policy._breeder_breakthrough_floor)
        self.assertIsNone(policy._breeder_engagement_race)


if __name__ == "__main__":
    unittest.main()
