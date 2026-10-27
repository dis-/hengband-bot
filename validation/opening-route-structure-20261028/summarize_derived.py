"""Recover unittest summaries when the runner encounters Windows log encoding."""
from collections import Counter
import json
from pathlib import Path
import re

OUT = Path(__file__).resolve().parent
modules = (OUT / "affected-modules.txt").read_text(encoding="utf-8").splitlines()
results = {}
for module in modules:
    path = OUT / "derived-logs" / (module + ".stderr.log")
    if not path.exists():
        results[module] = {"status": "not_started"}
        continue
    raw = path.read_bytes()
    encoding = "utf-8"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp932"
        text = raw.decode(encoding)
    text = text.replace("\r\n", "\n")
    if "ModuleNotFoundError: No module named 'tests'" in text:
        results[module] = {"status": "not_started"}
        continue
    summary = re.search(r"^Ran (\d+) tests? in ([\d.]+)s\s+^(OK(?: \([^\n]+\))?|FAILED \([^\n]+\))$",
                        text, re.MULTILINE)
    results[module] = {"status": ("ran" if summary.group(3).startswith("OK") else "failed")
                       if summary else "incomplete",
                       "log_encoding": encoding,
                       "failing_headers": re.findall(r"^(?:FAIL|ERROR): .+$", text, re.MULTILINE),
                       "stderr_path": str(path.relative_to(OUT))}
    if summary:
        results[module].update(tests=int(summary.group(1)), seconds=float(summary.group(2)),
                               summary=summary.group(3))
counts = Counter(row["status"] for row in results.values())
data = {"provenance": "unittest stderr summaries; process exit codes are not inferred",
        "counts": dict(counts), "modules": results}
(OUT / "derived-summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
print(dict(counts), "tests:", sum(row.get("tests", 0) for row in results.values()))
for name, row in results.items():
    if row["status"] == "failed":
        print(name, row["failing_headers"])
