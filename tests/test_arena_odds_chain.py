"""The arena's chance against an opponent that does not stay beside the character.

Owner 2026-11-05, on 達人超能力者 (race 1056) reading 0: 「直す」.  The cut on the lost actions is
gone: the ranged force counts while the opponent is away, and a fight past the longest one
reads low by itself.

Recorded: tests/fixtures/arena-live-1105.json.gz, the Lv45 warrior's board on the building's
floor.  CONSTRUCTED where a test says so: its ammunition, abilities or HP, or a race's table.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

import numpy as np

from hengbot import arena_fight_chain, arena_odds, attack_expectation
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy

FIXTURE = Path(__file__).with_name("fixtures") / "arena-live-1105.json.gz"
KNOWLEDGE = load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))
MASTER_MINDCRAFTER = 1056
AMMO_TVALS = (16, 17, 18)
# dbad1b58c's judge on this board: races with no teleport, no heal, and a frequency the
# innate gate leaves alone (0 or 50).
UNCHANGED = {1062: ("melee", 0.9999999999999997), 557: ("melee", 0.9999994242501894)}


class ArenaOddsChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.load(stream)["13-poster2"]["board"]

    def setUp(self):
        self.policy = ConservativePolicy(monrace_knowledge=KNOWLEDGE)
        self.snapshot = parse_snapshot(json.loads(json.dumps(self.raw)), KNOWLEDGE)

    def without_ammunition(self):
        return replace(self.snapshot, inventory=[
            item for item in self.snapshot.inventory if item.tval not in AMMO_TVALS])

    def test_the_blinker_is_no_longer_cut_to_zero(self):
        odds = arena_odds.judge(self.policy, self.snapshot, MASTER_MINDCRAFTER)
        self.assertIsNone(odds.refusal)
        self.assertGreater(odds.chance, 0.9)
        self.assertLess(odds.kill_actions, arena_odds.LONGEST_FIGHT_ACTIONS)

    def test_a_character_without_ranged_force_reads_low_against_it(self):
        # CONSTRUCTED: no ammunition, and melee at a Lv30 fighter's size.
        board = self.without_ammunition()
        real = attack_expectation.melee
        attack_expectation.melee = lambda *_args, **_kw: 120.0
        self.addCleanup(setattr, attack_expectation, "melee", real)
        odds = arena_odds.judge(self.policy, board, MASTER_MINDCRAFTER)
        self.assertLess(odds.chance, 0.5)
        self.assertGreater(odds.kill_actions, 100)

    def test_ranged_force_shortens_the_same_fight(self):
        race = replace(KNOWLEDGE[MASTER_MINDCRAFTER], abilities=KNOWLEDGE[MASTER_MINDCRAFTER].abilities - {"HEAL"})
        common = dict(melee=300.0, ratio=2.0, player_level=45, margin=0.85, recovery_per_action=0.8, longest=400)
        walking = arena_fight_chain.run(race, ranged=[], **common)
        firing = arena_fight_chain.run(race, ranged=[(150.0, 50, "launcher")], **common)
        self.assertLess(firing.kill_actions, walking.kill_actions)

    def test_an_opponent_with_no_blink_is_unchanged(self):
        for race, (plan, chance) in UNCHANGED.items():
            self.assertFalse(arena_fight_chain.applies(KNOWLEDGE[race]))
            odds = arena_odds.judge(self.policy, self.snapshot, race)
            self.assertEqual(odds.plan, plan)
            self.assertAlmostEqual(odds.chance, chance, places=12)

    def test_the_spell_choice_follows_the_game(self):
        race = KNOWLEDGE[MASTER_MINDCRAFTER]
        arena_race, beside = arena_odds._selection(race)
        self.assertAlmostEqual(beside["BLINK"], 0.772, places=3)  # distance < 4: 75% first
        self.assertNotIn("HEAL", beside)  # full HP
        self.assertNotIn("TPORT", beside)
        far = arena_fight_chain.selection_at(arena_race, arena_fight_chain.FAR, 0)
        self.assertLess(far["BLINK"], 0.1)
        self.assertGreater(far["BO_NETH"], 0.25)
        low = arena_fight_chain.selection_at(arena_race, arena_fight_chain.ADJACENT, 2)
        self.assertAlmostEqual(low["HEAL"], 0.5, places=2)
        self.assertGreater(low["TPORT"], 0.05)

    def test_the_innate_gate_is_the_game_s(self):
        # make_attack_spell: below frequency 50 the innate abilities leave the list in that branch.
        dragon = KNOWLEDGE[646]
        self.assertLess(dragon.spell_frequency, 50)
        _race, selection = arena_odds._selection(dragon)
        breaths = sum(share for ability, share in selection.items() if ability.startswith("BR_"))
        self.assertLessEqual(breaths, dragon.spell_frequency * 2 / 100 + 1e-9)
        # A caster of the same frequency casts in both branches, at every place of the chain.
        caster, _selection = arena_odds._selection(KNOWLEDGE[1058])
        self.assertLess(caster.spell_frequency, 50)
        self.assertGreater(sum(arena_fight_chain.selection_at(caster, arena_fight_chain.FAR, 0).values()), 0.95)

    def test_only_adjacent_actions_hold_a_melee_round(self):
        race = KNOWLEDGE[MASTER_MINDCRAFTER]
        arena_race, beside = arena_odds._selection(race)
        adjacent = arena_odds.monster_action_distribution(self.policy, self.snapshot, race, arena_race, beside)
        away = arena_odds.monster_action_distribution(
            self.policy, self.snapshot, race, arena_race, beside, adjacent=False)
        self.assertAlmostEqual(float(away.sum()), 1.0)
        self.assertGreater(adjacent @ np.arange(adjacent.size), away @ np.arange(away.size))

    def test_brain_smash_and_mind_blast_need_their_resistances(self):
        # CONSTRUCTED: the resistances off.  effect_player_brain_smash, effect_player_mind_blast.
        race = replace(KNOWLEDGE[1180], abilities=frozenset({"BRAIN_SMASH"}), blows=())
        player = self.snapshot.player
        open_board = replace(self.snapshot, player=replace(
            player, abilities=player.abilities - {"free_action", "resist_conf"}))
        self.assertEqual(arena_odds.refusal(open_board, race, True), "paralysis")
        race = replace(race, abilities=frozenset({"MIND_BLAST"}))
        self.assertEqual(arena_odds.refusal(open_board, race, True), "confusion")

    def test_the_launcher_reads_the_figure_the_game_shows(self):
        ammo = self.policy._matching_ammo(self.snapshot)
        shown = replace(ammo, name="クロスボウの矢 (1d5) (+3,+3) (95/shot 71/turn)")
        board = replace(self.snapshot, inventory=[
            shown if item is ammo else item for item in self.snapshot.inventory])
        self.policy._matching_ammo = lambda _board: shown
        self.assertEqual(arena_odds.launcher_per_action(self.policy, board),
                         (71 * arena_odds.LAUNCHER_HIT_MARGIN, ammo.count))

    def test_a_power_s_uses_end(self):
        race = replace(KNOWLEDGE[MASTER_MINDCRAFTER], abilities=frozenset({"BLINK", "BO_NETH"}))
        common = dict(melee=0.0, ratio=1.0, player_level=45, margin=1.0, recovery_per_action=0.0, longest=50)
        self.assertLess(arena_fight_chain.run(race, ranged=[(50.0, 3, "power")], **common).kill_at.sum(), 1e-9)
        self.assertGreater(arena_fight_chain.run(race, ranged=[(50.0, 40, "power")], **common).kill_at.sum(), 0.9)

    def test_a_burst_ends_what_the_heals_would_stall(self):
        # The mean HP would hang at the band edge; one blow from 1/3 HP kills.
        race = KNOWLEDGE[MASTER_MINDCRAFTER]
        fight = arena_fight_chain.run(race, melee=500.0, ranged=[(40.0, 40, "launcher")], ratio=1.0,
                                      player_level=45, margin=0.85, recovery_per_action=0.8, longest=400)
        self.assertGreater(fight.kill_at.sum(), 0.99)

    def test_the_fewest_actions_count_the_walk(self):
        ranged = [(100.0, 5, "power"), (50.0, 2, "launcher")]
        self.assertFalse(arena_fight_chain.melee_is_fewest(300.0, ranged, 150.0, 4))  # 6 against 3
        self.assertTrue(arena_fight_chain.melee_is_fewest(300.0, ranged, 150.0, 0))  # 2 against 3
        self.assertFalse(arena_fight_chain.melee_is_fewest(300.0, ranged, 0.0, 0))  # melee refused
        # The powers end: 600 HP is 5 + 2 uses, then the walk and the rest by melee.
        self.assertAlmostEqual(float(arena_fight_chain.actions_by_ranged(600.0, ranged, 100.0, 3)), 7.0)
        self.assertAlmostEqual(float(arena_fight_chain.actions_by_ranged(700.0, ranged, 100.0, 3)), 7.0 + 3 + 1)

    # --- the Magic-Eater's odds: the same plan as arena.fight_key (owner 2026-11-05)

    def magic_eater(self, *rows):
        lists = {}
        for kind, row in rows:
            lists.setdefault(kind, []).append(row)
        self.policy._me_device_lists = {kind: (0, tuple(found)) for kind, found in lists.items()}
        return replace(self.snapshot, player=replace(self.snapshot.player, class_id=16))

    def test_the_odds_read_the_hasted_ratio_when_speed_is_held(self):
        bolt = ("wand", {"name": "ファイア・ボルト", "success": 95, "current": 9})
        race = 1062
        plain = arena_odds.judge(self.policy, self.magic_eater(bolt), race)
        hasted = arena_odds.judge(
            self.policy, self.magic_eater(bolt, ("staff", {"name": "スピード", "success": 95, "current": 3})), race)
        self.assertLess(hasted.monster_actions_per_action, plain.monster_actions_per_action * 0.7)
        low_rate = arena_odds.judge(
            self.policy, self.magic_eater(bolt, ("staff", {"name": "スピード", "success": 79, "current": 3})), race)
        self.assertEqual(low_rate.monster_actions_per_action, plain.monster_actions_per_action)

    def test_the_odds_count_healing_only_above_the_rate(self):
        # CONSTRUCTED: a hard opponent at low HP.
        def chance(success):
            board = self.magic_eater(("staff", {"name": "体力回復", "success": success, "current": 9}))
            weak = replace(board, player=replace(board.player, hp=300))
            return arena_odds.judge(self.policy, weak, 1185).chance
        self.assertGreater(chance(81), chance(80))


if __name__ == "__main__":
    unittest.main()
