"""A Magic-Eater before a monster that never comes and that no shot of his reaches now (Quest 33).

Owner 2026-11-25 (verbatim), asked 「水から出ない敵や動かない敵に撃つ手が無い時、魔道具術師も岸や隣へ寄って近接で
倒しますか？」: 「撃つ手も取り込んだ魔法道具の手も無い時はそれを許可するが、休憩して魔法道具の使用回数を戻せる
場合はその限りではない」.  The warrior's shore blow (n1-a life-537, quest_summon_answer ``attack_cells``)
stays as it is; a Magic-Eater:

* with an absorbed attack power for the monster that has no use now and that a rest restores
  (hpmp/hp-mp-regenerator.cpp regenmagic refills every absorbed staff and wand and counts every
  absorbed rod's charging down with game time; me_device_attacks ``restorable_powers``), leaves its
  line (``fire-disengage-walk``) and, out of every line, rests (``R100``,
  ``quest-strategy:summoned-rest-recharge``) instead of closing on the shore to melee it;
* with none (no attack power absorbed), closes on the shore as the warrior does.

DECLARED CONSTRUCTED, on the replay of tests/test_n1c_220_q33_sensed_1122_recorded.py (n1-c life-220's
recorded Quest 33 boards, two 船幽霊 race 1389 AQUATIC in the deep water at [4,41] and [5,41], known by
telepathy; the policy is n1-c life-217's town arrival, a Magic-Eater with no rounds for its launcher):
the displayed power lists are life-217's with every absorbed attack power's uses spent (a staff's or
wand's ``current`` 0, a rod's ``charging`` at its count) for the first case, and with the attack powers
left out of the lists for the second.  No recorded run of a Magic-Eater met a monster that never comes
with its attack powers spent.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot import me_device_attacks, quest_summon_answer
from hengbot.q34_recharge import REST_KEY
from tests import test_n1c_220_q33_sensed_1122_recorded as base
from tests.test_n1c_220_q33_sensed_1122_recorded import ACTED_ON_CELL, HASTED_BOARDS, LIST_READ_REASON, PHANTOM_SHIP


def spent(kind, row):
    """``row`` with no use left: a staff or wand at 0 charges, a rod charging its whole count."""
    if kind == "rod":
        return {**row, "charging": row["max"]}
    return {**row, "current": 0}


def is_attack(kind, row) -> bool:
    return (kind, row.get("name")) in me_device_attacks._BY_NAME


class _Replay(base.N1c220SensedChooseKeyTest):
    """The n1-c 220 replay (setUp, ``answers``) with this module's lists; its own tests not re-run."""

    def lists_where(self, row_of):
        """life-217's lists with each attack row replaced by ``row_of(kind, row)`` (None: dropped)."""
        out = {}
        for kind, (turn, rows) in self.lists.items():
            kept = []
            for row in rows:
                if is_attack(kind, row):
                    row = row_of(kind, row)
                if row is not None:
                    kept.append(row)
            out[kind] = (turn, tuple(kept))
        return out

    def answers_with(self, lists, **kwargs):
        self.lists = lists
        return self.answers(**kwargs)


for _name in [name for name in vars(base.N1c220SensedChooseKeyTest) if name.startswith("test_")]:
    setattr(_Replay, _name, None)


class SpentPowersTest(_Replay):
    def setUp(self):
        super().setUp()
        self.spent = self.lists_where(spent)

    def test_the_spent_powers_are_restorable(self):
        (snapshot, _reason, _key), = self.answers_with(self.spent, boards=1)
        self.assertTrue(me_device_attacks.restorable_powers(self.policy, snapshot, PHANTOM_SHIP))
        self.assertTrue(quest_summon_answer.recharges_first(self.policy, snapshot, PHANTOM_SHIP))
        self.assertTrue(quest_summon_answer.melee_withheld(self.policy, snapshot, PHANTOM_SHIP))

    def test_in_their_line_the_line_is_left_not_the_shore_closed_on(self):
        # The recorded boards on [1,27], in the casters' line: no shot now, a power a rest restores.
        for disengaged in (True, False):
            with self.subTest(disengaged=disengaged):
                answers = self.answers_with(self.spent, boards=HASTED_BOARDS, disengaged=disengaged)
                reasons = [reason for _snapshot, reason, _key in answers]
                self.assertLessEqual(set(reasons), {quest_summon_answer.FIRE_WALK_REASON, LIST_READ_REASON})
                self.assertIn(quest_summon_answer.FIRE_WALK_REASON, reasons)

    def test_out_of_their_line_the_rest_is_taken(self):
        # [1,22]: within their vision (they act on the player) and out of their line, at full HP.
        answers = self.answers_with(self.spent, at=ACTED_ON_CELL, boards=8, full_hp=True)
        rested = [(reason, key) for _snapshot, reason, key in answers if reason != LIST_READ_REASON]
        self.assertTrue(rested)
        self.assertEqual(set(rested), {(quest_summon_answer.RECHARGE_REST_REASON, REST_KEY)})
        # The rest leaves the spent kinds' lists to be read again (me_powers_refresh.resume_read_key).
        self.assertTrue(me_device_attacks.stale_kinds(self.policy))


class NoPowerTest(_Replay):
    def setUp(self):
        super().setUp()
        self.none = self.lists_where(lambda kind, row: None)

    def test_with_no_attack_power_the_shore_is_closed_on(self):
        (snapshot, _reason, _key), = self.answers_with(self.none, boards=1)
        self.assertFalse(me_device_attacks.restorable_powers(self.policy, snapshot, PHANTOM_SHIP))
        self.assertFalse(quest_summon_answer.melee_withheld(self.policy, snapshot, PHANTOM_SHIP))
        answers = self.answers_with(self.none, boards=HASTED_BOARDS)
        reasons = [reason for _snapshot, reason, _key in answers]
        self.assertLessEqual(set(reasons), {quest_summon_answer.FIRE_APPROACH_REASON, LIST_READ_REASON})
        self.assertIn(quest_summon_answer.FIRE_APPROACH_REASON, reasons)

    def test_out_of_their_line_the_shore_is_walked_to(self):
        answers = self.answers_with(self.none, at=ACTED_ON_CELL, boards=8, full_hp=True)
        reasons = {reason for _snapshot, reason, _key in answers}
        self.assertNotIn(quest_summon_answer.RECHARGE_REST_REASON, reasons)
        self.assertIn(quest_summon_answer.LURE_WALK_REASON, reasons)


del _Replay


if __name__ == "__main__":
    unittest.main()
