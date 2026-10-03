"""Pins: teleport before the heal against paralysis and scroll locks.

USER DECISION 2026-10-03.  Question: 「低HP時の「回復が先」は、麻痺させる敵が
隣にいる時や、盲目・混乱で巻物を読めなくする攻撃が来る時にも当てはめますか？…」
Answer: 「その場面はテレポートを先にする (Recommended)」 -- 「耐性のない麻痺攻撃
の敵が隣にいる時と、巻物を読めなくする攻撃（盲目・混乱）を避けるための緊急脱出の
時は、回復量に関係なくテレポートを先に読む。それ以外は決定1どおり被害の量で
決める。」

DECLARED CONSTRUCTED boards (policy_fixtures), all below the low-HP threshold
with a Healing potion that outheals the next turn, so the heal-vs-teleport
decision alone would quaff it first:
- test_policy_combat.PredictiveEscapeTest's line board, HP 30 and 45 of 100,
  one adjacent awake TOUCH:PARALYZE 3d10 (no Free Action) -- the review's
  repro; with Free Action the same board heals first.
- test_policy_combat's Dokuro board (BA_LITE / BLIND / CONF caster at range
  9, predictor patched to 228 for three turns and 103 for one), HP 250 of
  533 (threshold 266.5): the ranged scroll-lock escape holds (228 + 103 >=
  250).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot.model import (
    DUNGEON_ANGBAND,
    SV_POTION_HEALING,
    SV_SCROLL_TELEPORT,
    Position,
    Snapshot,
)
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from policy_fixtures import grid, hostile, item, player
from test_policy import POTION, SCROLL
import test_policy_combat as combat


class ParalyzerTeleportBeforeHealTest(unittest.TestCase):
    def _decide(self, hp, free_action=False):
        monster = replace(
            hostile(1, 10, 11, distance=1, max_melee_damage=30), race_id=6002
        )
        knowledge = MonraceKnowledge(
            max_hp=20, average_hp=20, speed=110, can_summon=False,
            friendly=False, level=10, max_melee_damage=30,
            blows=(MonsterBlow("TOUCH", "PARALYZE", 3, 10),),
        )
        snapshot = combat.PredictiveEscapeTest()._line_snapshot(
            monster, hp=hp,
            inventory=[
                item("t", SCROLL, SV_SCROLL_TELEPORT),
                item("h", POTION, SV_POTION_HEALING),
            ],
        )
        if free_action:
            # An active per-source grant (_has_state_based_free_action).
            snapshot = replace(snapshot, player=replace(
                snapshot.player,
                abilities=frozenset({"free_action"}),
                ability_sources={"free_action": frozenset({"ring"})},
            ))
        policy = HengbotPolicy(monrace_knowledge={6002: knowledge})
        key = policy.choose_key(snapshot)
        return policy, snapshot, key

    def test_adjacent_paralyzer_teleports_before_the_heal(self):
        for hp in (30, 45):
            with self.subTest(hp=hp):
                policy, snapshot, key = self._decide(hp)
                self.assertLess(hp, policy._low_hp_walk_threshold(100))
                self.assertTrue(policy._emergency_escape_pending)
                # The heal would outheal the next turn (decision 1 alone).
                self.assertIsNotNone(policy._find_heal_potion(
                    snapshot,
                    expected_damage=policy._low_hp_next_turn_damage(
                        snapshot, snapshot.visible_monsters
                    ),
                ))
                self.assertEqual(
                    (key, policy.last_reason), ("rt", "emergency:teleport")
                )

    def test_free_action_leaves_decision_1(self):
        policy, snapshot, key = self._decide(30, free_action=True)
        self.assertTrue(policy._has_state_based_free_action(snapshot))
        self.assertTrue(policy._emergency_escape_pending)
        self.assertEqual((key, policy.last_reason), ("qh", "item:heal"))


class ScrollLockTeleportBeforeHealTest(unittest.TestCase):
    def test_ranged_scroll_lock_escape_teleports_before_the_heal(self):
        monster = replace(
            hostile(
                1, 7, 48, distance=9, max_melee_damage=120,
                max_ranged_damage=170,
            ),
            race_id=1124,
            speed=115,
        )
        knowledge = MonraceKnowledge(
            max_hp=900, average_hp=900, speed=115, can_summon=False,
            friendly=False, level=30, max_melee_damage=120,
            max_ranged_damage=170,
            abilities=frozenset({
                "CONF", "ANIM_DEAD", "BLINK", "HOLD", "CAUSE_3", "BLIND",
                "SHRIEK", "BA_LITE",
            }),
            spell_frequency=16,
        )
        grids = {
            Position(7, x): grid(7, x, monster=(x == 48)) for x in range(39, 49)
        }
        snapshot = Snapshot(
            player(
                7, 39, hp=250, max_hp=533,
                abilities=frozenset({"free_action", "resist_conf", "resist_chaos"}),
            ),
            grids,
            [monster],
            floor_key=(DUNGEON_ANGBAND, 40, 0),
            inventory=[
                item("t", SCROLL, SV_SCROLL_TELEPORT),
                item("h", POTION, SV_POTION_HEALING),
            ],
        )
        policy = HengbotPolicy(monrace_knowledge={1124: knowledge})
        with patch.object(
            policy, "_predicted_damage",
            side_effect=lambda _snapshot, _hostiles, turns, **_kwargs: {
                3: 228, 1: 103,
            }[turns],
        ):
            key = policy.choose_key(snapshot)
            self.assertLess(250, policy._low_hp_walk_threshold(533))
            self.assertTrue(policy._ranged_scroll_lock_escape_needed(
                snapshot, snapshot.visible_monsters, predicted=228
            ))
            # Healing 300 outheals the next turn (103).
            self.assertIsNotNone(policy._find_heal_potion(snapshot, expected_damage=103))
        self.assertEqual((key, policy.last_reason), ("rt", "emergency:teleport"))
        self.assertEqual(policy._last_return_trigger, "emergency-ranged-status-lock")


if __name__ == "__main__":
    unittest.main()
