"""Threat tiers plan step 7 on recorded boards: the selected supply fight.

Owner 2026-11-07, answer 4, OQ-4, D3, D4, D7 (test_threat_tiers_supply_fight says them).

Acceptance: the recorded death lives of n1-a 450/466/470/474/475, n1-b 299/306/325, n1-c
077/084/085/099/103/123, n1-a 475's summons and n1-c's D57 lives were replayed with step 7 off
(today's supplied unique fight, the recorded trajectory) and each board decided by a copy with it
on (test_threat_tiers_leave_recorded.decided_with_and_without): no board changes.  One did before
the return guard: n1-c life-083's turn 1186972 (HP 95/171, a latched return reading Word of
Recall beside an ogre, a reward race, T2 by the Speed dose) became the supply fight's Speed; a
supply fight no longer opens while the floor is being left (pinned below), so no escape becomes
a stay.

The fights themselves are pinned on n1-c life-083's beetle board (ブラウン・キラービートル, HP
118/171, a reward race), DECLARED CONSTRUCTED where a test adds a potion or changes the race.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.model import SV_POTION_SPEED, parse_snapshot
from tests.test_threat_tiers_leave_recorded import decided_with_and_without

OFF = [(threat_tiers, "supply_fight_applies", lambda *args, **kwargs: False)]
SPEED_POTION = {"aware": True, "count": 2, "fully_known": True, "known": True, "name": "スピードの薬",
                "slot": "s", "sval": SV_POTION_SPEED, "tval": 75, "weight": 4}


def speed_key(raw):
    return "q" + next(item["slot"] for item in raw["inventory"]
                      if item["tval"] == 75 and item.get("sval") == SV_POTION_SPEED)


def beetle_board(*, speed_potions=False):
    from tests import test_d57_me_combat_1101_recorded as combat
    raw = copy.deepcopy(next(r for r in combat.CASE_083["boards"] if r["turn"] == combat.BEETLE_TURN))
    if speed_potions:
        # A copy of the pack's own potion row (protocol 3 keys), as two Potions of Speed.
        template = next(item for item in raw["inventory"] if item.get("aware") and "charging" in item)
        letter = chr(ord(max(item["slot"] for item in raw["inventory"])) + 1)
        raw["inventory"].append(dict(template, **{key: SPEED_POTION[key] for key in
                                                  ("count", "name", "sval", "tval", "weight")},
                                     is_equipment=False, known=True, fully_known=True, slot=letter))
    policy = combat.d57.new_policy(combat.CASE_083)
    return policy, raw


def decide(policy, raw):
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    return str(policy.choose_key(board)), policy.last_reason, board


def assessed(policy, board):
    with _PolicyObserverScope(policy):
        return threat_tiers.assess(policy, board, policy._strategic_hostiles(board))


class SupplyFightRecordedTest(unittest.TestCase):
    def test_the_reward_beetle_is_fought_with_speed_first(self):
        # DECLARED CONSTRUCTED: two Potions of Speed in the pack.  T2 by the Speed dose alone, the
        # beetle a reward race: the selected fight drinks Speed first (D7); today's supplied fight
        # (uniques and kill-quest targets only) fires the absorbed Magic Missile.
        policy, raw = beetle_board(speed_potions=True)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        result = assessed(policy, board)
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.categories, ("speed",))
        self.assertEqual([result.per_monster[i].selected for i in result.selected], [("reward",)])
        key, reason, _board = decide(policy, raw)
        self.assertEqual((key, reason), (speed_key(raw), threat_tiers.SUPPLY_SPEED_REASON))
        policy, raw = beetle_board(speed_potions=True)
        with patch.object(threat_tiers, "supply_fight_applies", return_value=False):
            key, reason, _board = decide(policy, raw)
        self.assertNotEqual(reason, threat_tiers.SUPPLY_SPEED_REASON)

    def test_as_the_quest_target_it_is_fought_without_the_reward(self):
        # DECLARED CONSTRUCTED: the reward taken away and the beetle the active quest's target.
        policy, raw = beetle_board(speed_potions=True)
        race = next(m["race_id"] for m in raw["visible_monsters"] if m["name"] == "ブラウン・キラービートル")
        with patch.object(threat_tiers, "reward_reasons", return_value=()), \
                patch.object(threat_tiers, "_quest_races", return_value={race}):
            key, reason, board = decide(policy, raw)
            self.assertEqual((key, reason), (speed_key(raw), threat_tiers.SUPPLY_SPEED_REASON))

    def test_a_unique_alone_spends_nothing_and_is_left(self):
        # DECLARED CONSTRUCTED: the beetle made UNIQUE with no reward (OQ-4: a unique alone is no
        # selected target); no supply is spent and the unselected T2 is left (step 6).
        policy, raw = beetle_board(speed_potions=True)
        race = next(m["race_id"] for m in raw["visible_monsters"] if m["name"] == "ブラウン・キラービートル")
        knowledge = policy._monrace_knowledge[race]
        policy._monrace_knowledge[race] = replace(knowledge, flags=knowledge.flags | {"UNIQUE"})
        with patch.object(threat_tiers, "reward_reasons", return_value=()):
            key, reason, board = decide(policy, raw)
        self.assertFalse(reason.startswith(("supply-fight", "unique:")), reason)
        self.assertTrue(reason.startswith(("flee", "emergency")), (key, reason))

    def test_no_supply_fight_opens_while_the_floor_is_being_left(self):
        # n1-c life-083, turn 1186972: the latched return reads Word of Recall, the ogre beside it
        # (a reward race, T2 by the Speed dose) does not stop it.
        changed = decided_with_and_without("d57-n1c-083-1101.json.gz", OFF, turns={1186972})
        self.assertEqual(changed, {})
        policy, raw = beetle_board(speed_potions=True)
        policy._returning_to_town = True
        key, reason, _board = decide(policy, raw)
        self.assertNotEqual(reason, threat_tiers.SUPPLY_SPEED_REASON)

    def test_lives_with_no_change(self):
        for name in ("death-n1a-475-1104.json.gz", "death-n1c-085-1101.json.gz",
                     "d57-me-combat-083-1101.json.gz", "d57-me-combat-084-1101.json.gz"):
            with self.subTest(life=name):
                self.assertEqual(decided_with_and_without(name, OFF), {})


if __name__ == "__main__":
    unittest.main()
