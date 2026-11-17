"""*Destruction* before every Teleport Away outside the quest plans (owner 2026-11-17 Q4).

Owner 2026-11-16 (the n1-c life-216 question, answer 「常に *破壊* を先」) was applied only to the
Magic-Eater's THREAT occasion (me_powers ``unbeatable-in-range``).  Owner 2026-11-17 (whole-bot
maintainability review, question Q4, answer verbatim 「テレポート・アウェイの全場面に広げる」):
every Teleport Away -- teleport_follower ``away_key`` for the follower and for the blinder
(``BLINDER_REASON``), the carried rods and wands, the emergency ladder's -- asks *Destruction* on
its target first (destruction_use ``before_teleport_away``); the quest plans' Teleport Away
(quest_plan_base, me_powers ``quest-opening-target``) is left alone.

Recorded: n1-a life-500's 23F boards (tests/fixtures/teleport-follower-n1a-500-1109.json.xz, see
test_teleport_follower_1109_recorded), one fresh policy deciding every board in order through
``choose_key``.  DECLARED CONSTRUCTED (as that module declares them): from the summons on
禁断の護り手 is ディアボロ (a faster blinder that does not follow, ``blinder_in_place``), and a Staff
of *Destruction* with the device skill raised (``destruction_staff``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import destruction_use, me_powers, status_cure, teleport_follower
from hengbot.model import SV_WAND_TELEPORT_AWAY, TVAL_WAND, parse_snapshot
from tests import test_teleport_follower_1109_recorded as follower_case


BEFORE_TELEPORT_AWAY = destruction_use.REASON + ":before-teleport-away"


def blinder_and_staff(raw):
    follower_case.blinder_in_place(raw)
    follower_case.destruction_staff(raw)


class DestructionBeforeTeleportAwayTest(follower_case.TeleportFollowerHarness):
    def test_the_blinders_teleport_away_asks_destruction_first(self):
        """The SUMMONED board's blinder: Teleport Away aimed at it (BLINDER_REASON) before Q4."""
        policy, _answers = self.replay(until=follower_case.SUMMONED - 1, change=blinder_and_staff)
        raw = copy.deepcopy(next(raw for raw in self.payload["boards"]
                                 if raw["turn"] == follower_case.SUMMONED))
        blinder_and_staff(raw)
        follower_case.skill(policy, raw)
        snapshot = parse_snapshot(raw, self.races)
        blinders = status_cure.outpacing_blinders(policy, snapshot)
        self.assertEqual([m.race_id for m in blinders], [follower_case.NON_FOLLOWING_BLINDER])
        self.assertTrue(teleport_follower.away_usable(policy, snapshot))
        policy.last_reason = None
        key = teleport_follower.away_key(policy, snapshot, blinders, teleport_follower.BLINDER_REASON)
        self.assertEqual(policy.last_reason, BEFORE_TELEPORT_AWAY)
        self.assertTrue(key.startswith("u"), key)

    def test_without_the_staff_the_teleport_away_is_aimed_as_before(self):
        _policy, answers = self.replay(until=follower_case.SUMMONED,
                                       change=follower_case.blinder_in_place)
        raw, key, reason, _snapshot = answers[follower_case.SUMMONED]
        self.assertEqual((key, reason),
                         ("a" + follower_case.letter(raw, TVAL_WAND, SV_WAND_TELEPORT_AWAY) + "8",
                          teleport_follower.BLINDER_REASON))

    def test_every_teleport_away_trigger_but_the_quest_plans_asks_first(self):
        triggers = {name for power in me_powers.POWERS if power.effect == "teleport-away"
                    for name in power.triggers}
        self.assertEqual(me_powers.DESTRUCTION_FIRST_TRIGGERS, triggers - {"quest-opening-target"})
        self.assertIn("unbeatable-in-range", me_powers.DESTRUCTION_FIRST_TRIGGERS)


if __name__ == "__main__":
    unittest.main()
