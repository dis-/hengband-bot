"""Record issue #47 verification with system Python and UTF-8 logs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
GUARDS = Path(r"C:\hengband-backups\guard-tools")
ENV = dict(os.environ, PYTHONPATH="src;tests;scripts", PYTHONIOENCODING="utf-8")
BASE = subprocess.check_output(["git", "rev-parse", "main"], cwd=ROOT, text=True).strip()
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
RESULTS = {}


def run(name, args):
    started = time.monotonic()
    with (OUT / (name + ".log")).open("w", encoding="utf-8") as stream:
        proc = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT,
                              env=ENV, stdout=stream, stderr=subprocess.STDOUT)
    RESULTS[name] = {"exit_code": proc.returncode, "seconds": round(time.monotonic() - started, 3),
                     "command": [sys.executable, *map(str, args)]}
    (OUT / (sys.argv[1] + "-results.json")).write_text(json.dumps({"base": BASE, "head": HEAD, "results": RESULTS},
                                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(name, RESULTS[name], flush=True)
    return proc.returncode


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "structure":
        run("four-structural-tests", ["-m", "unittest",
            "tests.test_ownership_s2a1_closure.GoalTypingTableTest.test_every_reason_the_package_can_emit_is_typed",
            "tests.test_ownership_s2a1_closure.SurvivalTriggerTest.test_every_return_start_and_end_is_recorded",
            "tests.test_town_arbiter.TownTurnArbiterAcceptanceTest.test_pin_vacuity_registered_owner_consumes_static_reason_census",
            "tests.test_quest_door_confirm_recorded.StepEntryStructureTest.test_every_walking_producer_consults_the_confirm_predicate"])
    elif mode == "preflight":
        run("preflight", [GUARDS / "preflight.py", ROOT, BASE])
        run("affected", [GUARDS / "affected_tests.py", ROOT, BASE, HEAD])
        run("scope-derive", ["scripts/verify_scope.py", "--base", BASE, "--target", "WORKTREE",
                             "--derive-only", "--output", OUT / "scope.json"])
    elif mode == "mutation":
        scratch = Path(tempfile.mkdtemp(prefix="opening-structure-mutation-"))
        subprocess.run(["git", "worktree", "add", "--detach", str(scratch), HEAD], cwd=ROOT, check=True)
        shutil.copytree(Path(r"C:\hengband\lib\edit"), scratch / "lib" / "edit")
        (OUT / "mutation-worktree.txt").write_text(str(scratch) + "\n", encoding="utf-8")
        selected = json.loads((ROOT / "validation/opening-route-pins-20261027/mutation-selected-command.json").read_text(encoding="utf-8"))["tests"]
        selected.extend([
            "tests.test_ownership_s2a1_closure.GoalTypingTableTest.test_every_reason_the_package_can_emit_is_typed",
            "tests.test_ownership_s2a1_closure.SurvivalTriggerTest.test_every_return_start_and_end_is_recorded",
            "tests.test_town_arbiter.TownTurnArbiterAcceptanceTest.test_pin_vacuity_registered_owner_consumes_static_reason_census",
            "tests.test_quest_door_confirm_recorded.StepEntryStructureTest.test_every_walking_producer_consults_the_confirm_predicate",
        ])
        run("mutation", [GUARDS / "mutation_check.py", scratch, BASE, "--record", "--full",
                         "--tests", *selected, "--timeout", "2400"])
    elif mode == "fast":
        run("fast", [GUARDS / "fast_tier.py", ROOT, BASE, "--shards", "4"])
    elif mode == "derived":
        sys.path.insert(0, str(ROOT / "scripts"))
        import verify_scope as scope_harness
        affected = subprocess.check_output([sys.executable, str(GUARDS / "affected_tests.py"),
                                            str(ROOT), BASE, HEAD], cwd=ROOT, env=ENV,
                                           text=True, encoding="utf-8")
        (OUT / "affected-modules.txt").write_text(affected, encoding="utf-8")
        modules = [line for line in affected.splitlines() if line.startswith("tests.")]
        runners = OUT / "derived-runners"
        runners.mkdir(exist_ok=True)
        results = {}

        def module_run(module):
            runner = runners / (module + ".py")
            runner.write_text("import sys\nsys.path.insert(0, " + repr(str(ROOT)) + ")\n"
                              + scope_harness._test_code(module), encoding="utf-8")
            return scope_harness.run_item(ROOT, module, [sys.executable, str(runner)],
                                          1200, OUT / "derived-logs")

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(module_run, module): module for module in modules}
            for future in as_completed(futures):
                module = futures[future]
                results[module] = future.result()
                (OUT / "derived-results.json").write_text(json.dumps(
                    {"base": BASE, "head": HEAD, "modules": results,
                     "excluded_tests": scope_harness.EXCLUDED_TESTS},
                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(module, results[module]["status"], results[module]["duration"], flush=True)
