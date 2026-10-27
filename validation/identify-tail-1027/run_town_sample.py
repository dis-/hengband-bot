"""Use the repository's existing N=5 merge-check mode for the slow module."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    env = dict(os.environ, HENGBOT_TEST_SAMPLE="5", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join(str(ROOT / part) for part in ("", "src", "tests", "scripts")))
    started = time.monotonic()
    with (OUT / "town-work-sampled.log").open("w", encoding="utf-8") as stream:
        run = subprocess.run([sys.executable, str(OUT / "run_module.py"), "test_town_work_contract"],
                             cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
    value = {"exit": run.returncode, "seconds": round(time.monotonic() - started, 2),
             "HENGBOT_TEST_SAMPLE": 5, "python": sys.version,
             "board_controls": {"complete": [1452, 203], "sampled": [292, 42]},
             "recorded_producer_populations": [629, 656]}
    (OUT / "town-work-sampled.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2))
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
