"""Freeze the 07:10:40 Home scan incident; read backup sources only."""
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hengbot.baseitem_knowledge import find_baseitem_definitions, load_baseitem_costs

SOURCE = Path(r"C:\hengband-backups\state-logs\home-full-await-knowledge-20261004-0710")
OUTPUT = ROOT / "tests/fixtures/home-full-await-knowledge-20261004.json.gz"


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    state = next(SOURCE.glob("autorecover-20261004-071054*.bot-state-fixed.jsonl.gz"))
    decision = next(SOURCE.glob("autorecover-20261004-071054*.bot-decisions.jsonl.gz"))
    with gzip.open(state, "rt", encoding="utf8") as stream:
        states = [json.loads(line) for line in stream]
    with gzip.open(decision, "rt", encoding="utf8") as stream:
        decisions = [json.loads(line) for line in stream]
    process = SOURCE / "bot-state-fixed.jsonl"
    with process.open(encoding="utf8") as stream:
        for index, line in enumerate(stream):
            if 'skill_exp' not in line:
                continue
            row = json.loads(line)
            if row.get("knowledge", {}).get("category") == "skill_exp":
                skill = {"line": index + 1, "row": row}
                break
        else:
            raise ValueError("process capture has no skill knowledge")
    definitions = find_baseitem_definitions(ROOT)
    costs = load_baseitem_costs(definitions)
    relevant = {(item["tval"], item["sval"])
                for item in states[53]["knowledge"]["items"] if "sval" in item}
    # State lines 51-75 cover the previous sale, complete Home scan, next
    # withdrawal/sale, and the 07:10:40 store board. Decisions 207-218 bind it.
    pin = {
        "provenance": {
            "capture": SOURCE.name,
            "state_sha256": digest(state),
            "decision_sha256": digest(decision),
            "process_state_sha256": digest(process),
            "baseitem_definitions_sha256": digest(definitions),
            "note": "No policy checkpoint retained. Raw recorded boards; policy ledgers reconstructed explicitly. Historical replay stops on first differing key.",
        },
        "states": [{"line": index + 1, "row": states[index]} for index in range(50, 75)],
        "decisions": [{"line": index + 1, "row": decisions[index]} for index in range(206, 218)],
        "skill_knowledge": skill,
        "baseitem_costs": [[tval, sval, costs[(tval, sval)]]
                           for tval, sval in sorted(relevant) if (tval, sval) in costs],
    }
    OUTPUT.write_bytes(gzip.compress(json.dumps(
        pin, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0))
    print(f"{OUTPUT.name}: {digest(OUTPUT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
