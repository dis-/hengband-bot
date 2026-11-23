"""The floor plans' contract, their one walk and their survival stage (2026-11-23).

Whole-bot maintainability review 2026-11-23 K1: the quest plans pre-empted the generic ladder and each
kept its own walking, survival and attack choices; only quest25_battle's ``_path`` knew the cells not to
pass.  (a)-4: quest_plan_base ``Contract`` (stand cells, cells not to pass, recovery line) on every
plan's board, ``plan_walk`` / ``plan_door`` for every step and door of a plan, ``survival_stage`` in
every branch of every FLOOR_PLANS plan.

The boards are the recorded Quest 25 board of n1-c life-221 (tests/fixtures/n1c-221-q25-floor-restore-1123
.json.gz, decision 61363, through tests/test_n1c_221_q25_floor_restore_1123_recorded.py), the policy
restoring the battle record through the real path.  The lint cases edit the repository's sources as
tests/test_dungeon_ladder.py does.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dungeon_ladder_lint as lint  # noqa: E402
from hengbot import dungeon_ladder as ladder, quest25_battle  # noqa: E402
from hengbot import quest25_geometry as geo, quest_plan_base  # noqa: E402
from hengbot.model import Position  # noqa: E402
from tests.test_n1c_220_q25_speed_retry_1122_recorded import WALL_PASSER_KILLS, _Replay  # noqa: E402
from tests.test_n1c_221_q25_floor_restore_1123_recorded import PHASE, board  # noqa: E402

KEY = "8"


class TheContractTest(_Replay):
    def test_the_phase_battle_s_board_carries_its_cells_not_to_pass(self):
        raw = board()
        policy = self.policy(raw, PHASE, WALL_PASSER_KILLS)
        ctx = quest25_battle._ctx(policy, self.snapshot(policy, raw))
        contract = quest25_battle.contract(ctx, ctx.profile.engagement_plan["room_sweep"])
        self.assertIn(geo.DRUJ_DOOR, contract.no_pass)   # the druj lives: its door is not passed
        self.assertIn(geo.DRUJ_AREA_STAND, contract.stand_cells)
        self.assertEqual(contract.recovery_line, 0.9)

    def test_plan_walk_refuses_a_cell_not_to_pass(self):
        raw = board()
        policy = self.policy(raw, PHASE, WALL_PASSER_KILLS)
        snapshot = self.snapshot(policy, raw)
        policy.last_reason = "before"
        step = Position(6, 1)
        self.assertIsNone(quest_plan_base.plan_walk(policy, snapshot, step, "walk", no_pass={(6, 1)}))
        self.assertEqual(policy.last_reason, "before")
        self.assertEqual(quest_plan_base.plan_walk(policy, snapshot, step, "walk"), "2")
        self.assertEqual(policy.last_reason, "walk")


def analyze_with(module, old, new):
    policy_source, sources = lint.repository_sources()
    sources = dict(sources)
    assert old in sources[module], old
    sources[module] = sources[module].replace(old, new, 1)
    return lint.analyze(policy_source, sources)


class TheLintTest(unittest.TestCase):
    def test_the_repository_agrees(self):
        self.assertEqual(lint.analyze_repository(), [])

    def test_a_plan_module_stepping_by_itself_fails(self):
        findings = analyze_with(
            "quest_find_exit",
            "return quest_plan_base.plan_walk(policy, snapshot, exit_cell, STEP_ON_EXIT_REASON)",
            "return policy._step_toward(snapshot, exit_cell)")
        self.assertTrue(any("_step_toward called directly" in finding for finding in findings), findings)

    def test_a_plan_module_keying_a_door_by_itself_fails(self):
        findings = analyze_with(
            "quest25_battle",
            "return quest_plan_base.plan_door(ctx.policy, ctx.snapshot, door, CLOSE_REASON, close=True)",
            "return CLOSE_KEY + _direction(ctx.here, door)")
        self.assertTrue(any("CLOSE_KEY composed directly" in finding for finding in findings), findings)

    def test_a_branch_without_the_survival_stage_fails(self):
        plan = ladder.FLOOR_PLANS[0]
        branch = ladder.Branch("board", (
            (ladder.INSTANT_DEATH, ladder.SURVIVAL), ("_heal", ladder.SURVIVAL),
            ("summon_response.key", ladder.SUMMONS), ("_fight", ladder.OWN)))
        self.assertTrue(any("survival stage" in finding for finding in lint._stage_findings(plan, branch)))
        quiet = ladder.Branch("board", (
            ("summon_response.key", ladder.SUMMONS), (ladder.SURVIVAL_STAGE, ladder.OWN),
            ("_advance", ladder.OWN)), enemy=False)
        self.assertTrue(any("recovery" in finding for finding in lint._stage_findings(plan, quiet)))

    def test_every_plan_branch_enters_the_survival_stage(self):
        for plan in ladder.FLOOR_PLANS:
            for branch in plan.branches:
                if ladder.OWN in [role for _, role in branch.rungs]:
                    with self.subTest(plan=plan.rung, board=branch.board):
                        self.assertIn(ladder.SURVIVAL_STAGE, [name for name, _ in branch.rungs])
                        self.assertEqual(lint._stage_findings(plan, branch), [])

    def test_the_stage_dropped_from_a_plan_module_fails(self):
        findings = analyze_with(
            "quest_room_sweep",
            "            or quest_plan_base.survival_stage(policy, snapshot, profile, board)\n"
            "            or quest_plan_base.floor_restore_key",
            "            or quest_plan_base._restore(policy, snapshot)\n"
            "            or quest_plan_base.floor_restore_key")
        self.assertTrue(any("quest_room_sweep.key: the table says" in finding for finding in findings),
                        findings)

    def test_a_board_without_the_sensed_shooters_or_the_contract_fails(self):
        findings = analyze_with("quest_find_exit", "        self.firing = [monster",
                                "        self.shooting = [monster")
        self.assertTrue(any("does not set self.firing" in finding for finding in findings), findings)
        findings = analyze_with("quest_room_sweep", "        self.contract = contract(plan)\n", "")
        self.assertFalse(any("quest_room_sweep._Board does not set self.contract" in finding
                             for finding in findings), findings)   # quest_plan_base.Board sets it
        findings = analyze_with("quest_plan_base", "        self.contract = NO_CONTRACT\n", "")
        self.assertEqual([finding for finding in findings if "self.contract" in finding], [])
        findings = analyze_with("quest_find_exit", "        self.contract = quest_plan_base.Contract(",
                                "        contract = quest_plan_base.Contract(")
        self.assertTrue(any("does not set self.contract" in finding for finding in findings), findings)


if __name__ == "__main__":
    unittest.main()
