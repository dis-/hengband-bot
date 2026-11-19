"""QUEST_32 is taken only once one player turn kills 閾に棲む者 (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「Q32の戦略を作って。受注を急がないクエストなので閾に棲む者を一撃で
倒せる程度の強さを要求する。」 and 「閾に棲む者の召喚魔法を受ける回数を最小化するのが目的なので、
1ターンで倒せれば良い」.  required_force.one_turn_kill: one player turn's expected damage
(melee's blows, or a Magic-Eater's attack device) against race 263 reaches 240, the largest
roll of its 30d8 (no FORCE_MAXHP: one-monster-placer.cpp rolls the dice).  Owner's answers of
the same day: 「加速手段が十分なら135以上で良いとする」 (135 with two haste doses carried, read by
quest_force_rows' haste reader) and 「条件を満たした時だけ割り込む」 (non_urgent: an unmet Q32 is
passed over in the fixed-quest order, a met one is taken in its level-25 place).

Owner 2026-11-19 (later the same day), verbatim: 「攻撃力の判定を1行動あたりではなく、10ゲームターン
あたりのダメージで評価して」 (scope 「攻撃力の判定すべて」): the figure is per 10 game turns, the
per-action one times speed_energy / 10.  At the permanent speed it is the "full" tier; reached only
at the permanent speed + 10 it is the "hasted" tier, which asks the two doses (the earlier 135 line
is this one read hasted, so ``hasted_hit_points`` left the schema).

Recorded: the newest town arrivals of 2026-11-19 (tests/extract_quest32_one_turn_kill_1119_fixtures.py),
all three in the Outpost with Q32 offered:

* n1-c life-217 (Magic-Eater Lv36, permanent +6, hasted on the board): melee 231.8, devices 72.2;
  per action it was the hasted tier (135..240), per 10 game turns at +6 (energy 16) it is 370.8,
  the full tier: no Speed dose is asked; it is refused only for lacking resist_fear, and Q32 heads
  its offers ahead of Q18 (met: it takes its level-25 place).
* n1-a life-531 (warrior Lv42, +4): melee 496.9 (695.6 per 10 game turns) -- met; it is short only
  of the four Light scrolls.
* n1-b life-411 (Magic-Eater Lv50, +25): melee 504.6 (1766.2), devices 280 -- met; refused only for
  not-full-hp.

DECLARED CONSTRUCTED: n1-b's board at full HP (accepted); n1-c's board with resist_fear and full HP
(accepted on the full tier); with three blows a turn instead of seven (99.3 a turn: 158.9 per 10
game turns at +6, 258.3 hasted at +16 -- the hasted tier: accepted with its absorbed Speed,
refused without it and with no potion, two Speed potions asked); with two blows (66.2, the device's
72.2 is larger: 115.5 and 187.7 -- no tier: refused, no kit, and Q18 heads the offers instead).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import quest_one_turn_kill
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
        self.assertEqual(force["one_turn_kill"], {"race": DWELLER, "hit_points": 240,
                                                  "haste_doses": 2, "device_classes": [16]})
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

    def test_the_hasted_tier_and_the_order(self):
        force = load_quest_strategies(STRATEGIES)[32].required_force
        self.assertEqual(force["one_turn_kill"]["haste_doses"], 2)
        self.assertNotIn("hasted_hit_points", force["one_turn_kill"])
        self.assertTrue(force["non_urgent"])

    def test_the_per_action_hasted_line_is_not_loaded(self):
        data = json.loads(quest_one_turn_kill_text())
        data["required_force"]["one_turn_kill"]["hasted_hit_points"] = 135
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "QUEST_32.jsonc").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with patch("sys.stderr"):
                self.assertNotIn(32, load_quest_strategies(Path(temp)))


def quest_one_turn_kill_text() -> str:
    from hengbot.monrace_knowledge import _strip_jsonc
    return _strip_jsonc((STRATEGIES / "QUEST_32.jsonc").read_text(encoding="utf-8"))


class Quest32RecordedAcceptanceTest(unittest.TestCase):
    def test_n1c_on_the_full_tier_heads_the_offers(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            # Per action it was the hasted tier (231.8 < 240); per 10 game turns at its permanent
            # +6 (energy 16; the board's +16 is a timed haste) it is 370.8.
            self.assertEqual((found["melee"], found["device"], found["speed"]["permanent"],
                              found["per_10_game_turns"]["permanent"], found["tier"]),
                             (231.8, 72.2, 116, 370.8, "full"))
            resolved = policy._strategy_force_for_snapshot(board, policy.approved_quest_strategy(32))
            # The full tier asks no haste: the force's own Speed potion, no departure flag.
            self.assertEqual((resolved["speed_potions"], resolved.get("speed_required_to_depart")), (1, None))
            verdict, telemetry, strategy = readiness(policy, board)
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]),
                             (False, "strategy-force", ["resists"]))
            self.assertTrue(policy._fixed_quest_is_offered(board, 32))
            self.assertEqual(policy._fixed_quest_head(board).id, 32)

    def test_n1c_is_accepted(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            player = replace(board.player, abilities=board.player.abilities | {"resist_fear"},
                             hp=board.player.max_hp)
            verdict, telemetry, strategy = readiness(policy, replace(board, player=player))
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]), (True, "ready", []))

    def test_n1c_with_three_blows_is_on_the_hasted_tier(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            player = replace(board.player, abilities=board.player.abilities | {"resist_fear"},
                             hp=board.player.max_hp, main_hand_blows=3)
            constructed = replace(board, player=player)
            force = policy.approved_quest_strategy(32).required_force
            found = quest_one_turn_kill.details(policy, constructed, force)
            self.assertEqual((found["melee"], found["per_10_game_turns"], found["tier"]),
                             (99.3, {"permanent": 158.9, "hasted": 258.3}, "hasted"))
            resolved = policy._strategy_force_for_snapshot(constructed, policy.approved_quest_strategy(32))
            # The absorbed Speed holds the two doses: no potion asked, carried at departure.
            self.assertEqual((resolved["speed_potions"], resolved["speed_required_to_depart"]), (0, True))
            verdict, telemetry, strategy = readiness(policy, constructed)
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]), (True, "ready", []))

    def test_n1c_with_three_blows_without_haste_is_refused(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch, patch("hengbot.me_capability.replaced_by_absorbed", return_value=False):
            player = replace(board.player, abilities=board.player.abilities | {"resist_fear"},
                             hp=board.player.max_hp, main_hand_blows=3)
            constructed = replace(board, player=player)
            resolved = policy._strategy_force_for_snapshot(constructed, policy.approved_quest_strategy(32))
            self.assertEqual(resolved["speed_potions"], 2)
            verdict, _, strategy = readiness(policy, constructed)
            self.assertFalse(verdict)
            self.assertEqual(strategy["failed"], ["speed_potions"])

    def test_n1c_short_of_both_tiers_is_passed_over_for_q18(self):
        scratch, policy, board = recorded("n1c-217")
        with scratch:
            weak = replace(board, player=replace(board.player, main_hand_blows=2))
            force = policy.approved_quest_strategy(32).required_force
            self.assertEqual(quest_one_turn_kill.details(policy, weak, force)["per_10_game_turns"],
                             {"permanent": 115.5, "hasted": 187.7})
            self.assertIsNone(quest_one_turn_kill.tier(policy, weak, force))
            verdict, _, strategy = readiness(policy, weak)
            self.assertFalse(verdict)
            self.assertIn("one_turn_kill", strategy["failed"])
            resolved = policy._strategy_force_for_snapshot(weak, policy.approved_quest_strategy(32))
            self.assertEqual((resolved["heal_potions"], resolved["speed_potions"],
                              resolved["required_scrolls"]), (0, 0, {}))
            # Q32 is offered and level 25, yet the unmet non_urgent quest does not block Q18.
            self.assertTrue(policy._fixed_quest_is_offered(weak, 32))
            self.assertTrue(quest_one_turn_kill.holds_back(policy, weak, 32))
            self.assertEqual(policy._fixed_quest_head(weak).id, 18)

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
