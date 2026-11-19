"""Structural check: attack power is compared per 10 game turns, through one reader.

Owner 2026-11-19: 「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりのダメージで評価して」
(「攻撃力の判定すべて」).  scripts/attack_time_lint.py flags a comparison that holds a per-action
attack figure no reader scaled; the comparisons there on 2026-11-19 (same-speed choices and kill
times in player actions) are its recorded baseline.
"""

import tests  # noqa: F401

import io
import unittest
from contextlib import redirect_stdout

import attack_time_lint


class AttackTimeLintTest(unittest.TestCase):
    def test_a_direct_per_action_comparison_is_found(self):
        source = (
            "def gate(policy, snapshot, race):\n"
            "    damage = attack_expectation.melee_against(policy, snapshot, race)\n"
            "    return damage >= 240\n")
        self.assertEqual(len(attack_time_lint.findings_in(source, "x.py")), 1)

    def test_the_policy_measure_compared_directly_is_found(self):
        source = ("def gate(self, snapshot, force):\n"
                  "    return self._strategy_measured_dps(snapshot, force) >= 50\n")
        self.assertEqual(len(attack_time_lint.findings_in(source, "x.py")), 1)

    def test_a_figure_through_the_reader_is_not(self):
        source = (
            "def gate(policy, snapshot, race):\n"
            "    damage = attack_expectation.per_10_game_turns(\n"
            "        policy, snapshot, attack_expectation.melee_against(policy, snapshot, race))\n"
            "    return damage >= 240\n")
        self.assertEqual(attack_time_lint.findings_in(source, "x.py"), [])

    def test_a_name_rebound_through_the_reader_is_not(self):
        source = (
            "def gate(policy, snapshot, race):\n"
            "    damage = attack_expectation.melee_against(policy, snapshot, race)\n"
            "    damage = attack_expectation.per_10_game_turns(policy, snapshot, damage)\n"
            "    return damage >= 240\n")
        self.assertEqual(attack_time_lint.findings_in(source, "x.py"), [])

    def test_a_sign_test_is_not(self):
        source = ("def gate(policy, snapshot, race):\n"
                  "    return attack_expectation.melee_against(policy, snapshot, race) > 0\n")
        self.assertEqual(attack_time_lint.findings_in(source, "x.py"), [])

    def test_the_repository_adds_nothing_to_the_baseline(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(attack_time_lint.main([]), 0)


if __name__ == "__main__":
    unittest.main()
