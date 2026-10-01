"""Scoped semantic revert proof; one explicitly named module per process.

Only the Class C3 shop guard or fitting-target hunk is disabled, then restored
byte-for-byte in finally. No gate, broad runner, fixture or assertion is edited.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / "src/hengbot/policy_shop.py"
HOME = ROOT / "src/hengbot/policy_home.py"
saved = {p: p.read_bytes() for p in (SHOP, HOME)}
results = []
env = dict(os.environ, PYTHONPATH="src;tests;scripts",
           PYTHONDONTWRITEBYTECODE="1",
           PYTHONPYCACHEPREFIX=str(ROOT / "reports/classC3-no-bytecode"))


def run(label, pins, expected):
    result = subprocess.run([sys.executable, "-m", "unittest", *pins],
                            cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding="utf8", errors="replace")
    output = result.stdout + result.stderr
    (ROOT / f"reports/classC3-{label}.txt").write_text(output, encoding="utf8")
    results.append({"case": label, "exit_code": result.returncode,
                    "expected_exit_code": expected, "pins": pins})
    (ROOT / "reports/classC3-single-revert.json").write_text(
        json.dumps(results, indent=2), encoding="utf8")
    print(label, result.returncode, output, flush=True)
    if result.returncode != expected:
        raise AssertionError((label, result.returncode, expected))


try:
    source = saved[SHOP].decode("utf8").replace("\r\n", "\n")
    guard = ("                    if store_type in self._town_visit_ledger."
             "nonhome_attempted_without_effect:\n"
             "                        continue\n")
    assert source.count(guard) == 1
    SHOP.write_text(source.replace(guard, "", 1), encoding="utf8")
    run("item1-single-revert", ["tests.test_policy_shop.TownErrandPlanTest."
        "test_non_home_leave_blocks_reopened_out_of_stock_stop"], 1)
    SHOP.write_bytes(saved[SHOP])

    source = saved[HOME].decode("utf8").replace("\r\n", "\n")
    anchor = "        launcher = self._equipped_launcher(snapshot)\n        if launcher is None:\n"
    assert source.count(anchor) == 1
    # Restore the pre-decision target of 99 everywhere that asks this authority.
    HOME.write_text(source.replace(anchor, "        return AMMO_CARRY_TARGET\n" + anchor, 1),
                    encoding="utf8")
    run("item2-single-revert", [
        "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
        "test_recorded_residual_weight_deposits_exactly_four_shots_after_restore",
        "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
        "test_next_visit_buys_only_fitting_count_and_leaves_deposit_home",
    ], 1)
finally:
    for path, data in saved.items():
        path.write_bytes(data)
    results.append({"byte_exact_restoration": {
        str(path.relative_to(ROOT)): path.read_bytes() == data
        for path, data in saved.items()}, "restored_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in saved}})
    (ROOT / "reports/classC3-single-revert.json").write_text(
        json.dumps(results, indent=2), encoding="utf8")

run("item1-restored-pin", ["tests.test_policy_shop.TownErrandPlanTest."
    "test_non_home_leave_blocks_reopened_out_of_stock_stop"], 0)
run("item2-restored-pins", [
    "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
    "test_recorded_residual_weight_deposits_exactly_four_shots_after_restore",
    "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
    "test_next_visit_buys_only_fitting_count_and_leaves_deposit_home",
    "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
    "test_any_remaining_safe_surplus_goes_home_before_guardian_switch",
    "tests.test_classC2_departure_recorded.ClassC2DepartureRecordedTest."
    "test_public_stop_board_offers_deeper_guardian_remedy_after_restore",
], 0)
(ROOT / "reports/classC3-single-revert.json").write_text(
    json.dumps(results, indent=2), encoding="utf8")
