"""QUEST_33 (クローン地獄): the max-HP requirement re-read at the 95% value (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「95%の値で計算し直す」 -- the min_hp of 1000 (578 = two Grendels' blows
at their maximum with the SUPERHURT critical doubled, a Dagon water bolt at 138 and a Cleaner round
at 80, over 0.6) was judged too high.  The same corridor scene is read with the bot's 即死 reading
(``instant_death.next_action_p95``, threat_prediction's ``operational_total``: the damage taken
before the player acts again, 95% value, through the player's AC), the plan fighting hasted (every
+10 monster acts once a player action), and the requirement is the HP that takes it once above the
withdrawal line: p95 / (1 - 0.4).

The force has no AC-dependent HP floor, so the figure is read at a reference AC: the lowest of the
three recorded town arrivals (n1-c life-217, AC 91): 198 / 0.6 = 330 -> 350.

Recorded: the town arrivals of 2026-11-19 (tests/fixtures/quest32-one-turn-kill-1119: n1-a
life-531 AC 141, n1-b life-411 AC 115, n1-c life-217 AC 91) and n1-c life-217 at 16:15
(tests/fixtures/resist-alternatives-1119/n1c-217-1615, AC 110, max HP 948).

DECLARED CONSTRUCTED: each board moved onto the Q33 floor (test_quest33_alignment_split.on_floor)
with the quest map as known grids, the player at the corridor stand [15,38] at full HP and his
permanent speed + 10 (the always-hasted plan), two Grendels (431) beside at [15,37] [14,37], a
Cleaner (451) beside at [14,38] and a Dagon (595) in line at [15,42], each monster carrying its
race's speed, level and the per-monster maximum damages the game exports for it (model.py reads
them from the race knowledge).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import quest_alignment_split, threat_tiers
from hengbot.model import GridState, Position
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.quest_plan_base import _navigator
from hengbot.quest_strategies import load_quest_strategies
from tests import test_resist_alternatives_1119_recorded as resist_tests
from tests.test_quest33_alignment_split import QUEST, STRATEGIES, monster, on_floor, quest_dir, recorded

GRENDEL, CLEANER, DAGON = 431, 451, 595
STAND = (15, 38)
SCENE = ((GRENDEL, (15, 37)), (GRENDEL, (14, 37)), (CLEANER, (14, 38)), (DAGON, (15, 42)))
WITHDRAWAL = 0.4
MIN_HP = 350
# (fixture, AC, next-action p95 on the scene hasted)
RECORDED = (("n1a-531", 141, 112), ("n1b-411", 115, 157), ("n1c-217", 91, 198))


def grids(policy, board):
    """The quest map as known grids (tests/test_quest33_summon_answer)."""
    navigator = _navigator(policy, on_floor(policy, board, STAND), QUEST)
    known = {}
    for (y, x), kind in navigator.battlefield.terrain.items():
        sight = kind in quest_alignment_split._SIGHT_KINDS
        door = kind == "door"
        known[Position(y, x)] = GridState(
            position=Position(y, x), known=True,
            passable=kind in {"floor", "exit", "passage", "shallow_water"},
            wall=not sight and not door, has_monster=False, has_down_stairs=False,
            has_up_stairs=kind == "exit", unsafe=False, is_closed_door=door, is_door=door,
            allows_los=sight)
    return known


def scene(policy, board, *, speed_bonus=10, turn=1):
    """DECLARED CONSTRUCTED (module docstring)."""
    monsters = []
    for index, (race, cell) in enumerate(SCENE, 1):
        knowledge = policy._monrace_knowledge[race]
        monsters.append(replace(
            monster(policy, index, race, cell), distance=Position(*STAND).distance_to(Position(*cell)),
            speed=knowledge.speed, level=knowledge.level, max_melee_damage=knowledge.max_melee_damage,
            max_ranged_damage=knowledge.max_ranged_damage))
    snapshot = replace(on_floor(policy, board, STAND, monsters=tuple(monsters), turn=turn),
                       grids=grids(policy, board))
    player = replace(snapshot.player, hp=snapshot.player.max_hp, speed=snapshot.player.speed + speed_bonus)
    return replace(snapshot, player=player)


def requirement(p95):
    return math.ceil(p95 / (1 - WITHDRAWAL))


class Quest33MinHpP95Test(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")

    def test_the_shipped_figure(self):
        force = load_quest_strategies(STRATEGIES)[QUEST].required_force
        self.assertEqual(force["min_hp"], MIN_HP)
        self.assertEqual([row["min_hp"] for row in force["force_alternatives"]], [MIN_HP])
        self.assertEqual(load_quest_strategies(STRATEGIES)[QUEST].abort_conditions["hp_ratio"], WITHDRAWAL)

    def test_the_scene_read_on_each_recorded_board(self):
        for name, ac, p95 in RECORDED:
            with self.subTest(name):
                scratch, policy, board = recorded(name)
                with scratch:
                    self.assertEqual(board.player.ac, ac)
                    snapshot = scene(policy, board)
                    found = threat_tiers.instant_death(policy, snapshot)
                    self.assertEqual(found.next_action_p95, p95)
                    self.assertFalse(found.holds)
                    # Hasted, every +10 monster of the scene acts once before the player acts again.
                    rows = policy.threat_prediction(snapshot, snapshot.visible_monsters, 1)["monsters"]
                    self.assertEqual({row["actions"] for row in rows}, {1})
                    self.assertLessEqual(requirement(p95), MIN_HP)
                    # Each recorded character's max HP meets the figure.
                    self.assertGreaterEqual(board.player.max_hp, MIN_HP)
        # The reference: the lowest recorded AC (n1-c, 91): 198 / 0.6 = 330, rounded up to 350.
        self.assertEqual(requirement(198), 330)
        self.assertEqual(max(requirement(p95) for _, _, p95 in RECORDED), 330)

    def test_unhasted_the_monsters_act_twice(self):
        # Control: without the haste (n1-a's +4 against the +10 monsters) the same scene reads two
        # actions each, so the always-hasted plan is what keeps the figure at one round.
        scratch, policy, board = recorded("n1a-531")
        with scratch:
            hasted = threat_tiers.instant_death(policy, scene(policy, board, turn=1)).next_action_p95
            plain = threat_tiers.instant_death(policy, scene(policy, board, speed_bonus=0, turn=2)).next_action_p95
            self.assertEqual((hasted, plain), (112, 234))

    def test_n1c_recorded_readiness_reads_the_new_requirement(self):
        scratch, policy, board = resist_tests.recorded()
        with scratch:
            full = resist_tests.with_heroism(resist_tests.with_player(board, hp=board.player.max_hp), 15)
            verdict, strategy = resist_tests.readiness(policy, full, QUEST)
            self.assertEqual(strategy["hp"], {"measured": 948, "required": MIN_HP})
            # Refused or not for its other rows (carries, firepower), HP is not among them.
            self.assertNotIn("hp", strategy["failed"])

    def test_revert_proof_the_old_figure_refuses_n1c_for_hp(self):
        data = json.loads(_strip_jsonc((STRATEGIES / "QUEST_33.jsonc").read_text(encoding="utf-8")))
        data["required_force"]["min_hp"] = 1000
        for row in data["required_force"]["force_alternatives"]:
            row["min_hp"] = 1000
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_33.jsonc").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            old = load_quest_strategies(Path(temp))
        self.assertEqual(old[QUEST].required_force["min_hp"], 1000)
        scratch, policy, board = resist_tests.recorded()
        with scratch:
            policy._quest_strategies = old
            full = resist_tests.with_heroism(resist_tests.with_player(board, hp=board.player.max_hp), 15)
            verdict, strategy = resist_tests.readiness(policy, full, QUEST)
            self.assertEqual(strategy["hp"], {"measured": 948, "required": 1000})
            self.assertFalse(verdict)
            self.assertIn("hp", strategy["failed"])


if __name__ == "__main__":
    unittest.main()
