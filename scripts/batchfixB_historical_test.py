"""Run one authorized module against read-only historical production sources."""
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
revision, module = sys.argv[1:3]
with tempfile.TemporaryDirectory(prefix="batchfixB-history-", dir=ROOT / "reports/batchfixB") as directory:
    archive = subprocess.check_output(["git", "archive", revision, "src"])
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(directory, filter="data")
    sys.path[:0] = [str(Path(directory) / "src"), str(ROOT), str(ROOT / "tests"), str(ROOT / "scripts")]
    if module.startswith("first:"):
        import runpy
        sys.argv = ["batchfixB_first_optimizer_difference.py", module.split(":", 1)[1]]
        runpy.run_path(str(ROOT / "scripts/batchfixB_first_optimizer_difference.py"), run_name="__main__")
        raise SystemExit(0)
    import unittest
    print("HISTORICAL", revision, module, flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(module))
    raise SystemExit(not result.wasSuccessful())
