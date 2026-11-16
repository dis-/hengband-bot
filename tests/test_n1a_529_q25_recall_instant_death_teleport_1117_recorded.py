"""Quest 25 phase 2 on n1-a life-529 (2026-11-17 00:10): the Recall wait's 即死 boards, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-a/life-529/captures/20261117-001053-exit-no-marker,
build bot-945ab02d2; battle phase 2, Ipsissimus; Word of Recall read at 36515):

 * At 36522 the next action's p95 (threat_tiers ``instant_death``) was 689 against HP 541 with
   15 Teleportation scrolls in the pack; the plan's 即死 rung answered with Teleport Away
   (``quest-strategy:teleport-away``), as the 11-12 rule (quest_no_teleport ``q25_hall_forbids``:
   no relocation up to phase 3) left it.  From 36531 on every board was 即死 and the answers were
   Teleport Away and the cornered blow; the player died at 36547.

The rule (owner 2026-11-17, 「Q25 の段階3より前に即死になった時はどうしますか？」 → 「帰還待ちの
即死ならテレポートを許す」): with the Recall counting down on the 即死 board, the Teleportation
scroll; before the Recall is read the 11-12 rule stands.

Recorded: tests/fixtures/n1a-529-q25-recall-wait-1117.json.gz (its module note), decided by a fresh
policy through the public ``choose_key`` (tests/test_n1a_529_q25_recall_wait_1117_recorded
``decide``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest_no_teleport, quest_plan_base, threat_tiers
from tests import test_n1a_529_q25_recall_wait_1117_recorded as recorded

INSTANT_DEATH = (36522, 36531, 36533)
NOT_INSTANT_DEATH = (36516, 36520)


def _read_item(snapshot, key):
    letter = key[1]
    return next(item for item in snapshot.inventory if item.slot == letter)


class TheRecordingTest(unittest.TestCase):

    def test_teleport_away_on_the_instant_death_boards(self):
        for sequence in INSTANT_DEATH:
            row = recorded.CASE["second"]["recorded"][recorded._index(sequence)]
            self.assertEqual(row["reason"], quest_plan_base.AWAY_REASON, sequence)

        def facts(policy, snapshot):
            death = threat_tiers.instant_death(policy, snapshot)
            return (snapshot.player.recalling, death.holds, death.next_action_p95, snapshot.player.hp,
                    policy._count_teleport_scrolls(snapshot))

        key, _reason, _snapshot = recorded.decide(36522, answer=facts)
        self.assertEqual(key, (True, True, 689, 541, 15))


class RecallInstantDeathTeleportTest(unittest.TestCase):

    def test_recall_counting_down_on_the_instant_death_board_reads_teleportation(self):
        for sequence in INSTANT_DEATH:
            key, reason, snapshot = recorded.decide(sequence)
            self.assertTrue(snapshot.player.recalling, sequence)
            self.assertEqual(reason, quest_plan_base.TELEPORT_REASON, (sequence, key))
            self.assertEqual(key[0], "r", sequence)
            self.assertTrue(_read_item(snapshot, key).is_teleport_scroll, (sequence, key))

    def test_without_instant_death_the_rule_stands(self):
        for sequence in NOT_INSTANT_DEATH:
            forbidden, _reason, _snapshot = recorded.decide(sequence, answer=quest_no_teleport.q25_hall_forbids)
            self.assertTrue(forbidden, sequence)
            _key, reason, _snapshot = recorded.decide(sequence)
            self.assertNotEqual(reason, quest_plan_base.TELEPORT_REASON, sequence)

    def test_before_the_recall_is_read_the_rule_stands(self):
        # DECLARED CONSTRUCTED control: the 36522 board with the Recall not read (``recalling``
        # False) -- still 即死, the 11-12 rule's answer, Teleport Away, unchanged.
        def not_recalling(raw):
            raw["player"]["recalling"] = False

        key, reason, snapshot = recorded.decide(36522, not_recalling)
        self.assertFalse(snapshot.player.recalling)
        self.assertEqual(reason, quest_plan_base.AWAY_REASON, key)


if __name__ == "__main__":
    unittest.main()
