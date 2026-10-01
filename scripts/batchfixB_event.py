"""Write the batchfixB verification/audit event from completed per-module logs."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from assertion_change_audit import functions

DIRECTORY = ROOT / "reports/batchfixB"
LOGS = {
    "tests.test_guardian_recall_pingpong_recorded": "fixed-guardian.txt",
    "tests.test_overweight_home_unreachable_recorded": "fixed-overweight.txt",
    "tests.test_equipment_in_home_stage1": "fixed-equipment-home.txt",
    "tests.test_home_withdraw_failed_stock_present_recorded": "fixed-withdraw-failed.txt",
    "tests.test_home_withdraw_deposit_alternation_recorded": "fixed-alternation.txt",
    "tests.test_declarations_r14": "fixed-r14.txt",
    "tests.test_calibration_live25": "fixed-calibration.txt",
    "tests.test_classC2_departure_recorded": "fixed-classC2.txt",
    "tests.test_classC_departure_remedies": "fixed-classC.txt",
    "tests.test_live36_weight": "fixed-live36.txt",
    "tests.test_town_approach_retired_recorded": "fixed-town-approach.txt",
    "tests.test_identify_staff_live27_recorded": "fixed-live27.txt",
    "tests.test_catcycle": "fixed-catcycle.txt",
    "tests.test_crash_position_key_recorded": "fixed-crash.txt",
    "tests.test_input_executor": "fixed-input-executor.txt",
    "tests.test_test_fakery_lint": "fixed-fakery-lint.txt",
}


def read_log(path):
    data = path.read_bytes()
    return data.decode("utf16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf8").replace("\r\n", "\n")


def main():
    results = {}
    for module, log in LOGS.items():
        text = read_log(DIRECTORY / log)
        count = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
        if count is None or re.search(r"^OK(?: \(.*\))?$", text, re.M) is None:
            raise RuntimeError(f"missing passing result: {module}")
        results[module] = {"tests": int(count[1]), "seconds": float(count[2]), "log": log}
    s33 = read_log(DIRECTORY / "fixed-overweight-s33.txt")
    measurement = json.loads(s33)
    row = measurement["first_divergence"]
    if (row["list_index"], row["historical_sequence"]) != (3715, 3714):
        raise RuntimeError("changed fixed S3.3 first divergence")
    if measurement.get("trajectory_defect") is not None:
        raise RuntimeError("S3.3 trajectory defect")
    audit = subprocess.run([sys.executable, "scripts/assertion_change_audit.py", "--base", "a4e51bf9"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf8", check=True).stdout
    path = "tests/test_home_withdraw_failed_stock_present_recorded.py"
    before = subprocess.check_output(["git", "show", f"a4e51bf9:{path}"], cwd=ROOT, encoding="utf8")
    after = (ROOT / path).read_text(encoding="utf8")
    old_functions, new_functions = functions(before), functions(after)
    changes = []
    for name, old in old_functions.items():
        for previous, current in zip(old.assertions, new_functions[name].assertions):
            if previous != current:
                changes.append({"file": path, "test": name, "before": previous[1], "after": current[1],
                                "quoted_clause": "dual-wield half-max-melee selection, ruling #9",
                                "authority": "fixer-batchfix-common.txt; 7410a5cb game-correct melee bonus distribution"})
    if len(changes) != 6:
        raise RuntimeError("unexpected assertion-change set")
    event = {"topic": "batchfixB", "step": 2, "base": "a4e51bf9", "status": "complete",
             "report": "reports/batchfixB/report.md", "tests": results,
             "s33": measurement, "changed_preexisting_assertions": changes,
             "assertion_audit": audit, "blockers": [],
             "decisions": [
                 {"quote": "dual-wield half-max-melee selection, ruling #9", "evidence": "first-guardian.txt; first-overweight.txt; fixed-withdraw-failed.txt", "conformance": "production optimizer preserved; historical gear is replay input; combat expectations use corrected melee"},
                 {"quote": "重量に収まる個数までしか買わない", "evidence": "fixed-classC.txt; fixed-live36.txt", "conformance": "approved ammunition fitting preserved"},
                 {"quote": "重量超過時に鉄弾を所持している場合、超過分を預ける。", "evidence": "fixed-calibration.txt; fixed-overweight.txt", "conformance": "retention sees already discharged weight; no needless extra ammo reduction"},
                 {"quote": "町の用事は同じ順位（横取り禁止）＋例外2つ（非破棄の装備取引・自宅の原子操作）", "evidence": "fixed-overweight-s33.txt", "conformance": "fixed 3715 Home tail remains the owner"},
             ]}
    (DIRECTORY / "assertion-audit.txt").write_text(audit, encoding="utf8")
    with (DIRECTORY / "event.jsonl").open("a", encoding="utf8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    print("verified", sum(row["tests"] for row in results.values()), "tests; six audited assertion changes; S33 no defect")


if __name__ == "__main__":
    main()
