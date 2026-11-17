"""*Destruction* is no longer refused while an attacker the board does not show is evidenced.

Owner 2026-11-17 (whole-bot maintainability review, question Q2 「見えない敵に攻撃された形跡がある
間は *破壊* を使わない条件」, answer verbatim 「この条件を外す」): destruction_use refused every use
while ``_unseen_attack_evidence`` stood (``_in_view`` answered no monster, ``_threat_in_reach``
False), reasoning only 「届かないだろうから」, with no owner rule behind it.  Now the threats seen
or sensed decide the use and an unseen attacker inside the circle is destroyed with them.

Recorded: test_destruction_use_1104_recorded's HELD board (tests/fixtures/rq-teleport-reserve-1101
.json.gz "reserve-held", turn 1662215: 鉄獄38階, seven awake hounds in view, recorded
``emergency:teleport``), decided through the public ``choose_key``.  DECLARED CONSTRUCTED (as that
module declares): the staff of *Destruction* in the pack at a reliable skill; the bite message
「何かに噛まれた。」 and the 5 HP it took (the evidence of an attacker the board does not show).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import destruction_use
from hengbot.model import parse_snapshot
from tests import test_destruction_use_1104_recorded as base


def unseen_bite(raw):
    raw["messages"] = ["何かに噛まれた。"]
    raw["player"]["hp"] -= 5
    return raw


@base.own_tests_only
class UnseenAttackerDestructionTest(base.DestructionUseTest):
    def test_the_bite_of_an_unseen_attacker_is_evidenced(self):
        raw = unseen_bite(base.with_staff(copy.deepcopy(self.raw)))
        _, policy = self.answer(raw)
        self.assertIsNotNone(policy._unseen_attack_evidence)

    def test_with_the_scroll_the_instant_death_board_still_reads_it_first(self):
        """The unseen loss makes the board 即死 (threat_tiers' unseen correction), where owner
        2026-11-08 reads the Teleportation scroll before *Destruction*: unchanged."""
        raw = unseen_bite(base.with_staff(copy.deepcopy(self.raw)))
        self.assertEqual(self.answer(raw)[0], base.TELEPORT)

    def test_an_unseen_attacker_does_not_refuse_the_use(self):
        """DECLARED CONSTRUCTED: the Teleportation scrolls taken out of the pack.  On the 即死 board
        with none to read the engagement is left by *Destruction* (owner 2026-11-13); before
        2026-11-17 Q2 the unseen attacker's evidence refused it and the rung below read."""
        raw = unseen_bite(base.with_staff(self.without_scrolls(copy.deepcopy(self.raw),
                                                               base.SV_TELEPORT)))
        self.assertEqual(self.answer(raw)[0], base.STAFF_KEY)

    def test_usable_with_the_evidence_standing(self):
        raw = unseen_bite(base.with_staff(copy.deepcopy(self.raw)))
        _, policy = self.answer(copy.deepcopy(raw))
        policy._unseen_attack_evidence = "何かに噛まれた。"
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        hounds = [monster for monster in board.visible_monsters if monster.hostile]
        self.assertTrue(destruction_use._in_view(policy, board, None))
        self.assertTrue(destruction_use._threat_in_reach(policy, board, None, hostiles=hounds))


if __name__ == "__main__":
    unittest.main()
