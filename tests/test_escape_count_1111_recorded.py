"""The escape count is per floor, and an escape whose cause a *Destruction* removed no longer
counts (C1 of the 50F plan, owner 2026-11-11).

Owner 2026-11-11 (verbatim): 「確認したいのが、*破壊*で対処した分を帰還カウントに数えていないか。
*破壊*すれば階の脅威は減るので滞在しても問題はない。」 and, answering how: 「逃げは階が変われば
リセット。逃げた原因を後から*破壊*で排除した場合もリセット。」  Every escape is still counted
(owner 11-09 「全部の逃げを数える」) and the second returns (escape_count).

Boards: tests/fixtures/deaths-1109.json.xz, n1-b life-355 (Angband 80F, 2026-11-09 04:29), the
harness of tests/test_deaths_1109_recorded.py: one fresh policy replays the recorded boards in
order through the public ``choose_key``; every escape is counted by the real observation and
every *Destruction* is the policy's own decision.  4229931: thirteen awake Chiron locusts
(race 1087) read 即死 and Teleportation is read (escape 1, cause the locusts).  4229938: the
absorbed *Destruction* (with it listed) or the sensed-T1 Teleportation (escape 2, without it).
DECLARED CONSTRUCTED: as tests/test_deaths_1109_recorded A, the staff list without *Destruction*
and the depth gate walled off where named; the flash message 「燃えるような閃光が発生した！」 on
the board after a use (the live character read Teleportation there); the floor change of the
per-floor case (the boards from 4229938 on one floor up, as a Teleport Level would land); the
locust board again after the escapes with the HP at 2000 (so it is no 即死 board and the ladder
takes *Destruction*, test_deaths_1109 C raises the HP the same way) and its flash board without
the locusts; the active Word of Recall (``player.recalling``) of the last case.

Owner 2026-11-13 「射線にT1が入っていない=感知しただけはカウントしない」: on 4229938 no awake
hostile known (the five 1244, the two 746, the 812) has a line of fire to the player at (22,53),
so that sensed-T1 Teleportation is no escape (threat_tiers.counts_as_escape;
test_a_sensed_t1_out_of_the_line_of_fire_is_no_escape).  The C1 cases need it to count: they
declare it in the line of fire (``in_line_of_fire``), the case the 11-13 rule still counts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest import mock

from hengbot import destruction_use, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
import tests.test_deaths_1109_recorded as deaths
from tests.test_deaths_1109_recorded import DESTRUCTION_NAME, DESTRUCTION_REASON, at_depth, from_turn

LIFE = "life-355"
LOCUST_BOARD, SECOND_BOARD, LATCH_BOARD, RECALL_BOARD = 4229931, 4229938, 4229941, 4229948
LOCUST = 1087


def flash(raw):
    raw["messages"] = list(raw.get("messages") or []) + [destruction_use.FLASH[0]]


def in_line_of_fire():
    """DECLARED CONSTRUCTED: the sensed T1 left on 4229938 reads as in the line of fire."""
    def note(policy, snapshot, strong):
        setattr(policy, threat_tiers.IN_LINE_OF_FIRE, True)
    return mock.patch.object(threat_tiers, "note_line_of_fire", note)


def no_depth_gate():
    return mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                             lambda self, *args, **kwargs: frozenset())


class EscapeCountRecordedTest(deaths.DeathsRecordedHarness):
    def listed(self, policy, raw):
        """The displayed lists again, *Destruction* included (as the replay shows them)."""
        for kind, (_, rows) in sorted(self.payload[LIFE]["lists"].items(),
                                      key=lambda entry: entry[1][0]):
            shown = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                         _magic_eater_power_list={"kind": kind, "rows": rows})
            observe_lists(policy, parse_snapshot(shown, self.races))

    def locusts_destroyed(self, *, recalling=False):
        """Two escapes latch the return; then the locusts of the first are destroyed."""
        with in_line_of_fire():
            policy, answers = self.replay(LIFE, LATCH_BOARD, without=(DESTRUCTION_NAME,))
        self.assertEqual([answers[turn][2] for turn in (LOCUST_BOARD, SECOND_BOARD)],
                         ["emergency:teleport", "sensed-t1:teleport"])
        self.assertEqual((policy._dive_emergencies, policy._last_return_trigger),
                         (2, "emergency-repeat"))
        raw = self.board(LIFE, LOCUST_BOARD)
        raw["turn"] = LATCH_BOARD + 4
        raw["player"]["hp"] = raw["player"]["max_hp"] = 2000
        self.listed(policy, raw)
        self.assertEqual(self.decide(policy, raw)[1], DESTRUCTION_REASON)
        after = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        after["visible_monsters"] = [m for m in after["visible_monsters"]
                                     if m["race_id"] != LOCUST]
        flash(after)
        if recalling:
            after["player"]["recalling"] = True
        self.decide(policy, after)
        return policy

    def test_a_new_floor_starts_the_count_again(self):
        """Live (A of 11-09): the second Teleportation of the floor returned on 4229948.  On
        another floor it is the first escape there: no return."""
        with no_depth_gate(), in_line_of_fire():
            policy, answers = self.replay(LIFE, RECALL_BOARD, from_turn(SECOND_BOARD, at_depth(79)),
                                          without=(DESTRUCTION_NAME,))
        self.assertEqual(answers[SECOND_BOARD][2], "sensed-t1:teleport")
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertFalse(policy._returning_to_town)
        self.assertNotEqual(answers[RECALL_BOARD][2], "return:recall")

    def test_a_sensed_t1_out_of_the_line_of_fire_is_no_escape(self):
        """As recorded: the 4229938 Teleportation leaves T1s with no line of fire (owner
        2026-11-13): the count stays at the locusts' one and no return is latched."""
        policy, answers = self.replay(LIFE, LATCH_BOARD, without=(DESTRUCTION_NAME,))
        self.assertEqual(answers[SECOND_BOARD][2], "sensed-t1:teleport")
        board = parse_snapshot(self.board(LIFE, SECOND_BOARD), self.races)
        self.assertFalse(any(
            policy._has_line_of_fire(board, monster.position, board.player.position)
            for monster in (*board.visible_monsters, *board.detected_monsters)
            if monster.hostile and not monster.asleep))
        self.assertEqual((policy._dive_emergencies, policy._last_return_trigger), (1, None))

    def test_a_destruction_away_from_the_cause_keeps_the_escape(self):
        """4229938's *Destruction* is 70 cells from the locusts the escape fled."""
        policy, answers = self.replay(LIFE, LATCH_BOARD, from_turn(LATCH_BOARD, flash))
        self.assertEqual(answers[SECOND_BOARD][2], DESTRUCTION_REASON)
        self.assertEqual(policy._dive_emergencies, 1)

    def test_destroying_the_cause_ends_the_latched_return(self):
        with no_depth_gate():
            policy = self.locusts_destroyed()
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertFalse(policy._returning_to_town)
        self.assertIsNone(policy._last_return_trigger)
        self.assertFalse(policy.last_reason.startswith("return:"), policy.last_reason)

    def test_a_recall_already_read_stays(self):
        with no_depth_gate():
            policy = self.locusts_destroyed(recalling=True)
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertTrue(policy._returning_to_town)


if __name__ == "__main__":
    unittest.main()
