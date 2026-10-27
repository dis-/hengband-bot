"""Compare unrelated guard findings with the requested base revision."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "726627a6b"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import test_fakery_lint as lint
    changed = set(git("diff", "--name-only", BASE, "HEAD", "--", "tests").decode().splitlines())
    current, baseline = [], []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        findings = [item.render() for item in lint.analyze_source(source, Path(relative)) if not item.allowed_reason]
        current.extend(findings)
        if relative in changed:
            content = subprocess.run(["git", "show", BASE + ":" + relative], cwd=ROOT,
                                     capture_output=True)
            findings = ([item.render() for item in lint.analyze_source(content.stdout.decode("utf-8"),
                         Path(relative)) if not item.allowed_reason] if content.returncode == 0 else [])
        baseline.extend(findings)
    value = {"lint_current": current, "lint_baseline": baseline,
             "lint_added": sorted(set(current) - set(baseline))}
    with tempfile.TemporaryDirectory(prefix="identify-base-") as raw:
        scratch = Path(raw)
        shutil.copytree(ROOT / "src", scratch / "src", ignore=shutil.ignore_patterns("__pycache__"))
        for path in git("diff", "--name-only", BASE, "HEAD", "--", "src").decode().splitlines():
            (scratch / path).write_bytes(git("show", BASE + ":" + path))
        test = "tests.test_flight_recorder.FlightRecorderTest.test_budget_stats_unprunable_bulk_only_once_during_deletion_loop"
        assert not git("diff", BASE, "HEAD", "--", "tests/test_flight_recorder.py")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(path) for path in (
            scratch / "src", ROOT, ROOT / "tests", ROOT / "scripts")), PYTHONIOENCODING="utf-8")
        run = subprocess.run([sys.executable, "-m", "unittest", "-v", test], cwd=scratch,
                             env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        (OUT / "baseline-flight.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        value["flight_base_exit"] = run.returncode
        value["flight_same_failure"] = "AssertionError: 5 != 4" in run.stderr
        shutil.copytree(ROOT / "scripts", scratch / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        for document in ROOT.glob("*.md"):
            shutil.copyfile(document, scratch / document.name)
        (scratch / "scripts/town_work_manifest.json.gz").write_bytes(
            git("show", BASE + ":scripts/town_work_manifest.json.gz"))
        generated = subprocess.run([sys.executable, str(scratch / "scripts/town_work_manifest.py")],
                                  cwd=scratch, env=env, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
        (OUT / "baseline-manifest.log").write_text(generated.stdout + generated.stderr, encoding="utf-8")
        value["manifest_base_exit"] = generated.returncode
        value["manifest_same_failure"] = "generated town work manifest is stale" in generated.stdout
    (OUT / "baseline-comparison.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("lint", len(current), len(baseline), "added", len(value["lint_added"]))
    print("baseline flight", value["flight_base_exit"], value["flight_same_failure"])
    return int(bool(value["lint_added"]) or not value["flight_same_failure"]
               or not value["manifest_same_failure"])


if __name__ == "__main__":
    raise SystemExit(main())
