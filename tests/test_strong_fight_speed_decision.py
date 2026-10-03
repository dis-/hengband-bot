"""Pins: a Speed potion at the start of a strong fight.

USER DECISION 2026-10-03 06:2x.  Question: use Speed potions when it is
dangerous (death 2026-10-03 05:33: ten carried, never considered; the 09-18
rule 「逃走の成否で判定」 covers fleeing only).  Answer: option
「強敵との戦闘開始時に飲む」 -- 「予測被害が HP の一定割合を超える戦闘に入った
時点で飲む。消費は増えるが被害は減る。」 -- with the ratio 「HP の5割
(Recommended)」: the 3-turn predicted damage at least half the current HP.
The 09-18 escape rule stays as it is (「逃走時の判定はそのまま」).

The prediction is the operational 3-turn projection of the hostiles in view,
at least three repeats of the observed one-move loss (the death fix's
fair-play correction for an unseen caster).  The start of the fight is the
first board of a run of strong boards on one floor; the bot quaffs once
unless the speed field already shows haste.

Recorded pin: the death capture (fixture of test_lethal_unseen_caster_
recorded) board 06036445, HP 307 of 731 among 25 visible hostiles, 3-turn
projection 173 >= 153.5, ten Speed potions in slot a, speed +0 (white): a
fresh process quaffs Speed; the recorded game meleed (the pre-decision bot
decides the same melee).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.model import Position, Snapshot, SV_POTION_SPEED, SV_SCROLL_TELEPORT
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STRONG_FIGHT_SPEED_HP_RATIO
from policy_fixtures import grid, hostile, item, player
import test_lethal_unseen_caster_recorded as lethal
from test_lethal_unseen_caster_recorded import (
    B_CURE,
    B_CURED,
    B_WARMUP,
    C_WARMUP,
)
from test_policy import POTION, SCROLL
import test_policy_combat as combat

SPEED_SLOT = "a"


class StrongFightSpeedRecordedTest(lethal._Replay):
    def _strong(self, board):
        hostiles = self.policy._strategic_hostiles(board)
        return self.policy._corrected_predicted_damage(board, hostiles, 3)

    def test_recorded_strong_fight_start_quaffs_speed(self):
        self.assertEqual(self._live(C_WARMUP), ("3", "melee"))
        board, key, reason = self._decide(C_WARMUP)
        self.assertEqual(board.player.hp, 307)
        self.assertEqual(board.player.speed, 110)
        self.assertFalse(self.policy._player_hasted(board))
        self.assertGreater(len(self.policy._strategic_hostiles(board)), 20)
        self.assertGreaterEqual(
            self._strong(board), board.player.hp * STRONG_FIGHT_SPEED_HP_RATIO
        )
        # Not the lethal ladder: the fight itself starts here.
        self.assertFalse(self.policy._emergency_escape_pending)
        speed = self.policy._find_exact_potion(board, SV_POTION_SPEED)
        self.assertEqual(speed.slot, SPEED_SLOT)
        self.assertEqual(
            (key, reason), ("q" + SPEED_SLOT, "item:strong-fight-speed")
        )

    def test_one_quaff_per_strong_run(self):
        board, key, _reason = self._decide(C_WARMUP)
        self.assertEqual(key, "q" + SPEED_SLOT)
        hostiles = self.policy._strategic_hostiles(board)
        # The same run: no second quaff.
        self.assertIsNone(self.policy._strong_fight_speed_key(board, hostiles, 0))
        # A board that is not strong ends the run (no hostile, no hit) ...
        self.assertIsNone(self.policy._strong_fight_speed_key(board, [], 0))
        self.assertIsNone(self.policy._strong_fight_speed_floor)
        # ... and the next strong board starts a new one.
        self.assertEqual(
            self.policy._strong_fight_speed_key(board, hostiles, 0),
            "q" + SPEED_SLOT,
        )

    def test_below_half_hp_is_no_strong_fight(self):
        # 06036417: HP 600, 29 visible hostiles, 3-turn projection 230 < 300.
        # (Conformance pin: the pre-decision bot also meleed.)
        board, key, reason = self._decide(B_WARMUP)
        self.assertLess(
            self._strong(board), board.player.hp * STRONG_FIGHT_SPEED_HP_RATIO
        )
        self.assertIsNotNone(self.policy._find_exact_potion(board, SV_POTION_SPEED))
        self.assertEqual((key, reason), self._live(B_WARMUP))

    def test_lethal_ladder_goes_before_the_speed_potion(self):
        # 06036437 (B chain, as test_lethal_unseen_caster_recorded): strong
        # (the carried loss 290 x 3 >= 168.5) with ten Speed potions and no
        # strong run yet, but the lethal ladder heals first -- a Speed potion
        # never delays the emergency ladder.  (Ordering pin: not
        # distinguished by reverting the decision, which never quaffed.)
        for turn in (B_WARMUP, B_CURE):
            _board, key, reason = self._decide(turn)
            self.assertEqual((key, reason), self._live(turn), turn)
        board, key, reason = self._decide(B_CURED)
        self.assertIsNotNone(self.policy._find_exact_potion(board, SV_POTION_SPEED))
        self.assertTrue(self.policy._emergency_escape_pending)
        self.assertIsNone(self.policy._strong_fight_speed_floor)
        self.assertEqual(reason, "item:heal")


class StrongFightSpeedConstructedTest(unittest.TestCase):
    """DECLARED CONSTRUCTED boards: an open room, one adjacent hostile, the
    predictor patched (3 turns 60 against HP 100 of 200 unless stated)."""

    def _snap(self, *, hp=100, poisoned=False, afraid=False, hasted=False,
              hostiles=True):
        grids = {
            Position(10, x): grid(10, x, monster=(x == 11 and hostiles))
            for x in range(8, 13)
        }
        me = player(
            10, 10, hp=hp, max_hp=200, poisoned=poisoned, afraid=afraid,
            speed=120 if hasted else 110,
        )
        if hasted:
            me = replace(me, speed_display=(10, "+10", "yellow", False))
        else:
            me = replace(me, speed_display=(0, "", "white", False))
        return Snapshot(
            me, grids,
            [hostile(1, 10, 11, hp=30, max_hp=30, distance=1)] if hostiles else [],
            inventory=[item(SPEED_SLOT, POTION, SV_POTION_SPEED, count=5)],
            floor_key=(0, 10, 0),
        )

    def _key(self, snap, *, observed_loss=0, three_turns=60):
        policy = HengbotPolicy()
        hostiles = [m for m in snap.visible_monsters if m.hostile]
        with patch.object(
            policy, "_predicted_damage",
            side_effect=lambda *_a, **kw: three_turns if kw.get("turns") == 3 else 0,
        ), patch.object(policy, "_engagement_is_winnable", return_value=True):
            return policy, policy._strong_fight_speed_key(snap, hostiles, observed_loss)

    def test_strong_fight_quaffs(self):
        policy, key = self._key(self._snap())
        self.assertEqual(key, "q" + SPEED_SLOT)
        self.assertEqual(policy.last_reason, "item:strong-fight-speed")

    def test_below_half_hp_does_not_quaff(self):
        _policy, key = self._key(self._snap(), three_turns=49)
        self.assertIsNone(key)

    def test_hasted_does_not_quaff(self):
        # The speed field shows haste (yellow): the run starts, no quaff.
        policy, key = self._key(self._snap(hasted=True))
        self.assertIsNone(key)
        self.assertEqual(policy._strong_fight_speed_floor, (0, 10, 0))

    def test_unseen_hit_without_hostiles_is_a_fight(self):
        # No hostile in view; one move cost 20 (3 x 20 >= 50).
        _policy, key = self._key(
            self._snap(hostiles=False), observed_loss=20, three_turns=0
        )
        self.assertEqual(key, "q" + SPEED_SLOT)

    def test_poison_tick_without_hostiles_is_no_fight(self):
        # Poisoned, no hostile in view, no unseen attacker's message: the
        # loss of 20 is the poison tick, not a fight.
        policy, key = self._key(
            self._snap(hostiles=False, poisoned=True), observed_loss=20,
            three_turns=0,
        )
        self.assertIsNone(policy._unseen_attack_evidence)
        self.assertIsNone(key)

    def test_flee_board_leaves_speed_to_the_escape_rule(self):
        # Afraid with an adjacent hostile: the bot flees this board, and the
        # 09-18 escape rule (「逃走時の判定はそのまま」) alone judges Speed.
        policy, key = self._key(self._snap(afraid=True))
        self.assertIsNone(key)
        self.assertIsNone(policy._strong_fight_speed_floor)


class StrongFightSpeedLeavesEscapesTest(unittest.TestCase):
    """Review 2026-10-03 (F1): the Speed quaff takes only a fighting action's
    place; 「逃走時の判定はそのまま」 for every escape/relocation producer.

    DECLARED CONSTRUCTED: test_policy_combat.PredictiveEscapeTest's line
    board, HP 100 of 100, one adjacent unresisted TOUCH:PARALYZE 3d10 (no
    Free Action), a Teleportation scroll and a Speed potion; 3-turn p95 81 >=
    50 makes the fight strong.  The status-threat rung reads the scroll.
    (Before this, the quaff in _emergency_item pre-empted it: 'qs'.)"""

    def _board(self, inventory):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=30), race_id=6002
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=10, max_melee_damage=30,
            blows=(MonsterBlow("TOUCH", "PARALYZE", 3, 10),),
        )
        snapshot = combat.PredictiveEscapeTest()._line_snapshot(
            monster, hp=100, inventory=inventory
        )
        return snapshot, HengbotPolicy(monrace_knowledge={6002: knowledge})

    def test_paralyzer_scroll_read_is_not_replaced_by_speed(self):
        snapshot, policy = self._board([
            item("t", SCROLL, SV_SCROLL_TELEPORT),
            item("s", POTION, SV_POTION_SPEED),
        ])
        key = policy.choose_key(snapshot)
        self.assertGreaterEqual(
            policy.threat_prediction(snapshot, snapshot.visible_monsters, 3)[
                "operational_total"
            ],
            snapshot.player.hp * STRONG_FIGHT_SPEED_HP_RATIO,
        )
        self.assertEqual((key, policy.last_reason), ("rt", "status-threat:scroll"))
        self.assertIsNone(policy._strong_fight_speed_floor)


if __name__ == "__main__":
    unittest.main()
