"""Cure Serious / Critical Wounds are no HP recovery (threat tiers C-7, plan step 2).

Owner 2026-11-03 「致命傷の治癒は HP の回復の手段に数えない」 and 2026-11-07 (OQ-7):
Cure Light and Cure Serious Wounds are not HP recovery either; only Healing,
*Healing* and Life are.  The one exception stays: QUEST_14's strategy names
Cure Critical Wounds as its heal potion (owner 2026-10-31 「致命傷の治癒でよい」,
``heal_potion_kind``).  Their use as status cures is unchanged.

Boards:

* the recorded Forest 32F board 534 (tests/test_low_hp_no_unchecked_walk.py
  ``LowHpHealVsTeleportTest``, live 03:43 process) after an unseen bite at HP
  420/731, its Healing stack turned into Cure Serious Wounds, recall removed and
  the bite set to 10 HP -- DECLARED CONSTRUCTED.  Before: ``item:heal`` drank the
  Cure Serious Wounds (4d8 covers the 10-HP turn); now the teleport is read;
* an adjacent unique carrying only Cure Critical Wounds
  (tests/test_policy_combat.py ``UniqueCombatConsumableTest``) -- DECLARED
  CONSTRUCTED; no unique fight that drank Cure Critical Wounds was recorded.
  Before: ``unique:quaff-cure-critical``;
* the recorded n1-c life-072 town board of tests/test_q14_heal_ccw_recorded.py
  for the readiness projection: Cure Critical Wounds counted only for a
  strategy that names it (QUEST_14).

Cure Light Wounds was never counted as HP recovery (HEAL_POTION_SVALS had no 34).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace

from hengbot.model import SV_POTION_HEALING, TVAL_POTION, parse_snapshot
from hengbot.monrace_knowledge import MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_low_hp_no_unchecked_walk as low_hp
from tests import test_policy_combat as combat
from tests import test_q14_heal_ccw_recorded as q14
from tests.test_policy import item

SV_POTION_CURE_SERIOUS = 35
SV_POTION_SPEED = 29


class CureSeriousIsNoHpRecoveryTest(low_hp._Boards):
    def _decide_after_bite(self, *, cure_serious, bite):
        board = low_hp.LowHpHealVsTeleportTest._kit_board(self, cure_serious=cure_serious)
        policy = copy.deepcopy(self.policy)
        policy._last_hp = board.player.hp + bite    # DECLARED CONSTRUCTED: the bite's size
        key = str(policy.choose_key(board))
        return board, key, policy.last_reason

    def test_cure_serious_is_not_drunk_for_hp(self):
        board, key, reason = self._decide_after_bite(cure_serious=True, bite=10)
        potion = next(i for i in board.inventory if i.is_potion and i.sval == SV_POTION_CURE_SERIOUS)
        self.assertNotEqual(key, "q" + potion.slot, reason)
        scroll = next(i for i in board.inventory if i.is_teleport_scroll)
        self.assertEqual((key, reason), ("r" + scroll.slot, "emergency:teleport"))

    def test_control_healing_is_drunk_for_the_same_bite(self):
        board, key, reason = self._decide_after_bite(cure_serious=False, bite=10)
        potion = next(i for i in board.inventory if i.is_potion and i.sval == SV_POTION_HEALING)
        self.assertEqual((key, reason), ("q" + potion.slot, "item:heal"))


class UniqueFightCountsNoCureCriticalTest(unittest.TestCase):
    def _board(self, *, healing=0):
        case = combat.UniqueCombatConsumableTest()
        snapshot, monster, knowledge = case._cure_critical_guardian(
            hp=100, monster_speed=110, blow_sides=4)
        if healing:
            snapshot = replace(snapshot, inventory=[
                *snapshot.inventory, item("d", TVAL_POTION, SV_POTION_HEALING, count=healing)])
        return snapshot, monster, knowledge

    def test_cure_critical_is_not_drunk_as_unique_fight_healing(self):
        snapshot, monster, knowledge = self._board()
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        key = policy.choose_key(snapshot)
        self.assertNotEqual(key, "qc", policy.last_reason)
        self.assertFalse(str(policy.last_reason).startswith("unique:quaff"), policy.last_reason)
        # The projection credits no Cure Critical dose: the fight needs one, so it is not viable.
        self.assertIsNone(policy._unique_fight_projection(
            snapshot, [monster], monster, player_speed=snapshot.player.speed))

    def test_no_speed_potion_to_save_cure_critical_doses(self):
        # The unique-fight Speed rule spends a potion only when haste saves healing
        # doses; Cure Critical Wounds are none, so a pack of them alone no longer
        # buys the haste (the outpaced guardian board, two Potions of Speed added).
        case = combat.UniqueCombatConsumableTest()
        snapshot, _, knowledge = case._cure_critical_guardian()
        snapshot = replace(snapshot, inventory=[
            *snapshot.inventory, item("s", TVAL_POTION, SV_POTION_SPEED, count=2)])
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        key = policy.choose_key(snapshot)
        self.assertNotEqual((key, policy.last_reason), ("qs", "unique:quaff-speed"))

    def test_control_healing_is_drunk_on_the_same_board(self):
        snapshot, monster, knowledge = self._board(healing=1)
        policy = HengbotPolicy(monrace_knowledge={9001: knowledge})
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("qd", "unique:quaff-healing"))


class FixedQuestReadinessCountsCureCriticalOnlyForQ14Test(unittest.TestCase):
    """The readiness projection's healing doses (``_evaluate_fixed_quest_readiness``)."""

    @classmethod
    def setUpClass(cls):
        q14.Q14HealCureCriticalRecordedTest.setUpClass.__func__(cls)

    recorded_policy = q14.Q14HealCureCriticalRecordedTest.recorded_policy

    def test_recorded_board_still_requests_q14(self):
        # The recorded board requests Q14 through choose_key (test_q14_heal_ccw_recorded).
        policy, raw = self.recorded_policy()
        policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        readiness = policy._fixed_quest_readiness
        self.assertEqual((readiness["quest_id"], readiness["verdict"]), (14, True))

    def _budget(self, *, names_cure_critical):
        """The projection's HP + healing budget on the recorded board (1 Healing, 10 CCW).

        DECLARED CONSTRUCTED: the Warg's bite lowered to 1d3, so a Cure Critical
        dose (27) covers the projected turn and the dose filter keeps it; for the
        control, Q14's force without ``heal_potion_kind`` (a strategy that does
        not name Cure Critical Wounds) and one heal potion.
        """
        policy, raw = self.recorded_policy()
        # The class's race and strategy tables are shared: work on copies.
        policy._monrace_knowledge = dict(policy._monrace_knowledge)
        policy._quest_strategies = dict(policy._quest_strategies)
        warg = policy._monrace_knowledge[257]
        policy._monrace_knowledge[257] = replace(
            warg, blows=(MonsterBlow("BITE", "HURT", 1, 3),), max_melee_damage=3)
        if not names_cure_critical:
            profile = policy._quest_strategies[14]
            force = {key: value for key, value in profile.required_force.items()
                     if key != "heal_potion_kind"}
            policy._quest_strategies[14] = replace(profile, required_force=dict(force, heal_potions=1))
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        sink = []
        verdict = policy._evaluate_fixed_quest_readiness(
            snapshot, 14, require_target_town=False, commit=False, telemetry_sink=sink)
        self.assertTrue(verdict, sink)
        return sink[0]["hp_healing_budget"] - snapshot.player.max_hp

    def test_q14_counts_its_cure_critical_doses(self):
        # Healing 300 plus the two strongest further doses: Cure Critical 27 + 27.
        self.assertEqual(self._budget(names_cure_critical=True), 300 + 27 + 27)

    def test_a_strategy_not_naming_cure_critical_counts_only_healing(self):
        self.assertEqual(self._budget(names_cure_critical=False), 300)


if __name__ == "__main__":
    unittest.main()
