"""An ``always_hasted`` quest row doses and is read hasted at +10 or more too (owner 2026-11-19).

Owner 2026-11-19, to 「Q33 など加速して戦う作戦で、素の速度が既に +10 以上のキャラもスピードの薬を
飲み、火力の判定も加速した速度で読むか」, verbatim: 「+10 以上でも飲んで読む」.

Game (C:/hengband/src): a Potion of Speed is set_acceleration (object-use/quaff/quaff-effects.cpp
``speed()``: randint1(25) + 15), and while the acceleration is active ``is_fast`` holds
(player/player-status.cpp) and PlayerSpeed::time_effect_bonus adds +10
(player-status/player-speed.cpp), summed with every other bonus in PlayerStatusBase::get_value up
to +99: the haste adds +10 on top of any permanent speed.

So quest_plan_base ``_speed`` doses an ``always_hasted`` row whenever the haste is off (the
heavy-fight dose of the other rows keeps its PERMANENT_HASTE_SPEED stop),
attack_expectation.always_hasted_speed is the permanent speed + 10, and QUEST_33's
``one_turn_kill`` has the "hasted" tier, on which quest_force_rows takes the gear-speed waiver
out of its rows (the doses are carried, or an absorbed Speed power holds them).

Recorded: n1-c life-217's town arrival of 2026-11-19 16:15 (tests/fixtures/quest33-haste-above-ten-1119,
Magic-Eater, permanent +12 shown +22 yellow, max HP 948): melee 244.9 a turn against
クイーン・アント, 538.9 per 10 game turns at +12 (it was read there, no dose at +10 or more) and
783.8 at +22: the 750 line is met hasted; it is refused for blindness and fear and its HP.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import attack_expectation, quest_one_turn_kill, quest_plan_base
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load
from tests import test_q18_water_cave as q18

FIXTURE = Path(__file__).with_name("fixtures") / "quest33-haste-above-ten-1119" / "n1c-217-1615"
QUEST32_FIXTURES = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"


def recorded(path=FIXTURE):
    scratch = tempfile.TemporaryDirectory()
    policy, _, steps = load(path, Path(scratch.name))
    policy._quest_strategies = load_quest_strategies(STRATEGIES)
    return scratch, policy, steps[0][1]()


def readiness(policy, board):
    sink = []
    verdict = policy._evaluate_fixed_quest_readiness(
        board, 33, require_target_town=False, commit=False, telemetry_sink=sink)
    return verdict, sink[0], policy._fixed_quest_readiness.get("strategy_force", {})


def at_speed(board, permanent):
    """DECLARED CONSTRUCTED: the board with that permanent speed (still hasted, yellow +10) and
    the max HP Q33 asks, at full HP."""
    return replace(board, player=replace(board.player, speed=permanent + 10, max_hp=1000, hp=1000))


class RecordedN1c1615Test(unittest.TestCase):
    def test_the_queen_line_is_met_hasted(self):
        scratch, policy, board = recorded()
        with scratch:
            force = policy.approved_quest_strategy(33).required_force
            found = quest_one_turn_kill.details(policy, board, force)
            self.assertEqual((found["melee"], found["device"], found["means"]), (244.9, 190.0, "melee"))
            self.assertEqual(found["speed"], {"permanent": 122, "hasted": 132})
            self.assertEqual(found["per_10_game_turns"], {"permanent": 538.9, "hasted": 783.8})
            self.assertEqual(found["tier"], "hasted")
            verdict, telemetry, strategy = readiness(policy, board)
            # Still refused: blindness and fear are missing (and max HP 948 is below 1000).
            self.assertEqual((verdict, telemetry["reason"], strategy["failed"]),
                             (False, "strategy-force", ["resists"]))
            self.assertEqual(strategy["hp"], {"measured": 948, "required": 1000})


class HastedTierAsksTheDosesTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: n1-c's board at a permanent +20 with HP 1000 and the turn pinned at
    220 melee (660 at +20, 836 at +30) and 150 by device (at full HP 1000 the Powerful Activation
    would pay), so only the hasted reading meets 750."""

    def setUp(self):
        self.scratch, self.policy, board = recorded()
        self.board = at_speed(board, 130)
        self.profile = self.policy.approved_quest_strategy(33)

    def tearDown(self):
        self.scratch.cleanup()

    def resolve(self, absorbed):
        with patch("hengbot.attack_expectation.melee_against", return_value=220.0),                 patch("hengbot.attack_expectation.devices_against", return_value=150.0), \
                patch("hengbot.me_capability.replaced_by_absorbed", return_value=absorbed):
            tier = quest_one_turn_kill.tier(self.policy, self.board, self.profile.required_force)
            return tier, self.policy._strategy_force_for_snapshot(self.board, self.profile)

    def test_the_gear_speed_waives_nothing_on_the_hasted_tier(self):
        tier, force = self.resolve(absorbed=False)
        self.assertEqual(tier, "hasted")
        # +20 gear met the row's gear_speed_bonus 20, but the line needs the dose: ten potions.
        self.assertEqual(force["speed_potions"], 10)
        self.assertNotIn("gear_speed_bonus", force.get("speed_alternatives", {}))

    def test_an_absorbed_speed_still_stands_for_the_potions(self):
        tier, force = self.resolve(absorbed=True)
        self.assertEqual(tier, "hasted")
        self.assertEqual(force["speed_potions"], 0)


class FullTierKeepsTheGearWaiverTest(unittest.TestCase):
    def test_n1b_at_plus_25_reaches_the_line_unhasted(self):
        scratch, policy, board = recorded(QUEST32_FIXTURES / "n1b-411")
        with scratch, patch("hengbot.me_capability.replaced_by_absorbed", return_value=False):
            profile = policy.approved_quest_strategy(33)
            found = quest_one_turn_kill.details(policy, board, profile.required_force)
            self.assertEqual(found["per_10_game_turns"], {"permanent": 1452.4, "hasted": 1659.8})
            self.assertEqual(found["tier"], "full")
            force = policy._strategy_force_for_snapshot(board, profile)
            self.assertEqual(force["speed_potions"], 0)
            # The gear-waived row is read at the permanent speed, the dosing row hasted.
            rows = profile.required_force["force_alternatives"]
            self.assertEqual(attack_expectation.row_speed(board, profile.required_force, rows[0]), 135)
            self.assertEqual(attack_expectation.row_speed(board, profile.required_force,
                                                          profile.required_force), 145)


class PlanDosesAtPlusTenOrMoreTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: Q18's recorded seahorse board (the free choke, tests/test_q18_water_cave)
    at a permanent +15, unhasted."""

    @staticmethod
    def raw(speed):
        raw = copy.deepcopy(q18.LIVE[2723443])
        raw["player"].update(y=1, x=12, speed=speed)
        raw["player"]["speed_display"] = {"color": "light_green", "riding": False, "text": "",
                                          "value": speed - 110}
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in q18.AMMO_TVALS]
        raw["equipment"] = [item for item in raw["equipment"] if item["slot"] != "bow"]
        return raw

    def test_the_always_hasted_row_doses_at_plus_15(self):
        key, reason, _ = q18.decide(self.raw(125))
        self.assertEqual((key, reason), ("qa", quest_plan_base.SPEED_REASON))

    def test_the_heavy_fight_dose_of_other_rows_still_stops_at_plus_10(self):
        # The row not always hasted, a heavy fight projected: the dose stops at +10.
        for speed, dosed in ((115, True), (125, False)):
            raw = self.raw(speed)
            policy = q18.new_policy(raw)
            snapshot = q18.parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            profile = q18.STRATEGIES[18]
            force = {key: value for key, value in policy._strategy_force_for_snapshot(snapshot, profile).items()
                     if key != "always_hasted"}
            board = SimpleNamespace(coming_in_view=[object()])
            with patch.object(policy, "_strategy_force_for_snapshot", return_value=force), \
                    patch.object(policy, "threat_prediction", return_value={"operational_total": 10 ** 6}):
                key = quest_plan_base._speed(policy, snapshot, profile, board)
            self.assertEqual(key is not None, dosed, speed)


if __name__ == "__main__":
    unittest.main()
