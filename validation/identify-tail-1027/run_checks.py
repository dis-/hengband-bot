"""Run the requested guards and every derived module without changing sources."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "726627a6b"
GUARDS = Path("C:/hengband-backups/guard-tools")
GENERATOR_PYTHON = Path("C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe")
ENV = dict(os.environ, PYTHONPATH=os.pathsep.join(str(ROOT / part)
           for part in ("", "src", "tests", "scripts")), PYTHONIOENCODING="utf-8")


def main():
    results = {}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    commands = {
        "preflight": [str(GENERATOR_PYTHON), str(GUARDS / "preflight.py"), str(ROOT), BASE],
        "derive": [sys.executable, "scripts/verify_scope.py", "--base", BASE,
                   "--target", "HEAD", "--derive-only", "--output", str(OUT / "scope.json")],
        "fast-tier": [str(GENERATOR_PYTHON), str(GUARDS / "fast_tier.py"), str(ROOT), BASE,
                      "--shards", "2"],
    }
    if "--scope-only" in sys.argv:
        previous = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
        results, head, commands = previous["stages"], previous["head"], {}
    for name, command in commands.items():
        print("starting", name, flush=True)
        started = time.monotonic()
        with (OUT / (name + ".log")).open("w", encoding="utf-8") as stream:
            process = subprocess.run(command, cwd=ROOT, env=ENV, stdout=stream,
                                     stderr=subprocess.STDOUT)
        results[name] = {"exit": process.returncode, "seconds": round(time.monotonic() - started, 2)}
        print(name, results[name], flush=True)
        (OUT / "results.json").write_text(json.dumps({"head": head, "base": BASE,
             "python": sys.version, "stages": results}, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_scope
    scope = json.loads((OUT / "scope.json").read_text(encoding="utf-8"))["derived"]
    print("starting", len(scope["modules"]), "modules and", len(scope["lints"]), "lints", flush=True)
    work = [(module, [sys.executable, str(OUT / "run_module.py"), module.removeprefix("tests.")])
            for module in scope["modules"]]
    work += [(lint, [sys.executable, lint]) for lint in scope["lints"]]
    modules = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(verify_scope.run_item, ROOT, key, command, 600,
                              OUT / "module-logs-complete"): key for key, command in work}
        for future in as_completed(futures):
            modules[futures[future]] = future.result()
    (OUT / "modules.json").write_text(json.dumps(modules, indent=2) + "\n", encoding="utf-8")
    for key, value in modules.items():
        print(key, value["status"], value.get("failed", 0), flush=True)
    return int(any(value["exit"] for value in results.values())
               or any(value["status"] in {"failed", "error"} for value in modules.values()))


if __name__ == "__main__":
    raise SystemExit(main())
