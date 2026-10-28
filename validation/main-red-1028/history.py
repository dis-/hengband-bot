"""Reproduce the six issue #47 pins on each main first-parent revision."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT.parent / "main-red-1028-history"
OUT = Path(__file__).resolve().parent
TESTS = [
    "tests.test_equipment_in_home_stage1.EquipmentInHomeBehaviorPins.test_supplementary_planner_admits_pack_space_deposit_inside_home",
    "tests.test_keep_running_a0.DepartureTest.test_existing_supply_stockout_fallback_and_exhausted_hard_stop",
    "tests.test_optimizer_lamp_recorded.OptimizerLampRecordedTest.test_worn_lantern_withdraws_the_home_lamp_before_departure",
    "tests.test_recall_churn_stockout_recorded.RecallChurnStockoutRecordedTest.test_supply_stockout_owner_keeps_its_three_round_stop",
    "tests.test_town_plan_exhausted_wander.TownPlanExhaustedWanderTest.test_p5_unaffordable_return_still_names_the_missing_entrance",
    "tests.test_town_terminal_declarations.TerminalDeclarationTest.test_1_every_entry_rung_is_declared",
]
revisions = subprocess.check_output(
    ["git", "rev-list", "--first-parent", "--reverse", "524054b47..main"],
    cwd=ROOT, text=True,
).splitlines()
revisions.insert(0, subprocess.check_output(
    ["git", "rev-parse", "524054b47"], cwd=ROOT, text=True).strip())
subprocess.run(["git", "worktree", "add", "--detach", str(HISTORY), revisions[0]],
               cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
               stderr=subprocess.PIPE)
env = dict(os.environ, PYTHONPATH="src;tests;scripts", PYTHONIOENCODING="utf-8")
try:
    for revision in revisions:
        subprocess.run(["git", "checkout", "--detach", revision], cwd=HISTORY,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        result = subprocess.run([sys.executable, "-m", "unittest", "-v", *TESTS],
                                cwd=HISTORY, env=env, capture_output=True)
        (OUT / f"history-{revision[:9]}.log").write_bytes(result.stdout + result.stderr)
        print(json.dumps({"revision": revision, "exit_code": result.returncode,
                          "log": f"history-{revision[:9]}.log"}), flush=True)
finally:
    subprocess.run(["git", "worktree", "remove", str(HISTORY)], cwd=ROOT, check=True)
