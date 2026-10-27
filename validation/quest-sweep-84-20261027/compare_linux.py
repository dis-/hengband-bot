"""Compare failure identities on identical Linux environments, without filtering tests."""
import ast
from collections import Counter
import json
from pathlib import Path
import re


OUT = Path(__file__).resolve().parent


def headers(text):
    return Counter(re.findall(r"^(?:FAIL|ERROR): ([^\n]+)$", text, re.MULTILINE))


def fast_headers(text, label):
    line = next(line for line in text.splitlines() if line.startswith(label + ":"))
    value = line.split(":", 1)[1].strip()
    return Counter([] if value == "none" else ast.literal_eval(value))


def main():
    head = OUT / "linux"
    base = OUT / "linux-baseline"
    result = {"base": "4db110bd5", "modules": {}}
    summary = json.loads((head / "scope-results.json").read_text(encoding="utf-8"))
    baseline_summary = json.loads((base / "scope-results.json").read_text(encoding="utf-8"))
    result["head"] = summary["head"]
    for module in summary["modules"]:
        candidate = (head / (module + ".log")).read_text(encoding="utf-8")
        baseline = base / (module + ".log")
        if baseline.exists():
            reference = baseline.read_text(encoding="utf-8")
            added = headers(candidate) - headers(reference)
            result["modules"][module] = {
                "head_failure_headers": sum(headers(candidate).values()),
                "base_failure_headers": sum(headers(reference).values()),
                "added": dict(added),
                "same_test_and_skip_counts": all(
                    summary["modules"][module][key] == baseline_summary["modules"][module][key]
                    for key in ("tests", "skipped")
                ),
            }
        else:
            result["modules"][module] = {
                "own_new_module": True, "added": dict(headers(candidate)),
            }
    candidate = (head / "fast-tier-linux.log").read_text(encoding="utf-8")
    reference = (base / "fast-tier-linux.log").read_text(encoding="utf-8")
    result["fast_tier"] = {}
    for label in ("Failures", "Errors"):
        mine, theirs = fast_headers(candidate, label), fast_headers(reference, label)
        result["fast_tier"][label] = {
            "head": sum(mine.values()), "base": sum(theirs.values()),
            "added": dict(mine - theirs),
        }
    total = lambda text: int(re.search(r"^Total: (\d+)", text, re.MULTILINE).group(1))
    new_tests = sum(summary["modules"][module]["tests"]
                    for module, value in result["modules"].items() if value.get("own_new_module"))
    result["fast_test_count"] = {
        "head": total(candidate), "base": total(reference), "new_module_tests": new_tests,
        "same_collection_plus_new_module": total(candidate) == total(reference) + new_tests,
    }
    (OUT / "linux-comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(any(value["added"] for value in result["modules"].values())
               or any(not value.get("same_test_and_skip_counts", True)
                      for value in result["modules"].values())
               or not result["fast_test_count"]["same_collection_plus_new_module"]
               or any(value["added"] for value in result["fast_tier"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
