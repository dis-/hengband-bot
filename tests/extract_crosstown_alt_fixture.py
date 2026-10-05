"""Freeze a complete late cycle; only this extractor reads operator evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("C:/hengband-backups/state-logs/crosstown-loop-20261006-0355")
OUTPUT = ROOT / "tests/fixtures/crosstown-alt-20261006"


def main():
    decisions_path = SOURCE / "bot-decisions.jsonl"
    state_path = SOURCE / "bot-state-tail.jsonl"
    decisions = [json.loads(line) for line in
                 decisions_path.read_text(encoding="utf-8").splitlines()]
    lines = state_path.read_text(encoding="utf-8").splitlines(keepends=True)
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({})  # the 40MB tail starts mid-row
    end = len(rows) - 1
    while rows[end].get("turn") != decisions[-1]["turn"]:
        end -= 1
    ends = [end]
    for i in range(len(decisions) - 1, 0, -1):
        end = ends[-1] - int(decisions[i - 1]["timing"]["jsonl_drain_records"])
        while rows[end].get("turn") != decisions[i - 1]["turn"]:
            end -= 1
        ends.append(end)
    ends.reverse()
    selected = [i for i, d in enumerate(decisions)
                if 1497 <= d["decision_sequence"] <= 1504]
    segments = [lines[ends[i - 1] + 1:ends[i] + 1] for i in selected]
    for i, segment in zip(selected, segments):
        assert json.loads(segment[-1])["turn"] == decisions[i]["turn"]
    payload = "".join(line.replace("\r\n", "\n")
                      for segment in segments for line in segment).encode("utf-8")
    fixture = OUTPUT.with_suffix(".jsonl.gz")
    fixture.write_bytes(gzip.compress(payload, mtime=0))
    metadata = {
        "source": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (decisions_path, state_path)},
        "base": "4d864cb36cd3ee6d4f887a937c974214e8b17ea0",
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "input_rows": [len(s) for s in segments],
        "state_line_ranges": [[ends[i - 1] + 1, ends[i]] for i in selected],
        "decisions": [{k: decisions[i].get(k) for k in (
            "decision_sequence", "turn", "key", "reason", "position", "store_type",
            "store_visit", "cross_town_shopping", "shop_selector", "town_emit_ownership")}
            for i in selected],
    }
    OUTPUT.with_suffix(".boundaries.json").write_text(
        json.dumps(metadata, ensure_ascii=True, indent=1) + "\n", encoding="utf-8")
    print("Frozen decisions 1497..1504:", len(segments), "inputs,", len(payload), "bytes")


if __name__ == "__main__":
    main()
