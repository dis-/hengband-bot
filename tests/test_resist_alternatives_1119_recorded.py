"""Blindness and fear requirements another means stands in for (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「魔道具術師でテレパシーがあるなら盲目でも戦闘に支障はない。また、恐怖
攻撃はヒーローの薬で対処する決まりが既にある。」  resist_alternatives: a Magic-Eater (class 16) with
telepathy needs no resist_blind (cmd-magiceat.cpp:463 refuses absorbed powers only while confused;
monster-update.cpp marks telepathic monsters seen before its blindness return); fear without a
lasting resistance is the heroism rule's carry (heroism_potion.carry_target, 15) -- a shortage is a
carry the town buys, never a missing resistance.

Recorded: n1-c life-217 at 16:15 on 2026-11-19 (Magic-Eater Lv44, telepathy, neither resistance,
14 Potions of Heroism), the town arrival that was refused QUEST_33 for ``resists`` (blindness and
fear) and ``one_turn_kill``, and QUEST_32 for ``resists`` (fear).  Now both read the resistances
ready; the one Heroism short of 15 is the carry ``heroism_potions``; Q33's one_turn_kill stays
failed (its always_hasted speed reading is another branch).

DECLARED CONSTRUCTED: the same board with 15 Potions of Heroism and full HP (the recorded 553/948
reads ``not-full-hp`` past the force: Q32 ready; Q33 then fails on one_turn_kill only -- its max HP
948 meets QUEST_33's min_hp 350 (owner 2026-11-19 「95%の値で計算し直す」, tests/test_quest33_min_hp_p95)); as a warrior (class 0) with the same telepathy (resist_blind is required again);
without telepathy (likewise); with a lasting (equipment) fear resistance (no Heroism carry is
asked); with a hero state only (temporary: the carry is still asked).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import arena_odds, fear_cover, heroism_potion
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "resist-alternatives-1119" / "n1c-217-1615"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
WARRIOR = 0


def recorded():
    scratch = tempfile.TemporaryDirectory()
    policy, _, steps = load(FIXTURE, Path(scratch.name))
    policy._quest_strategies = load_quest_strategies(STRATEGIES)
    return scratch, policy, steps[0][1]()


def readiness(policy, board, quest_id):
    sink = []
    verdict = policy._evaluate_fixed_quest_readiness(
        board, quest_id, require_target_town=False, commit=False, telemetry_sink=sink)
    return verdict, policy._fixed_quest_readiness.get("strategy_force", {})


def with_player(board, **changes):
    return replace(board, player=replace(board.player, **changes))


def with_heroism(board, count):
    inventory = tuple(replace(item, count=count) if heroism_potion.is_heroism(item) else item
                      for item in board.inventory)
    return replace(board, inventory=inventory)


class RecordedN1cTest(unittest.TestCase):
    def test_the_recorded_character(self):
        scratch, _policy, board = recorded()
        with scratch:
            player = board.player
            self.assertEqual((player.class_id, player.level), (16, 44))
            self.assertIn("telepathy", player.abilities)
            self.assertNotIn("resist_blind", player.abilities)
            self.assertNotIn("resist_fear", player.abilities)
            self.assertEqual(heroism_potion.carried(board), 14)

    def test_q33_resists_are_ready_and_fear_is_the_heroism_carry(self):
        scratch, policy, board = recorded()
        with scratch:
            verdict, strategy = readiness(policy, board, 33)
            self.assertFalse(verdict)
            self.assertTrue(strategy["resists"]["ready"])
            self.assertEqual(strategy["failed"], ["heroism_potions", "one_turn_kill"])
            self.assertEqual(strategy["carries"]["heroism_potions"],
                             {"measured": 14, "required": 15, "ready": False})

    def test_q32_is_short_only_of_one_heroism(self):
        scratch, policy, board = recorded()
        with scratch:
            verdict, strategy = readiness(policy, board, 32)
            self.assertFalse(verdict)
            self.assertTrue(strategy["resists"]["ready"])
            self.assertEqual(strategy["failed"], ["heroism_potions"])

    def test_with_fifteen_heroism(self):
        scratch, policy, board = recorded()
        with scratch:
            full = with_heroism(with_player(board, hp=board.player.max_hp), 15)
            verdict, strategy = readiness(policy, full, 32)
            self.assertEqual((verdict, strategy["failed"]), (True, []))
            verdict, strategy = readiness(policy, full, 33)
            # Past the carries the force's own floors are read: max HP 948 meets QUEST_33's 350.
            self.assertEqual((verdict, strategy["failed"]), (False, ["one_turn_kill"]))
            self.assertEqual(strategy["hp"], {"measured": 948, "required": 350})

    def test_a_warrior_with_telepathy_still_needs_resist_blind(self):
        scratch, policy, board = recorded()
        with scratch:
            warrior = with_heroism(with_player(board, class_id=WARRIOR), 15)
            _, strategy = readiness(policy, warrior, 33)
            self.assertFalse(strategy["resists"]["ready"])
            self.assertIn("resists", strategy["failed"])
            self.assertFalse(fear_cover.blind_covered(warrior))

    def test_a_magic_eater_without_telepathy_still_needs_resist_blind(self):
        scratch, policy, board = recorded()
        with scratch:
            blind = with_heroism(with_player(
                board, abilities=board.player.abilities - {"telepathy"}), 15)
            _, strategy = readiness(policy, blind, 33)
            self.assertFalse(strategy["resists"]["ready"])
            self.assertFalse(fear_cover.blind_covered(blind))

    def test_a_lasting_fear_resistance_asks_no_heroism(self):
        scratch, policy, board = recorded()
        with scratch:
            sources = dict(board.player.ability_sources)
            sources["resist_fear"] = frozenset({"equipment"})
            resisted = with_player(board, abilities=board.player.abilities | {"resist_fear"},
                                   ability_sources=sources, hp=board.player.max_hp)
            verdict, strategy = readiness(policy, resisted, 32)
            self.assertNotIn("heroism_potions", strategy["carries"])
            self.assertEqual((verdict, strategy["failed"]), (True, []))

    def test_a_hero_state_is_not_a_lasting_resistance(self):
        scratch, policy, board = recorded()
        with scratch:
            sources = dict(board.player.ability_sources)
            sources["resist_fear"] = frozenset({"temporary"})
            hero = with_player(board, abilities=board.player.abilities | {"resist_fear"},
                               ability_sources=sources)
            _, strategy = readiness(policy, hero, 32)
            self.assertEqual(strategy["failed"], ["heroism_potions"])

    def test_threat_tiers_and_the_arena_read_the_magic_eater_blind_rule(self):
        scratch, policy, board = recorded()
        with scratch:
            self.assertTrue(fear_cover.blind_covered(board))
            blinder = next(k for k in policy._monrace_knowledge.values() if "BLIND" in k.abilities)
            self.assertFalse(arena_odds.open_to_blindness(board, blinder))
            self.assertTrue(arena_odds.open_to_blindness(
                with_player(board, class_id=WARRIOR), blinder))


if __name__ == "__main__":
    unittest.main()
