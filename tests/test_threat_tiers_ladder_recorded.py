"""Threat tiers plan step 5 (docs/threat-tiers-design.md 3.1, 5; OQ-2): 即死 on the shared ladder.

Owner 2026-11-07, OQ-2: 「作戦中と物資を使って倒しに行くときは次の1手のみ。それ以外は3ターン基準も
使う」.  The 1-turn 即死 (the next action's p95 at the monsters' adjusted speed plus the observed
unseen loss) joins ``_emergency_item``'s ``lethal``; outside the plans and the supplied fights the
3-turn ``predicted >= hp`` and the other conditions stay, so the new test only adds escapes.  In a
committed supplied fight (today's committed unique fight), which the 3-turn test does not abort,
the 1-turn test does.

Acceptance (design step 5): over the recorded death lives no board that escaped before now stays,
and no board that fought before now flees unless the 1-turn test holds there.  Recorded: the death
lives of n1-c 077, 099, 103 and 123 and n1-a 475's summons, the ones the 1-turn test fires on (12
boards in all); on each the decision with the test equals the decision without it.
``decided_with_and_without`` (tests/test_threat_tiers_plans_recorded.py) decides a copy of the
policy with the test on every board where its read held inside the recorded decision.
DECLARED CONSTRUCTED where a test makes the recorded fight a committed unique fight (it says so).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from unittest.mock import patch

from hengbot.policy import ConservativePolicy
from tests import test_threat_tiers_recorded as recorded
from tests.test_threat_tiers_plans_recorded import EMERGENCY_TELEPORT, decided_with_and_without

LIVES = {
    # The observed loss counts only with an unseen attacker evidenced (design 3.1).
    # n1-c 099: 8 since n1-a life-514 (2026-11-12): an awake caster reaches the player over grids
    # the board has not shown (owner 2026-11-08 「未知のマスを壁と見ない」), so the 1-turn test
    # also reads 691548, 691667 and 691679, each already the existing ``lethal``'s teleport.
    "death-n1c-077-1101.json.gz": 3, "death-n1c-099-1102.json.gz": 8,
    "death-n1c-103-1102.json.gz": 1, "death-n1c-123-1104.json.gz": 1,
    # n1-a 475's summons: 1 since 2026-11-12 (t3-survival-1112 D: the game's spell odds put
    # 2038858's next-action p95 below the HP).
    "summon-response-n1a-475-1104.json.gz": 1,
}
for _name in LIVES:
    recorded.CASES.setdefault(_name, recorded.load(_name))


def ONE_TURN(death):
    """The shared ladder acts on the 1-turn p95 test (the paralyser and hallucination labels
    have their own rungs there)."""
    return death.next_action


def life(name):
    case = recorded.CASES[name]
    raws = recorded.boards(case)
    return (lambda: recorded.d57.loops.new_policy(dict(case, boards=raws), case["skill"],
                                                  monraces=case.get("monraces"))), raws


def committed():
    """DECLARED CONSTRUCTED: the recorded fight taken as a committed unique fight."""
    return patch.object(ConservativePolicy, "_committed_unique_fight_viable",
                        lambda self, snapshot, hostiles: True)


class AcceptanceTest(unittest.TestCase):
    def test_no_recorded_death_board_changes_outside_the_plans(self):
        for name, fired in LIVES.items():
            with self.subTest(life=name):
                answers = decided_with_and_without(*life(name), fires=ONE_TURN)
                self.assertEqual(len(answers), fired)
                for turn, (before, after, death) in answers.items():
                    self.assertTrue(death.next_action, turn)
                    # Already the existing ``lethal``'s answer (or a filter's after it, as the
                    # torch thrown on n1-c 077's 442514): the new test adds no escape here.
                    self.assertEqual(before, after, turn)


class CommittedFightTest(unittest.TestCase):
    """In a committed supplied fight only the 1-turn test aborts it (OQ-2, design 3.4)."""

    def answers(self, name):
        with committed():
            return decided_with_and_without(*life(name), fires=ONE_TURN)

    def test_the_committed_fight_gives_way_on_the_n1c_099_boards(self):
        answers = self.answers("death-n1c-099-1102.json.gz")
        # 691696: HP 77/310, the next action's p95 337; the committed fight left it to the late
        # no-wait escape, the 1-turn test now reads the emergency ladder's teleport.
        before, after, death = answers[691696]
        self.assertEqual(before[1], "no-wait:escape-scroll")
        self.assertEqual(after[1], EMERGENCY_TELEPORT)
        self.assertGreaterEqual(death.next_action_p95, 77)
        changed = {turn for turn, (before, after, _death) in answers.items() if before != after}
        # 691548, 691667, 691679: the 1-turn test reads them since n1-a life-514's line of fire
        # over unknown grids (see LIVES); the committed fight gives way there too.
        self.assertEqual(changed, {691548, 691667, 691679, 691696, 691704, 691716, 691725})
        for turn in changed:
            self.assertEqual(answers[turn][1][1], EMERGENCY_TELEPORT, turn)

    def test_the_committed_fight_gives_way_on_the_n1a_475_summons(self):
        answers = self.answers("summon-response-n1a-475-1104.json.gz")
        for turn in (2038863,):  # 2038858: no longer 即死 (see LIVES)
            before, after, _death = answers[turn]
            self.assertEqual(before[1], "summons:recall")
            self.assertEqual(after[1], EMERGENCY_TELEPORT)


if __name__ == "__main__":
    unittest.main()
