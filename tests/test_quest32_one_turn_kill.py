"""QUEST_32 is taken only once one player turn kills 閾に棲む者 (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「Q32の戦略を作って。受注を急がないクエストなので閾に棲む者を一撃で
倒せる程度の強さを要求する。」 and 「閾に棲む者の召喚魔法を受ける回数を最小化するのが目的なので、
1ターンで倒せれば良い」.  required_force.one_turn_kill: one player turn's expected damage
(melee's blows, or a Magic-Eater's attack device) against race 263 reaches 240, the largest
roll of its 30d8 (no FORCE_MAXHP: one-monster-placer.cpp rolls the dice).

Recorded: the newest town arrivals of 2026-11-19 (tests/extract_quest32_one_turn_kill_1119_fixtures.py),
all three in the Outpost with Q32 offered:

* n1-c life-217 (Magic-Eater Lv36): melee 231.8, devices 72.2 -- short of 240, refused, and the
  quest asks it no kit; it also lacks resist_fear.  Its head is Q18 (untaken), not Q32: Q32 is
  ordered after Q25 (FIXED_QUEST_ORDER_LEVEL), so an unready Q32 holds nothing back.
* n1-a life-531 (warrior Lv42): melee 496.9 -- met; it is short only of the four Light scrolls.
* n1-b life-411 (Magic-Eater Lv50): melee 504.6, devices 280 -- met; refused only for not-full-hp.

DECLARED CONSTRUCTED: n1-b's board at full HP (accepted); n1-c's board with resist_fear
(refused by the one-turn kill alone).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import quest_one_turn_kill
from hengbot.policy_constants import FIXED_QUEST_ORDER_LEVEL
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
DWELLER = 263
STUNWALL = 326


def recorded(name):
    """(policy with the shipped strategies, the arrival board)."""
    scratch = tempfile.TemporaryDirectory()
    policy, _, steps = load(FIXTURES / name, Path(scratch.name))
    policy._quest_strategies = load_quest_strategies(STRATEGIES)
    board = steps[0][1]()
    return scratch, policy, board


def readiness(policy, board):
    sink = []
    verdict = policy._evaluate_fixed_quest_readiness(
        board, 32, require_target_town=True, commit=False, telemetry_sink=sink)
    return verdict, sink[0], policy._fixed_quest_readiness.get("strategy_force", {})


class Quest32StrategyTest(unittest.TestCase):
    def test_the_shipped_strategy(self):
        profile = load_quest_strategies(STRATEGIES)[32]
        self.assertTrue(profile.approved)
        force = profile.required_force
        self.assertEqual(force["one_turn_kill"], {"race": DWELLER, "hit_points": 240, "device_classes": [16]})
        self.assertEqual(force["resists"], ["free_action", "confusion", "fear"])
        self.assertTrue(force["floors_replace_projection"])
        self.assertNotIn("launcher", force)
        self.assertEqual(profile.engagement_plan["engage_never_move_races"], [DWELLER, STUNWALL])
        self.assertEqual(profile.engagement_plan["hold_position"], [19, 4])
        self.assertEqual(profile.priority_targets[0], DWELLER)

    def test_a_malformed_requirement_is_not_loaded(self):
        data = json.loads(quest_one_turn_kill_text())
        data["required_force"]["one_turn_kill"] = {"race": DWELLER, "hit_points": "240"}
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_32.jsonc").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with patch("sys.stderr"):
                self.assertNotIn(32, load_quest_strategies(Path(temp)))

    def test_ordered_after_quest_25(self):
        self.assertEqual(FIXED_QUEST_ORDER_LEVEL[32], 49)


def quest_one_turn_kill_text() -> str:
    from hengbot.monrace_knowledge import _strip_jsonc
    return _strip_jsonc((STRATEGIES / "QUEST_32.jsonc").read_text(encoding="utf-8"))


class Quest32RecordedAcceptanceTest(unittest.TestCase):
    def test_n1c_short_of_one_turn_is_refused_and_buys_nothing(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            self.assertEqual((found["melee"], found["device"]), (231.8, 72.2))
            self.assertFalse(quest_one_turn_kill.met(policy, board, force))
            verdict, telemetry, strategy = readiness(policy, board)
            self.assertFalse(verdict)
            self.assertEqual(telemetry["reason"], "strategy-force")
            self.assertEqual(strategy["failed"], ["resists", "one_turn_kill"])
            resolved = policy._strategy_force_for_snapshot(board, policy.approved_quest_strategy(32))
            self.assertEqual((resolved["heal_potions"], resolved["speed_potions"],
                              resolved["required_scrolls"]), (0, 0, {}))
            # The Outpost offers Q32, yet Q18 heads the offers: Q32 waits behind it.
            self.assertTrue(policy._fixed_quest_is_offered(board, 32))
            self.assertEqual(policy._fixed_quest_head(board).id, 18)

    def test_n1c_with_fear_resistance_is_refused_by_the_one_turn_kill_alone(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            player = replace(board.player, abilities=board.player.abilities | {"resist_fear"})
            verdict, _, strategy = readiness(policy, replace(board, player=player))
            self.assertFalse(verdict)
            self.assertEqual(strategy["failed"], ["one_turn_kill"])

    def test_n1a_warrior_kills_it_in_one_melee_turn(self):
        scratch, policy, board = recorded("n1a-531")
        with scratch:
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            self.assertEqual((found["melee"], found["device"], found["means"]), (496.9, 0.0, "melee"))
            verdict, _, strategy = readiness(policy, board)
            self.assertFalse(verdict)
            self.assertEqual(strategy["failed"], ["required_scrolls.light"])
            self.assertEqual(policy._fixed_quest_head(board).id, 32)

    def test_n1b_at_full_hp_is_accepted(self):
        scratch, policy, board = recorded("n1b-411")
        with scratch:
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            self.assertEqual((found["melee"], found["device"], found["means"]), (504.6, 280.0, "melee"))
            verdict, telemetry, _ = readiness(policy, board)
            self.assertEqual((verdict, telemetry["reason"]), (False, "not-full-hp"))
            full = replace(board, player=replace(board.player, hp=board.player.max_hp))
            verdict, telemetry, strategy = readiness(policy, full)
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]), (True, "ready", []))

    def test_the_engaged_never_movers_are_fought_like_the_rest(self):
        scratch, policy, _ = recorded("n1b-411")
        with scratch:
            profile = policy.approved_quest_strategy(32)
            self.assertEqual(policy._quest_never_move_races(profile), set())
            plain = replace(profile, engagement_plan={
                key: value for key, value in profile.engagement_plan.items()
                if key != "engage_never_move_races"})
            self.assertEqual(policy._quest_never_move_races(plain), {DWELLER, STUNWALL})


if __name__ == "__main__":
    unittest.main()
