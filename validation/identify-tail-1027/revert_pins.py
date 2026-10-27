"""Run positive recorded pins against the base's two changed Python modules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TESTS = [
    "test_recorded_concatenated_failure_completes_with_named_refusal",
    "test_recorded_repeated_failure_outside_delta_completes",
    "test_repetition_suffix_in_fresh_delta_is_recognized",
    "test_dungeon_and_pressure_rebind_visible_target_for_both_languages",
]


def main():
    with tempfile.TemporaryDirectory(prefix="identify-revert-") as raw:
        scratch = Path(raw)
        shutil.copytree(ROOT / "src", scratch / "src", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("cli.py", "input_executor.py"):
            content = subprocess.check_output(["git", "show", "726627a6b:src/hengbot/" + name], cwd=ROOT)
            (scratch / "src/hengbot" / name).write_bytes(content)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(path) for path in (
            scratch / "src", ROOT, ROOT / "tests", ROOT / "scripts")), PYTHONIOENCODING="utf-8")
        ids = ["tests.test_identify_tail_recorded.IdentifyTailRecordedPin." + name for name in TESTS]
        run = subprocess.run([sys.executable, "-m", "unittest", "-v", *ids], cwd=scratch,
                             env=env, capture_output=True, text=True, encoding="utf-8", timeout=240)
        (OUT / "revert-pins.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        failures = [line for line in run.stderr.splitlines() if line.startswith("FAIL: ")]
        errors = [line for line in run.stderr.splitlines() if line.startswith("ERROR: ")]
        value = {"base": "726627a6b", "exit": run.returncode,
                 "assertion_failures": failures, "errors": errors}
        (OUT / "revert-pins.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(value, indent=2))
        return int(run.returncode != 1 or bool(errors) or len(failures) != 7)


if __name__ == "__main__":
    raise SystemExit(main())
