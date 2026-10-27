"""Run the derived HEAD scope in an isolated checkout, saving each result."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import verify_scope as scope_tool
sys.path.insert(0, r"C:\hengband-backups\guard-tools")
from gate_lock import wait_for_gate


def main():
    wait_for_gate("opening-scope")
    # Detached checkouts do not inherit the main worktree's ancestor game data.
    definitions = ROOT.parents[2] / "lib/edit/MonraceDefinitions.jsonc"
    if not definitions.is_file():
        raise FileNotFoundError(definitions)
    os.environ["HENGBAND_MONRACE_DEFINITIONS"] = str(definitions)
    head = "eb3ce7da643629a1a65553aa3bc523fbda049ed8"
    base = scope_tool.git(ROOT, "rev-parse", head + "^").strip()
    scope = scope_tool.derive_scope(ROOT, base, head)
    label = "scope"
    if "--compare-main" in sys.argv:
        head = json.loads((OUT / "guard-results.json").read_text())["base"]
        scope["modules"] = ["tests.test_policy"]
        label = "main-baseline"
    result = {"head": head, "base": base, "python": sys.version,
              "derived": scope, "modules": {}}
    checkout = Path(tempfile.mkdtemp(prefix="hengbot-verify-"))
    scope_tool.record_worktree_owner(checkout)
    try:
        scope_tool.git(ROOT, "worktree", "add", "--detach", str(checkout), head)
        scope_tool.copy_runtime_artifacts(ROOT, checkout)
        work = [(m, [sys.executable, "-m", "unittest", "-v", m])
                for m in scope["modules"]]
        work.extend((m, [sys.executable, m]) for m in scope["lints"])
        def run(module, command):
            if module.startswith("scripts/"):
                # run_item retains stderr only; preserve lint findings on stdout too.
                stdout = OUT / (label + "-" + Path(module).stem + ".stdout.log")
                command = [sys.executable, "-c",
                           "import subprocess,sys; "
                           f"f=open({str(stdout)!r},'w',encoding='utf8'); "
                           f"p=subprocess.run({command!r},stdout=f,stderr=subprocess.STDOUT); "
                           "f.close(); sys.exit(p.returncode)"]
            return scope_tool.run_item(checkout, module, command, 2400,
                                       OUT / (label + "-logs"))

        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks = {pool.submit(run, m, cmd): m for m, cmd in work}
            for task in as_completed(tasks):
                module = tasks[task]
                result["modules"][module] = task.result()
                (OUT / (label + "-results.json")).write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf8")
                print(module, task.result()["status"], task.result()["duration"], flush=True)
        return int(any(r["status"] in {"failed", "error"}
                       for r in result["modules"].values()))
    finally:
        scope_tool.cleanup_worktree(checkout, ROOT)


if __name__ == "__main__":
    sys.exit(main())
